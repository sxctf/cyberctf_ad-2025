from flask import Flask, render_template, jsonify, request, make_response
from urllib.parse import urlparse
import requests
from logs import *
from security import *
import generate_keys 
from model import *
import logging
import subprocess
import time
import threading


app = Flask(__name__, template_folder='templates')

setup_logging()
logger = logging.getLogger("webui")

def start_cleanup_scheduler():
    def cleanup_worker():
        while True:
            time.sleep(900)
            try:
                deleted_count = cleanup_unpopular_prompts() 
                if deleted_count > 0:
                    logger.info(f"Background cache cleanup: removed {deleted_count} unpopular prompts")
                else:
                    logger.debug("Background cache cleanup: no unpopular prompts to remove")
            except Exception as e:
                logger.error(f"Background cache cleanup error: {e}")
    
    thread = threading.Thread(target=cleanup_worker, daemon=True)
    thread.start()
    logger.info("Background cache cleanup scheduler started (runs every 15 minutes)")

def get_username_from_token():
    if not request.headers.get('Cookie'):
        return None
        
    cookie_header = request.headers.get('Cookie')
    if not cookie_header or 'auth_token=' not in cookie_header:
        return None
    
    try:
        token_str = cookie_header.split('auth_token=')[1].split(';')[0]
        result, username = verify_token(token_str)
        
        if result:
            return username
        else:
            logger.info(f"Invalid token: {username}")
            return None
            
    except Exception as e:
        logger.error(f"Error processing token: {e}")
        return None

def auth_required_response():
    response = make_response(render_template("auth.html"))
    response.set_cookie('auth_token', '', expires=0)
    return response

### UI-route

@app.route('/', methods=['GET'])
def index():
    username = get_username_from_token()
    if username:
        return render_template("index.html")
    else:
        return auth_required_response()

@app.route("/check", methods=['GET'])    
def check():
    username = get_username_from_token()
    if username:
        return render_template("check.html")
    else:
        return auth_required_response()
        
### API 

@app.route('/webui/v1/registration', methods=['POST'])
def registration():
    json_data = request.json
    
    if json_data.get("password") != json_data.get("confirmpassword"):
        response = {
            "status": "10002",
            "message": "Passwords do not match"
        }
        logger.info(f"Passwords do not match {json_data}")
        return jsonify(response), {'Content-Type': 'application/json; charset=utf-8'}

    try:
        success = insert_user(json_data["username"], json_data["password"])
        logger.info(f'Trying to create user: [{json_data["username"]}] with password: [{json_data["password"]}] /webui/v1/registration')
        if success:
            response = {
                "status": "200",
                "message": f'user with username {json_data["username"]} created'
            }
            logger.info(f"User {json_data['username']} created")
        else:
            logger.error(f'Failed to create user: [{json_data["username"]}] with password: [{json_data["password"]}], user already exist /webui/v1/registration')
            response = {
                "status": "10000",
                "message": f'user with username {json_data["username"]} already exists'
            }

        return jsonify(response), {'Content-Type': 'application/json; charset=utf-8'}

    except sqlite3.Error as e:
        logger.error(f'Problem with database: {e}')
        response = {
            "status": "10001",
            "message": f"Problem with database: {e}"
        }
        return jsonify(response), {'Content-Type': 'application/json; charset=utf-8'}

    except Exception as e:
        logger.error(f'Unexpected error /webui/v1/registration: {e} ')
        response = {
            "status": "500",
            "message": f"Unexpected error: {e}"
        }
        return jsonify(response), {'Content-Type': 'application/json; charset=utf-8'} 


