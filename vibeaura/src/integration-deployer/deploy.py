import subprocess
import threading
import logging
import os
import socket
import uuid
import shutil
import requests
import time
from typing import Dict, Tuple

logger = logging.getLogger("integration")
logger.setLevel(logging.INFO)

DOCKER_LIFETIME = 120
CTF_NETWORK = "ctf-net"
CTF_PORT_RANGE = (8000, 8100)
CPU = "0.25"
MEM = "512m"
WEBUI_LOG_ENDPOINT = "http://web-ui:8080/integration/v1/logs"

BUFFER_SIZE = 5
BUFFER_TIMEOUT = 2

active_containers: Dict[str, dict] = {}
cleanup_timers: Dict[str, threading.Timer] = {}

def is_port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(('', port))
            return True
        except OSError:
            return False

def allocate_free_port_from_range(start: int, end: int) -> int:
    for port in range(start, end + 1):
        if is_port_free(port):
            return port
    raise RuntimeError(f"All ports in range {start}-{end} are currently in use.")

def ensure_docker_network(network_name: str):
    existing_networks = subprocess.run(
        ["docker", "network", "ls", "--format", "{{.Name}}"],
        capture_output=True, text=True, check=True
    ).stdout.splitlines()

    if network_name not in existing_networks:
        logger.info(f"Creating Docker network '{network_name}'...")
        subprocess.run(["docker", "network", "create", network_name], check=True)
            
def precompile_python_code(file_path: str) -> bool:
    try:
        result = subprocess.run(
            ["python3", "-m", "py_compile", file_path],
            capture_output=True, text=True, check=True
        )
        logger.info(f"Precompiled {file_path} successfully.")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Precompilation failed:\nSTDOUT:\n{e.stdout}\nSTDERR:\n{e.stderr}")
        return False

