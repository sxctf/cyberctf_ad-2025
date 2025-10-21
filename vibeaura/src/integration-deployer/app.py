from flask import Flask, render_template, jsonify, request
import requests, yaml, os, json, re
import logging
import time
from logs import *
from token_gc import get_token
from deploy import prepare_job, deploy_service

app = Flask(__name__, template_folder='templates')

setup_logging()
logger = logging.getLogger("integration")

path = "integration_config.yml"

if os.path.exists(path):
        with open(path, 'rt') as f:
            config = yaml.safe_load(f)
            
             
def get_message_content(resp):
    try:
        response_json = resp.json()
        contents = [
            choice["message"]["content"]
            for choice in response_json.get("choices", [])
            if "message" in choice and "content" in choice["message"]
        ]
        return contents if contents else None
    except Exception as e:
        logger.error(f"Failed to parse response from GigaChat: {e}")
        return None
    
 
def extract_python_code(raw):
    if isinstance(raw, list) and raw:
        raw = raw[0]

    if not isinstance(raw, str):
        return ""

    match = re.search(r'```(?:python)?\n(.*?)```', raw, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else ""

def extract_docker_code(raw):
    if isinstance(raw, list) and raw:
        raw = raw[0]

    if not isinstance(raw, str):
        return ""

    pattern = re.compile(
        r'Dockerfile\s*[-=_.]*\s*```(?:dockerfile)?\s*(.*?)```',
        re.DOTALL | re.IGNORECASE
    )
    match = pattern.search(raw)
    return match.group(1).strip() if match else ""


def extract_html_code(raw):
    if isinstance(raw, list) and raw:
        raw = raw[0]

    if not isinstance(raw, str):
        return ""

    pattern = re.compile(
        r'.*html.*?```(?:html)?\s*\n(.*?)```',
        re.DOTALL | re.IGNORECASE
    )
    match = pattern.search(raw)
    return match.group(1).strip() if match else ""

### API 

# User request Handler
@app.route('/integration/v1/generate', methods=['POST'])
def webUiRequest():
    json_data = request.json
    logger.info(f"Get data from service WebUI: {json_data}")
    
    generated_python_code = ""
    generated_dockerfile_code = ""
    generated_html_code = ""
    
    if json_data.get("cached", False):
        logger.info("Processing CACHED request - using provided code from cache")
        
        generated_python_code = json_data.get("python_code", "")
        generated_dockerfile_code = json_data.get("dockerfile_code", "")
        generated_html_code = json_data.get("html_code", "")
        
        if not generated_python_code:
            logger.error("Cached request but no python_code provided")
            return jsonify({"message": "No cached code provided"})
        
        logger.info(f"Using cached code (Python: {len(generated_python_code)} chars, Dockerfile: {len(generated_dockerfile_code)} chars, HTML: {len(generated_html_code)})")
        
    else:
        logger.info("Processing NEW request - generating code via LLM")
        
        user_prompt = json_data.get("taskDescription", "")
        if not user_prompt:
            logger.error("New request but no taskDescription provided")
            return jsonify({"message": "No task description provided"})
        
        max_retries = 2
        for attempt in range(max_retries):
            try:
                access_token = get_token()
                if not access_token:
                    logger.error("Failed to get access token")
                    if attempt < max_retries - 1:
                        continue
                    else:
                        return jsonify({"message": "Failed to authenticate with LLM service"})
                
                headers = {
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json"
                }
                
                data = {
                    "model": config["LLM"]["model_name"],
                    "messages": [
                        {
                            "role": "system",
                            "content": config["LLM"]["system_prompt"]   
                        },
                        {
                            "role": "user",
                            "content": user_prompt  
                        }
                    ],
                    "stream": config["LLM"]["stream"],
                    "repetition_penalty": 1
                }
                
                logger.info(f"Making LLM request (attempt {attempt + 1}/{max_retries})")
                resp = requests.post(config["urls"]["llm"], headers=headers, json=data, timeout=(15, 50))
                
                if resp.status_code == 401:
                    logger.error(f"Received 401 on attempt {attempt + 1}")
                    
                    access_token = get_token(force_refresh=True)
                    headers = {
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json"
                    }

                    resp = requests.post(config["urls"]["llm"], headers=headers, json=data, timeout=(15, 50))

                    if resp.status_code == 401:
                        logger.error(f"Received 401 again after token refresh on attempt {attempt + 1}")
                        continue
                
                if resp.status_code == 429:
                    logger.error(f"Received 429 - Rate limit exceeded on attempt {attempt + 1}")
                    return jsonify({"message": "Too many requests to LLM service. Please try again later."})
                
                resp.raise_for_status()
                
                messages = get_message_content(resp)
                logger.info(f"Get answer from GigaChat {messages}")
                generated_python_code = extract_python_code(messages)
                generated_dockerfile_code = extract_docker_code(messages)
                generated_html_code = extract_html_code(messages)
                
                if not generated_python_code:
                    logger.error("No valid Python code extracted from LLM response")
                    if attempt < max_retries - 1:
                        continue
                    else:
                        return jsonify({"message": "No valid code returned from model"})
                        
                logger.info(f"Generated new code (Python: {len(generated_python_code)} chars, Dockerfile: {len(generated_dockerfile_code)} chars, HTML: {len(generated_html_code)})")
                break
                    
            except requests.exceptions.ReadTimeout:
                logger.error('The gigaproxy did not respond within the allotted time.')
                if attempt == max_retries - 1:
                    return jsonify({"message": "The server did not respond within the allotted time."})
                
            except requests.exceptions.HTTPError as e:
                logger.error(f'HTTP error occurred: {e}')
                if attempt == max_retries - 1:
                    return jsonify({"message": f"LLM service error: {str(e)}"})
                    
            except requests.exceptions.RequestException as e:
                logger.error(f'Request error occurred: {e}')
                if attempt == max_retries - 1:
                    return jsonify({"message": "An error occurred during LLM request"})
            
            if attempt < max_retries - 1:
                time.sleep(1)
        else:
            return jsonify({"message": "Failed to generate code after multiple attempts"})
    
    max_deployment_retries = 2
    for attempt in range(max_deployment_retries):
        try:
            job_id, job_dir = prepare_job(generated_python_code, generated_dockerfile_code, generated_html_code)
            port, container_name = deploy_service(job_id, job_dir)
            
            if port is None:
                logger.error(f"Deployment failed on attempt {attempt + 1}")
                if attempt < max_deployment_retries - 1:
                    time.sleep(2)
                    continue
                else:
                    logger.error(f"[{job_id}] Failed to deploy the container")
                    return jsonify({
                        "message": "Failed to deploy the container",
                        "python_code": generated_python_code,
                        "dockerfile_code": generated_dockerfile_code,
                        "port": None,
                        "content": "Deployment failed but code was generated",
                        "meta": None,
                        "cached": json_data.get("cached", False),
                        "should_cache": False,
                        "error_type": "deployment_failed"
                    })
            
            logger.info(f"Successfully deployed service on port {port}")
            break
            
        except Exception as e:
            logger.error(f"Deployment failed on attempt {attempt + 1}: {e}")
            if attempt == max_deployment_retries - 1:
                return jsonify({
                    "message": f"Deployment failed: {str(e)}",
                    "python_code": generated_python_code,
                    "dockerfile_code": generated_dockerfile_code,
                    "port": None,
                    "content": f"Deployment failed but code was generated. Error: {str(e)}",
                    "meta": None,
                    "cached": json_data.get("cached", False),
                    "should_cache": False,
                    "error_type": "deployment_error"
                })
    else:
        return jsonify({
            "message": "Deployment failed after all retries",
            "python_code": generated_python_code,
            "dockerfile_code": generated_dockerfile_code,
            "port": None,
            "content": "Deployment failed after multiple attempts but code was generated",
            "meta": None,
            "cached": json_data.get("cached", False),
            "should_cache": False,
            "error_type": "deployment_retries_exhausted"
        })
    
    response = {
        "message": generated_python_code,  
        "python_code": generated_python_code,  
        "dockerfile_code": generated_dockerfile_code,
        "html_code" : generated_html_code,  
        "port": port,
        "content": f"Your service deployed on port: {port}\nContainer directory: {job_dir}",
        "meta": container_name,
        "should_cache": True,
        "cached": json_data.get("cached", False) 
    }
    
    logger.info(f"Returning response (cached: {response['cached']})")
    return jsonify(response)


       
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8992)