@app.route('/webui/v1/auth', methods=['POST'])
def auth():
    
    if request.method == "GET":
        return render_template("index.html")

    json_data = request.json

    try:
        check_pwd = get_passwd(json_data["username"])

        if not check_pwd or json_data["password"] != check_pwd[0][2]:
            logger.info(f'Wrong username or password for user: {json_data["username"]} with password: {json_data["password"]} /webui/v1/auth')
            response = {
                "status": "401",
                "message": "Wrong username or password"
            }
            return jsonify(response), {'Content-Type': 'application/json; charset=utf-8'}

        user_payload = {
            "user_id": check_pwd[0][0],
            "username": check_pwd[0][1]
        }
        token = generate_jwt_token(user_payload)
        logger.debug(f'Generated JWT token: {token} for user: {json_data["username"]}')

        response = {
            "status": "200",
            "message": "Successful login"
        }
        resp = make_response(jsonify(response))
        resp.headers['Content-Type'] = 'application/json; charset=utf-8'
        resp.set_cookie('auth_token', value=token)
        return resp

    except sqlite3.Error as e:
        logger.error(f'Database error: {e}')
        response = {
            "status": "10003",
            "message": f"Database error: {e}"
        }
        return jsonify(response), {'Content-Type': 'application/json; charset=utf-8'}

    except Exception as e:
        logger.error(f'Unexpected error /webui/v1/auth: {e}')
        response = {
            "status": "500",
            "message": f"Unexpected error: {e}"
        }
        return jsonify(response), {'Content-Type': 'application/json; charset=utf-8'}    


@app.route('/webui/v1/vibeaura', methods=['POST'])
def userRequest():
    username = get_username_from_token()
    if not username:
        return auth_required_response()
    
    json_data = request.json
    user_prompt = json_data["taskDescription"]
    
    cached_result = get_cached_prompt(user_prompt)
    if cached_result:
        logger.info(f"Processing cached request from {username}")
    
    uuid_id = str(uuid.uuid4())
    insert_task(uuid_id, json_data["taskName"], json_data["taskDescription"], username)
    
    request_to_ids = {
        "taskName": json_data["taskName"],
        "taskDescription": json_data["taskDescription"],
        "cached": bool(cached_result)
    }
    
    if cached_result:
        request_to_ids.update({
            "python_code": cached_result['python_code'],
            "dockerfile_code": cached_result['dockerfile_code'],
            "html_code" : cached_result['html_code'],
            "image_name": cached_result['image_name']
        })
    
    try:
        resp = requests.post("http://integration-deployer-service:8992/integration/v1/generate", 
                        json=request_to_ids, timeout=(5, 50))
        resp.raise_for_status()
        data = resp.json()
        logger.info(f"Response from IDS {data}")
        
        if not cached_result and data.get("should_cache", False):
            python_code = data.get("python_code", "")
            dockerfile_code = data.get("dockerfile_code", "") 
            html_code = data.get("html_code", "")
            meta = data.get("meta", "")
            
            cache_prompt_response(user_prompt, data["python_code"], data["dockerfile_code"], data["html_code"], data.get("meta", ""))
            logger.info(f"Cached prompt based on integration-deployer recommendation: {user_prompt[:50]}...")
        
        insert_comtainerMap(uuid_id, data["meta"], username)
        data["content"] += "\nYour Task ID: " + uuid_id
        data["task_id"] = uuid_id
        
        return jsonify(data)
    
    except requests.exceptions.ReadTimeout:
        logger.error('IDS timeout')
        return jsonify({"message": "Service timeout. Please try again."}), 504
        
    except requests.exceptions.RequestException as e:
        logger.error(f'IDS error: {e}')
        return jsonify({"message": "Service error. Please try again."}), 500


@app.route('/webui/v1/getData/<task_id>', methods=['GET'])
def getdata(task_id):
    username = get_username_from_token()
    if not username:
        return auth_required_response()
    
    data = get_task_logs_by_task_id(task_id)
    if not data:
        return jsonify({"message": "Data not found"}), 404
    return jsonify(data), 200       
            
    
@app.route('/integration/v1/logs', methods=['POST'])
def getContainerLogs():
    data = request.json    
    required_keys = ["container_name", "stdout", "stderr"]
    if all(key in data for key in required_keys):
        update_task_logs_by_container(
            data["container_name"],
            data["stdout"],
            data["stderr"]
        )
        return jsonify({"message" : data}), 200
    else:
        return jsonify({"message" : "bad request"}), 400
    
    
if __name__ == '__main__':
    generate_keys.generate_keys_in_memory()
    create_table()
    start_cleanup_scheduler()
    app.run(host='0.0.0.0', port=8080)