def prepare_job(code: str, dockerfile: str, html: str) -> tuple[str, str]:
    job_uuid = str(uuid.uuid4())
    job_dir = os.path.join("generated_jobs", job_uuid)
    templates_dir = os.path.join(job_dir, "templates")

    os.makedirs(job_dir, exist_ok=True)
    os.makedirs(templates_dir, exist_ok=True)

    with open(os.path.join(job_dir, "main.py"), "w", encoding="utf-8") as f:
        f.write(code)
    with open(os.path.join(job_dir, "Dockerfile"), "w", encoding="utf-8") as f:
        f.write(dockerfile)
    with open(os.path.join(templates_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)

    if not precompile_python_code(f"{job_dir}/main.py"):
        logger.error(f"[{job_uuid}] Python code failed precompilation. Aborting job.")
        shutil.rmtree(job_dir)
        return None
    
    return job_uuid, job_dir

def send_logs_to_webui(container_name: str, stdout: str, stderr: str):
    try:
        payload = {"container_name": container_name, "stdout": stdout, "stderr": stderr}
        response = requests.post(WEBUI_LOG_ENDPOINT, json=payload, timeout=10)
        if response.status_code != 200:
            logger.error(f"[{container_name}] Failed to send logs: {response.status_code} {response.text}")
        else:
            logger.info(f"[{container_name}] Logs sent to WebUI")
    except Exception as e:
        logger.error(f"[{container_name}] Error sending logs: {e}")

def schedule_container_cleanup(container_name: str, image_name: str, job_id: str):
    def cleanup_task():
        logger.info(f"[{container_name}] Auto-cleanup timer expired, destroy running container")
        destroy_container(container_name, image_name, job_id)
        cleanup_timers.pop(container_name, None)
        active_containers.pop(container_name, None)
    
    timer = threading.Timer(DOCKER_LIFETIME, cleanup_task)
    timer.daemon = True
    timer.start()
    
    cleanup_timers[container_name] = timer
    active_containers[container_name] = {
        "image_name": image_name,
        "job_id": job_id,
        "created_at": time.time()
    }
    
    logger.info(f"[{container_name}] Scheduled auto-cleanup in {DOCKER_LIFETIME} seconds")

def cancel_scheduled_cleanup(container_name: str):
    if container_name in cleanup_timers:
        cleanup_timers[container_name].cancel()
        cleanup_timers.pop(container_name)
        logger.info(f"[{container_name}] Cancelled scheduled cleanup")

def monitor_and_collect_logs(container_name: str, image_name: str, job_id: str):
    logger.info(f"[{container_name}] Starting log monitoring")
    buffer = []
    last_flush = time.time()

    try:
        check_result = subprocess.run(
            ["docker", "ps", "-f", f"name={container_name}", "--format", "{{.Names}}"],
            capture_output=True, text=True, check=False
        )
        
        if container_name not in check_result.stdout:
            logger.warning(f"[{container_name}] Container not found at monitor start")
            destroy_container(container_name, image_name, job_id)
            return

        proc = subprocess.Popen(
            ["docker", "logs", "-f", container_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        while True:
            line = proc.stdout.readline()
            if line == '' and proc.poll() is not None:
                logger.info(f"[{container_name}] Container stopped, ending log monitoring")
                break
            if line:
                buffer.append(line.rstrip())

            now = time.time()
            if len(buffer) >= BUFFER_SIZE or (now - last_flush >= BUFFER_TIMEOUT and buffer):
                log_text = "\n".join(buffer)
                send_logs_to_webui(container_name, log_text, "")
                buffer.clear()
                last_flush = now

        if buffer:
            log_text = "\n".join(buffer)
            send_logs_to_webui(container_name, log_text, "")

    except Exception as e:
        logger.error(f"[{container_name}] Error while monitoring logs: {e}")

    finally:
        logger.info(f"[{container_name}] Log monitoring finished, ensuring cleanup")
        destroy_container(container_name, image_name, job_id)

def start_log_monitoring(container_name: str, image_name: str, job_id: str):
    thread = threading.Thread(
        target=monitor_and_collect_logs,
        args=(container_name, image_name, job_id),
        daemon=True
    )
    thread.start()
    return thread

def deploy_service(job_id: str, job_dir: str) -> tuple[int, str] | None:
    ensure_docker_network(CTF_NETWORK)
    image_name = f"ctf_job_{job_id}"
    container_name = f"ctf_container_{job_id}"
    host_dir = os.path.abspath(os.path.join("generated_jobs", job_id))
    
    try:
        port = allocate_free_port_from_range(*CTF_PORT_RANGE)
    except RuntimeError as e:
        logger.error(f"[{container_name}] Failed to allocate port: {e}")
        if os.path.exists(job_dir):
            shutil.rmtree(job_dir)
        return None

    try:
        logger.info(f"[{container_name}] Building Docker image...")
        build_result = subprocess.run(
            ["docker", "build", "-t", image_name, "."],
            cwd=job_dir, 
            capture_output=True, 
            text=True, 
            check=True
        )
        
        logger.info(f"[{container_name}] Running container on {port}...")
        run_result = subprocess.run([
            "docker", "run", "-d", 
            "--rm",
            "--cpus", CPU,
            "--memory", MEM,
            "--name", container_name,
            "--network", CTF_NETWORK,
            "-p", f"{port}:5000",
            "--privileged",
            "-v", f"{host_dir}:/app",
            image_name
        ], capture_output=True, text=True, check=True)
        
        logger.info(f"[{container_name}] Run output: {run_result.stdout.strip()}")
        logger.info(f"[{container_name}] Run stderr: {run_result.stderr.strip()}")

        time.sleep(7) 
        
        try:
            logs_result = subprocess.run(
                ["docker", "logs", container_name],
                capture_output=True, text=True, timeout=10
            )
            
            if logs_result.stdout:
                full_logs = logs_result.stdout
                logs_lower = full_logs.lower()
                
                if any(error_word in logs_lower for error_word in ["error", "exception", "traceback"]):
                    logger.error(f"[{container_name}] Application failed with errors:")
                    logger.error(f"FULL ERROR LOGS:\n{full_logs}")
                    return None
                else:
                    logger.info(f"[{container_name}] Container logs look clean")
                    
            if logs_result.stderr:
                logger.error(f"[{container_name}] Container stderr: {logs_result.stderr}")
                
        except subprocess.TimeoutExpired:
            logger.error(f"[{container_name}] Logs check timeout")
        except Exception as e:
            logger.error(f"[{container_name}] Failed to check logs: {e}")
        
        check_result = subprocess.run(
            ["docker", "ps", "-f", f"name={container_name}", "--format", "{{.Names}}"],
            capture_output=True, text=True, check=True
        )
        logger.info(f"Containger {container_name} result {check_result}")
        
        if container_name not in check_result.stdout:
            logger.error(f"[{container_name}] Container failed to start")
            destroy_container(container_name, image_name, job_id)
            return None

        start_log_monitoring(container_name, image_name, job_id)
        schedule_container_cleanup(container_name, image_name, job_id)

        logger.info(f"[{container_name}] Deployment successful on port {port}")
        return port, container_name

    except subprocess.CalledProcessError as e:
        logger.error(f"[{container_name}] Deployment failed: {e}")
        destroy_container(container_name, image_name, job_id)
        return None
    except Exception as e:
        logger.error(f"[{container_name}] Unexpected error: {e}")
        destroy_container(container_name, image_name, job_id)
        return None

def destroy_container(container_name: str, image_name: str, job_id: str):
    logger.info(f"[{container_name}] Starting destruction process...")
    
    cancel_scheduled_cleanup(container_name)
    
    errors = []
    
    try:
        stop_result = subprocess.run(
            ["docker", "rm", "-f", container_name], 
            capture_output=True, text=True, check=False, timeout=30
        )
        if stop_result.returncode == 0:
            logger.info(f"[{container_name}] Container removed")
        else:
            if "No such container" not in stop_result.stderr:
                errors.append(f"Container removal: {stop_result.stderr}")
    except subprocess.TimeoutExpired:
        errors.append("Container removal timeout")
    except Exception as e:
        errors.append(f"Container removal error: {e}")

    try:
        rmi_result = subprocess.run(
            ["docker", "rmi", "-f", image_name],
            capture_output=True, text=True, check=False, timeout=30
        )
        if rmi_result.returncode == 0:
            logger.info(f"[{container_name}] Image removed")
        else:
            if "No such image" not in rmi_result.stderr:
                errors.append(f"Image removal: {rmi_result.stderr}")
    except subprocess.TimeoutExpired:
        errors.append("Image removal timeout")
    except Exception as e:
        errors.append(f"Image removal error: {e}")

    try:
        job_dir = os.path.join("generated_jobs", job_id)
        if os.path.exists(job_dir):
            shutil.rmtree(job_dir)
            logger.info(f"[{container_name}] Job directory removed: {job_dir}")
        else:
            logger.info(f"[{container_name}] Job directory already removed: {job_dir}")
    except Exception as e:
        errors.append(f"Directory removal: {e}")

    if errors:
        logger.error(f"[{container_name}] Destruction completed with errors: {'; '.join(errors)}")
    else:
        logger.info(f"[{container_name}] Destruction completed successfully")

def cleanup_all_containers():
    logger.info("Starting cleanup of all active containers...")
    
    for container_name, timer in list(cleanup_timers.items()):
        timer.cancel()
    
    for container_name, info in list(active_containers.items()):
        destroy_container(container_name, info["image_name"], info["job_id"])
    
    cleanup_timers.clear()
    active_containers.clear()
    logger.info("All containers cleanup completed")

def cleanup_orphaned_jobs():
    try:
        result = subprocess.run(["docker", "ps", "--format", "{{.Names}}"],
                                capture_output=True, text=True, check=True)
        running_containers = set(name for name in result.stdout.splitlines()
                                 if name.startswith("ctf_container_"))

        jobs_root = "generated_jobs"
        if not os.path.exists(jobs_root):
            logger.info(f"Directory {jobs_root} does not exist, nothing to clean.")
            return

        cleaned_count = 0
        for job_dir in os.listdir(jobs_root):
            job_path = os.path.join(jobs_root, job_dir)
            if not os.path.isdir(job_path):
                continue
            expected_container_name = f"ctf_container_{job_dir}"
            if expected_container_name not in running_containers:
                logger.info(f"Cleaning up orphaned job directory: {job_path}")
                shutil.rmtree(job_path)
                cleaned_count += 1
        
        if cleaned_count > 0:
            logger.info(f"Cleaned up {cleaned_count} orphaned job directories")

    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to get running containers: {e}")
    except Exception as e:
        logger.error(f"Error during orphaned jobs cleanup: {e}")