from flask import Flask, render_template, request, jsonify, flash, redirect, url_for, abort, render_template_string
import logging
import threading, requests, os, random, time
import json, secrets, hashlib
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import create_engine, inspect
from jinja2 import Template
import pandas as pd
from datetime import datetime
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from requests.exceptions import ConnectTimeout
import concurrent.futures
from threading import Lock, RLock
import atexit


app = Flask(__name__)
def get_user_identifier():
    if current_user.is_authenticated:
        return str(current_user.id)
    return get_remote_address()

limiter = Limiter(key_func=get_user_identifier, app=app)

class ThreadSafeGlobals:
    def __init__(self):
        self._validation_enabled = False
        self._bearer_token = ''
        self._lock = RLock() 
        
    @property
    def VALIDATION_ENABLED(self):
        with self._lock:
            return self._validation_enabled
    
    @VALIDATION_ENABLED.setter
    def VALIDATION_ENABLED(self, value):
        with self._lock:
            self._validation_enabled = value
            
    @property
    def BEARER_TOKEN(self):
        with self._lock:
            return self._bearer_token
    
    @BEARER_TOKEN.setter
    def BEARER_TOKEN(self, value):
        with self._lock:
            self._bearer_token = value
            
    def update_bearer_token(self, value):
        with self._lock:
            self._bearer_token = value
            logging.info(f"BEARER_TOKEN updated to: {value[:10]}...") 

GLOBALS = ThreadSafeGlobals()
GIGACHAT_URL = f"http://10.63.0.110:8000/oauth/"
THREAD_POOL = concurrent.futures.ThreadPoolExecutor(max_workers=5)
model_chat_lock = Lock()

app.config['JSON_AS_ASCII'] = False
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///db/db.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['POSTGRES_HOST'] = os.environ.get('POSTGRES_HOST', 'localhost')
app.config['POSTGRES_PORT'] = os.environ.get('POSTGRES_PORT', '5433')

global HOST, PORT
HOST = app.config['POSTGRES_HOST']
PORT = app.config['POSTGRES_PORT']

logging.basicConfig(level=logging.DEBUG,filename='./logs/app.log', format='{"time": "%(asctime)s", "level": "%(levelname)s", "message": "%(message)s"}', datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)

def get_bearer_token_async():
    def token_task():
        attemps = 0
        current_token = GLOBALS.BEARER_TOKEN
        
        while (not current_token and attemps < 3):
            response = requests.Response()
            try:
                logger.info(f"Trying {attemps} attempt to get BEARER Token")
                response = requests.post(GIGACHAT_URL, timeout=10)
                
                if response.status_code == 200:
                    new_token = response.json().get('access_token')
                    GLOBALS.update_bearer_token(new_token)
                    logger.info("Successfully obtained BEARER token")
                    break
            except Exception as e:
                logger.error(f"Error decoding json: {e}, Args: {e.args}. response = {response.text}")
            finally:
                 attemps = attemps + 1
            current_token = GLOBALS.BEARER_TOKEN
        
        if GLOBALS.BEARER_TOKEN:
            logger.info("BEARER token obtained successfully in background thread")
        else:
            logger.warning("Failed to obtain BEARER token in background thread")
    
    token_thread = threading.Thread(target=token_task, daemon=True)
    token_thread.start()
    logger.info("BEARER token acquisition started in background thread")
    return token_thread

def check_token_status():
    if GLOBALS.BEARER_TOKEN:
        return "Token available"
    else:
        return "Token not available, retrying in background"

def refresh_bearer_token():
    GLOBALS.update_bearer_token('')
    logger.info("Forcing BEARER token refresh")
    return get_bearer_token_async()

token_thread = get_bearer_token_async()

sqlitedb = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def run_periodically(interval):
    def wrapper(func):
        def wrapped_func(*args, **kwargs):
            try:
                func(*args, **kwargs)
                logger.info(f"Func {func.__name__} finished")
            except Exception as e:
                logger.error(f"Error in periodic func {func.__name__}: {e}")
            
            timer = threading.Timer(interval, wrapped_func, args=args, kwargs=kwargs)
            timer.daemon = True
            timer.start()
            logger.info(f"Next start for periodic func {func.__name__} after {interval} sec")
        return wrapped_func
    return wrapper


@app.route('/')
def index():
    data = get_index_data()
    return render_template('index.html', **data)
    
def get_index_data():
    db = DatabaseManager()

    values = [item['sensor_value'] for item in db.get_sensor_value("temp")]
    tempData = values[-5:]

    values = [item['sensor_value'] for item in db.get_sensor_value("light")]
    lightData = values[-5:]

    values = [item['sensor_value'] for item in db.get_sensor_value("co2")]
    coData = values[-5:]

    values = [item['sensor_value'] for item in db.get_sensor_value("humidity")]
    humidityData = values[-5:]

    values = [item['sensor_value'] for item in db.get_sensor_value("DO")]
    doData = values[-5:]

    values = [item['sensor_value'] for item in db.get_sensor_value("EC")]
    ecData = values[-5:]

    values = [item['sensor_value'] for item in db.get_sensor_value("ph")]
    phData = values[-5:]

    life_agent_statuses = db.get_agent_status(1)
    eco_agent_statuses = db.get_agent_status(2)
    validator_agent_statuses = db.get_agent_status(3)
    defender_agent_statuses = db.get_agent_status(4)
    randomizer_agent_statuses = db.get_agent_status(5)
    
    statuses = {
        'life-agent':  life_agent_statuses[-1]['status'],
        'eco-agent': eco_agent_statuses[-1]['status'],
        'validator-agent':  validator_agent_statuses[-1]['status'],
        'defender-agent': defender_agent_statuses[-1]['status'],
        'randomizer-agent': randomizer_agent_statuses[-1]['status']
    }
    
    residents_status = get_residents_status()

    return {
        'tempData': tempData,
        'lightData': lightData,
        'coData': coData,
        'humidityData': humidityData,
        'doData': doData,
        'ecData': ecData,
        'phData': phData,
        'statuses': statuses,
        'residents_status': residents_status
    }

def get_residents_status():
    db = DatabaseManager()
    residents = Residents.get_all_residents()
    
    life_agent_status = db.get_agent_status(1) 
    eco_agent_status = db.get_agent_status(2)  

    life_status = life_agent_status[-1]['status'] if life_agent_status else 'unknown'
    eco_status = eco_agent_status[-1]['status'] if eco_agent_status else 'unknown'
    
    residents_with_status = []
    
    for resident in residents:
        if resident.type in ['civilian', 'repairman', 'military']:
            status = life_status
            status_class = get_status_class(life_status)
            emoji = get_resident_emoji(resident.type, life_status)
        elif resident.type == 'plant':
            status = eco_status
            status_class = get_status_class(eco_status)
            emoji = get_resident_emoji(resident.type, eco_status)
        else:
            status = 'unknown'
            status_class = 'unknown'
            emoji = '❓'
        
        residents_with_status.append({
            'name': resident.name,
            'type': resident.type,
            'room': resident.room,
            'status': status,
            'status_class': status_class,
            'emoji': emoji
        })
    
    return residents_with_status

def get_status_class(status):
    status_map = {
        'normal': 'good',
        'warning': 'warning', 
        'critical': 'danger',
        'unknown': 'unknown'
    }
    return status_map.get(status.lower(), 'unknown')

def get_resident_emoji(resident_type, status):
    if resident_type in ['civilian', 'repairman', 'military']:
        if status == 'normal':
            return '😃'
        elif status == 'warning':
            return '😟'
        elif status == 'critical':
            return '🥵'
        else:
            return '😐'
    elif resident_type == 'plant':
        if status == 'normal':
            return '🌱'
        elif status == 'warning':
            return '🌿'
        elif status == 'critical':
            return '🍂'
        else:
            return '🎍'
    else:
        return '❓'

@app.route('/account', methods=['GET', 'POST'])
@login_required
def account():
    user = current_user
    cookie = request.cookies['session']
    
    chat_history = ChatHistory.get_user_chat_history(user.id, limit=20)
    
    formatted_history = []
    for chat in chat_history:
        formatted_history.append({
            'role': 'user' if chat.message_type == 'ai_chat' else 'user',
            'content': chat.message if chat.message_type == 'ai_chat' else f"Запрос к БД: {chat.message}",
            'timestamp': chat.timestamp
        })
        formatted_history.append({
            'role': 'assistant',
            'content': chat.response,
            'timestamp': chat.timestamp
        })
    
    return render_template('account.html', 
                         user=user, 
                         cookie=cookie,
                         chat_history=formatted_history,
                         now=datetime.now())

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):

            login_user(user)
            flash('Sign-in success!', 'success', )
            data = get_index_data()
            logger.info(f'Sign-in success to user: {username}')
            return render_template('index.html', **data)
        else:
            flash('Wrong login or password', 'danger')
            logger.warning(f'Wrong password for user: {username}:{password}')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        existing_user = User.query.filter_by(username=username).first()
        
        if existing_user:
            flash('Login is already in use', 'danger')
            logger.warning(f'Login is already in use: {username}')
        else:
            new_user = User(username=username, role='user')
            new_user.set_password(password)
            sqlitedb.session.add(new_user)
            sqlitedb.session.commit()
            flash('Sign-up success!', 'success')
            logger.warning(f'Sign up success: {username}')
            return render_template('login.html')
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Success logout', 'info')
    data = get_index_data()
    return render_template('index.html', **data)

@app.route('/agents')
def agents():
    data = get_agents_data()
    return render_template('agents.html', **data)

def get_agents_data():
    db = DatabaseManager()
    agents = db.get_all_agents()
    life_agent_statuses = db.get_agent_status(1)
    eco_agent_statuses = db.get_agent_status(2)
    validator_agent_statuses = db.get_agent_status(3)
    defender_agent_statuses = db.get_agent_status(4)
    randomizer_agent_statuses = db.get_agent_status(5)

    changes = Changes.get_changes()


    validate_requests = Settings.get_setting('validate_requests')
    gigachat_url = Settings.get_setting('gigachat_url')
    bearer_token = Settings.get_setting('bearer_token')
    
    GLOBALS.VALIDATION_ENABLED = bool(validate_requests)
    GIGACHAT_URL = gigachat_url
    GLOBALS.BEARER_TOKEN = bearer_token

    if validate_requests == True or str(validate_requests) == '1':
        validate_requests = '"1" checked'
    else:
        validate_requests = '0'

    return {
        'life_agent_prompt': agents[0]['system_prompt'],
        'life_agent_logs': life_agent_statuses[-1]['status'],
        'eco_agent_prompt': agents[1]['system_prompt'],
        'eco_agent_logs': eco_agent_statuses[-1]['status'],
        'validator_agent_prompt': agents[2]['system_prompt'],
        'validator_agent_logs': validator_agent_statuses[-1]['status'],
        'defender_agent_prompt': agents[3]['system_prompt'],
        'defender_agent_logs': defender_agent_statuses[-1]['status'],
        'randomizer_agent_prompt': agents[4]['system_prompt'],
        'randomizer_agent_logs': randomizer_agent_statuses[-1]['status'],
        'chat_prompt':agents[5]['system_prompt'],
        'validate_requests': validate_requests,
        'gigachat_url': gigachat_url,
        'bearer_token': bearer_token,
        'changes': changes
    }

@app.route('/validate_prompt', methods=['POST'])
@login_required
def validate_prompt():
    if request.method == 'POST':
        db = DatabaseManager()
        agents = db.get_all_agents()

        life_prompt = request.form.get('life-prompt', '').strip()
        eco_prompt = request.form.get('eco-prompt', '').strip()
        validator_prompt = request.form.get('validator-prompt', '').strip()
        randomizer_prompt = request.form.get('randomizer-prompt', '').strip()
        chat_prompt = request.form.get('chat-prompt', '').strip()

        prompt_text = ""
        old_text = ""
        agent_name = ""

        if life_prompt and life_prompt != agents[0]['system_prompt']:
            prompt_text = life_prompt
            old_text = agents[0]['system_prompt']
            agent_name = "life-agent"

        elif eco_prompt and eco_prompt != agents[1]['system_prompt']:
            prompt_text = eco_prompt
            old_text = agents[1]['system_prompt']
            agent_name = "eco-agent"

        elif validator_prompt and validator_prompt != agents[2]['system_prompt']:
            prompt_text = validator_prompt
            old_text = agents[2]['system_prompt']
            agent_name = "validator-agent"

        elif randomizer_prompt and randomizer_prompt != agents[4]['system_prompt']:
            prompt_text = randomizer_prompt
            old_text = agents[4]['system_prompt']
            agent_name = "randomizer-agent"

        elif chat_prompt and chat_prompt != agents[5]['system_prompt']:
            prompt_text = chat_prompt
            old_text = agents[5]['system_prompt']
            agent_name = "chat-prompt"

        if not prompt_text:
            flash("No changes detected")
            logger.info(f'No changes in prompts for user: {current_user.id}')
        else:
            Changes.save_changes(agent_name=agent_name, old_text=old_text, new_text=prompt_text, validated=0, user_id=current_user.id)
            flash('Prompt sent for validation!')
            logger.info(f'Prompt sent to validation: agent={agent_name}, old_text={old_text}, new_text={prompt_text}, user_id={current_user.id}')
        
        data = get_agents_data()
        return render_template('agents.html', **data)
    return '', 400

@app.route('/validate/<int:change_id>', methods=['POST'])
def validate_change(change_id):
    change = Changes.query.get_or_404(change_id)
    change.validated = not change.validated  
    
    if current_user.id == change.user_id:
        flash('Validation by another user is required')
        logger.warning(f'Attemp to validate by the same user: {current_user.id}')
        data = get_agents_data()
        return render_template('agents.html', **data)

    db = DatabaseManager()
    agent_id = db.get_agent_id_by_role(change.agent_name)
    agent = db.update_agent(agent_id, change.new_text)
    new_text = change.new_text
    if agent:
        sqlitedb.session.delete(change)
        sqlitedb.session.commit()
        flash('The change was successfully validated!' if change.validated else 'Change cancelled.')
        logger.info(f"change successfully validated by user: {current_user}, для agent_id: {agent_id}, new text: {new_text}")
    data = get_agents_data()
    return render_template('agents.html', **data)

@app.route('/residents', methods=['GET'])
def residents():
    residents = Residents.get_all_residents()    
    return render_template('residents.html', 
                         residents=residents, 
                         current_user=current_user)

@app.route('/add_resident', methods=['POST'])
def add_resident():
    name = request.form['name']
    resident_type = request.form['type']
    room = request.form['room']
    voucher = request.form['voucher']
    
    resident = Residents.save_resident(name = name, resident_type = resident_type, room = room, voucher = voucher)
    logger.info(f'New resident: {name} Room: {room} Type: {resident_type}')
    flash(f"New resident: {resident.voucher}")

    residents = Residents.get_all_residents()  
    return render_template('residents.html',current_user = current_user, residents = residents)

@app.route('/resident/<int:resident_id>')
def resident_details(resident_id):
    resident = Residents.query.get_or_404(resident_id)
    voucher = ""
    if current_user.role != 'admin':
        resident.voucher = "Only admins can get voucher"
    template_code = f"""
        <h2>Resident Details</h2>
        <div class="resident-info">
            <div><strong>Name:</strong> {resident.name}</div>
            <div><strong>Type:</strong> {resident.type}</div>
            <div><strong>Room:</strong> {resident.room}</div>
            <div><strong>Voucher:</strong> {resident.voucher}</div>
        </div>
        """
    return render_template_string(template_code)

def get_resident_status(resident_type, temperature):
    if resident_type == 'plant':
        if temperature > 30:
            return 'danger', 'Dehydration'
        elif temperature > 28:
            return 'warning', 'Hot'
        else:
            return 'normal', 'Normal'
    else:  
        if temperature > 30:
            return 'danger', 'Danger'
        elif temperature > 28:
            return 'warning', 'Hot'
        elif temperature < 20:
            return 'warning', 'Cold'
        else:
            return 'normal', 'Normal'

@app.route('/save_settings', methods=['POST'])
def save_settings():
    GLOBALS.VALIDATION_ENABLED = bool(request.form.get('validate_requests'))
    gigachat_url = request.form.get('gigachat_url').strip()
    bearer_token = request.form.get('bearer_token').strip()
    GIGACHAT_URL = gigachat_url
    
    Settings.save_setting('validate_requests', GLOBALS.VALIDATION_ENABLED)
    Settings.save_setting('gigachat_url', gigachat_url)
    Settings.save_setting('bearer_token', bearer_token)

    flash('Settings saved', 'success')
    logger.info(f'Save settings: validation = {GLOBALS.VALIDATION_ENABLED}, gigachat_url = {gigachat_url}, bearer_token = {bearer_token}')
    
    data = get_agents_data()
    return render_template('agents.html', **data)

@app.route('/chat', methods=['POST'])
@limiter.limit("10 per minute", key_func=get_user_identifier)
def chat():
    data = request.json
    user_query = data.get('message')
    
    logger.info(f"New message in chat with user: { current_user.id}, message: {user_query}")
    if not user_query:
        return jsonify({'response': 'No message provided'}), 400
    
    try:
        def is_database_related(query):
            query_lower = query.lower()
            
            db_keywords = [
                'select', 'insert', 'update', 'delete', 'create', 'alter', 'drop',
                'показать', 'вывести', 'найти', 'поиск', 'сколько', 'статистик',
                'список', 'перечень', 'отчет', 'анализ', 'данные', 'информация',
                'количество', 'сумма', 'среднее', 'максимум', 'минимум',
                'пользовател', 'юзер', 'user', 'агент', 'agent', 'сенсор', 'sensor',
                'резидент', 'resident', 'настройк', 'setting', 'изменен', 'change',
                'флаг', 'flag', 'логи', 'log', 'статус', 'status', 'база', 'таблиц'
            ]
            
            return any(keyword in query_lower for keyword in db_keywords)
        
        user_id = current_user.id if current_user.is_authenticated else None
        response_text = ""
        message_type = "ai_chat"
        
        if is_database_related(user_query) and user_id:
            try:
                db_result = natural_language_to_sql(user_query)
                
                if not any(error in db_result.lower() for error in ['ошибка', 'error', 'не найдены']):
                    response_text = f"📊 Результат из базы данных:\n{db_result}"
                    message_type = "db_query"
                else:
                    regular_response = model_chat(user_query, 6)
                    response_data = json.loads(regular_response)
                    response_text = response_data['choices'][0]['message']['content']
                    message_type = "ai_chat"
                    
            except Exception as db_error:
                logger.warning(f"Database query failed, falling back to regular chat: {db_error}")
                regular_response = model_chat(user_query, 6)
                response_data = json.loads(regular_response)
                response_text = response_data['choices'][0]['message']['content']
                message_type = "ai_chat"
        else:
            future = model_chat_async(user_query, 6)
            try:
                regular_response = future.result(timeout=10)  
                if regular_response:
                    response_data = json.loads(regular_response)
                    response_text = response_data['choices'][0]['message']['content']
                else:
                    response_text = "Извините, произошла ошибка при обработке запроса"
            except concurrent.futures.TimeoutError:
                response_text = "Извините, время обработки запроса истекло. Попробуйте позже."
                logger.warning(f"Chat request timeout for user: {user_id}")
            except Exception as e:
                response_text = "Извините, произошла ошибка при обработке запроса"
                logger.error(f"Error in async chat processing: {e}")
            
            message_type = "ai_chat"
        
        if user_id:
            ChatHistory.save_chat_message(
                user_id=user_id,
                message=user_query,
                response=response_text,
                message_type=message_type
            )
        
        return jsonify({'response': response_text})
    
    except Exception as e:
        logger.error(f'Chat processing error: {e}')
        return jsonify({'response': f'Ошибка обработки запроса: {str(e)}'}), 500
    
def model_chat(prompt,agent_id):
        current_token = GLOBALS.BEARER_TOKEN
        # 1 - life-agent 
        # 2 - eco-agent
        # 3 - validator-agent
        # 4 - defender-agent
        # 5 - randomizer-agent
        Settings.save_setting('bearer_token', current_token)

        db_man = DatabaseManager()
        if agent_id == "":
            agent = db_man.get_agent(agent_id=6)
        else:
            agent = db_man.get_agent(agent_id)
        
        
        system_prompt = agent['system_prompt']
        role = agent['role']
        
        headers = {'Authorization': f'Bearer {current_token}'}
        payload = {
            "model": "GigaChat",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 500,
            "stream": False,
            "update_interval": 0
        }

        try:
            import time
            max_wait_time = 60  
            start_time = time.time()
            retry_delay = 10
            
            while time.time() - start_time < max_wait_time:
                response = requests.post('http://10.63.0.110:8000/chat/completions', headers=headers, json=payload, timeout=30)
                
                if response.status_code == 200:    
                    logger.info(f"Role: {role}, System prompt: {system_prompt}, User prompt: {prompt}, Response: {response.text}")    
                    return response.text
                if response.status_code == 401:
                    logger.info("Trying to update BEARER Token")
                    response = requests.post(GIGACHAT_URL,timeout=30)
                    new_token = response.json().get('access_token')
                    GLOBALS.update_bearer_token(new_token)
                    Settings.save_setting('bearer_token', new_token)
                    response = requests.post('http://10.63.0.110:8000/chat/completions', headers=headers, json=payload, timeout=30)
                    logger.info(f"Role: {role}, System prompt: {system_prompt}, User prompt: {prompt}, Response: {response.text}")
                    return response.text
                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', retry_delay))
                    logger.warning(f"Rate limit exceeded, retrying in {retry_after}s...")
                    time.sleep(retry_after)
                    continue
                if response.status_code == 503:
                    logger.warning(f"Service unavailable (503), retrying in {retry_delay}s...")
                    time.sleep(retry_delay)
                    retry_delay = min(retry_delay * 1.5, 60)
                    continue  
                else:
                    logger.warning(f"GigaChat returned status {response.status_code}, retrying in {retry_delay}s...")
                    time.sleep(retry_delay)
                    retry_delay = min(retry_delay * 1.5, 60) 
            
                logger.error(f"GigaChat unavailable after {max_wait_time} seconds")
                return None
    
        except requests.exceptions.Timeout:
            logger.error("GigaChat request timeout")
            return None
        except requests.exceptions.ConnectionError:
            logger.error("GigaChat connection error")
            return None
        except Exception as e:
            logger.error(f"Error connecting to GigaChat: {e}")
            return None

def model_chat_async(prompt, agent_id, callback=None):
    def task():
        try:
            result = model_chat(prompt, agent_id)
            if callback:
                callback(result)
            return result
        except Exception as e:
            logger.error(f"Error in async model_chat: {e}")
            if callback:
                callback(None)
            return None
    
    future = THREAD_POOL.submit(task)
    return future

@run_periodically(300)
def my_function():
    current_token = GLOBALS.BEARER_TOKEN
    global HOST 
    global PORT

    app.config['POSTGRES_HOST'] = HOST
    app.config['POSTGRES_PORT'] = PORT
    logger.info("Updating agents parameters")
    with app.app_context():
        db = DatabaseManager()
            
        content_data = ""
        #randomizer-agent - 5
        try:
            future = model_chat_async('{"temp":"","humidity":"", "light": "", "co2": "", "DO": "","EC": "", "ph": ""}', 5)
            out = future.result(timeout=30)  
            logger.info(f"Randomizer-agent response: {out}")
            if out == None:
                raise Exception("Error on get output from Gigachat")
            else:
                 db.insert_agent_status(5,"normal")
        except Exception as e:
            logger.error(f"Error get output from Gigachat: {out}, {e}")
            raise
        try:
            required_vars = ["temp", "humidity", "light", "co2", "DO", "EC", "ph", "choices", "message", "content"]
            missing_variables = []
            for var in required_vars:
                if var not in out:
                    missing_variables.append(var)

            if len(missing_variables) > 0:
                logger.warning(f"Missing variables in response from randomizer-agent: {', '.join(missing_variables)}")

            parsed_out = json.loads(out)
            first_choice = parsed_out['choices'][0]
            content_str = first_choice['message']['content']
            content_data = json.loads(content_str)
        except json.JSONDecodeError as e:  
            logger.error(f"Error on parsing json from randomizer-agent: {e}, {e.doc}")
            if GLOBALS.VALIDATION_ENABLED:
                future = model_chat_async(out, 3)
                coreccted_out = future.result(timeout=30)
                logger.info(f"Validated response from randomizer-agent: {out}")
                parsed_out = json.loads(coreccted_out)
                first_choice = parsed_out['choices'][0]
                content_str = first_choice['message']['content']
                content_data = json.loads(content_str)
        except Exception as e:   
            logger.error(f"Error on parsing response from randomizer-agent: {e} out = {out}")
        
        attr_dict = {}
        try:
            for attr in content_data.items():
                logger.info(f"Sensor data - {attr[0]}:{attr[1]}")
                attr_dict[attr[0]] = str(attr[1])
                db.insert_sensor_value(attr[0],attr[1])
        except Exception as e:        
                logger.error(f"Error on input to db sensor parameters from randomizer-agent: {e}")
                db.insert_agent_status(5,"critical")
    
        out_prompt = ""
        #life-agent - 1
        try:
            out_prompt = f'{{"temp": {attr_dict["temp"]}, "humidity": {attr_dict["humidity"]}, "light": {attr_dict["light"]}, "co2": {attr_dict["co2"]}}}'
        except Exception as e:  
            logger.error(f"Error on decoding response with sensors parameters from Life-agent: {e}")

        future = model_chat_async(out_prompt, 1)
        
        try:
            life_agent_out = future.result(timeout=30)
            logger.info(f"Life-agent response: {life_agent_out}")
            required_vars = ["message", "content", "system_status"]
            missing_variables = []
            for var in required_vars:
                if var not in life_agent_out:
                    missing_variables.append(var)

            if len(missing_variables) > 0:
                logger.warning(f"Missing variables in response from life-agent: {', '.join(missing_variables)}")
        except Exception as e:
            logger.error(f"Error on parsing response from Life-agent: {e}")
            
        try:
            parsed_out = json.loads(life_agent_out)
            first_choice = parsed_out['choices'][0]
            content_str = first_choice['message']['content']
            content_data = json.loads(content_str)
        except json.JSONDecodeError as e:  
            logger.error(f"Error on parsing output from life-agent:  {e}, {e.doc}")
            if GLOBALS.VALIDATION_ENABLED:
                coreccted_out = model_chat(parsed_out,3)
                logger.info(f"Validated response from life-agent: {out}")
                parsed_out = json.loads(coreccted_out)
                first_choice = parsed_out['choices'][0]
                content_str = first_choice['message']['content']
                content_data = json.loads(content_str)
        except Exception as e:
            logger.error(f"Error on getting output from life-agent: {e}")

        attr_life_dict = {}
        try:
            for attr in content_data.items():
                logger.info(f"Life-agent status - {attr[0]}:{attr[1]}")
                attr_life_dict[attr[0]] = str(attr[1])
                db.insert_agent_status(1,attr_life_dict["system_status"])
        except Exception as e:        
                logger.error(f"Error on gettint output from life-agent: {e}")
                db.insert_agent_status(1,"Critical")

        #eco-agent - 2
        try:
            out_prompt = f'{{"DO": {attr_dict["DO"]}, "EC": {attr_dict["EC"]}, "ph": {attr_dict["ph"]}}}'
        except Exception as e: 
            logger.error(f"Error on parsing response with sensor parameters from Eco-agent: {e}")
        
        future = model_chat_async(out_prompt, 2)
        try:
            eco_agent_out = future.result(timeout=30)
            logger.info(f"Eco-agent response: {eco_agent_out}")
            parsed_out = json.loads(eco_agent_out)
            first_choice = parsed_out['choices'][0]
            content_str = first_choice['message']['content']
            content_data = json.loads(content_str)
        except json.JSONDecodeError as e:  
            logger.error(f"Error on parsing output from eco-agent: {e}, {e.doc}")
            if GLOBALS.VALIDATION_ENABLED:
                coreccted_out = model_chat(parsed_out,3)
                logger.info(f"Validated output from Eco-agent: {out}")
                parsed_out = json.loads(coreccted_out)
                first_choice = parsed_out['choices'][0]
                content_str = first_choice['message']['content']
                content_data = json.loads(content_str)
        except Exception as e:
            logger.error(f"Error on parsing output from eco-agent: {e}")

        attr_eco_dict = {}
        try:
            for attr in content_data.items():
                logger.info(f"Eco-agent status - {attr[0]}:{attr[1]}")
                attr_eco_dict[attr[0]] = str(attr[1])
                db.insert_agent_status(2,attr_eco_dict["system_status"])
        except Exception as e:        
                logger.error(f"Error on getting output from eco-agent: {e}")
                db.insert_agent_status(2,"Critical")

def agent_validator(input,trigger):
    validated_output = ""
    return validated_output

def get_database_schema():
    engine = create_engine('sqlite:///db/db.db')
    inspector = inspect(engine)    
    schema_info = "Схема базы данных:\n"
    
    tables = inspector.get_table_names()
    
    for table in tables:
        schema_info += f"\nТаблица: {table}\n"
        columns = inspector.get_columns(table)
        for column in columns:
            schema_info += f"  - {column['name']} ({column['type']})"
            if column.get('primary_key'):
                schema_info += " PRIMARY KEY"
            if column.get('nullable') is False:
                schema_info += " NOT NULL"
            schema_info += "\n"
        
        foreign_keys = inspector.get_foreign_keys(table)
        if foreign_keys:
            schema_info += "  Внешние ключи:\n"
            for fk in foreign_keys:
                schema_info += f"    - {fk['constrained_columns']} -> {fk['referred_table']}.{fk['referred_columns']}\n"
    
    return schema_info

def execute_sql_query(sql_query):
    engine = create_engine('sqlite:///db/db.db')
    
    try:
        with engine.connect() as conn:
            if sql_query.strip().upper().startswith('SELECT'):
                result = conn.execute(str(sql_query))
                df = pd.DataFrame(result.fetchall(), columns=result.keys())
                return df.to_string(index=False)
            else:
                result = conn.execute(str(sql_query))
                conn.commit()
                return f"Запрос выполнен успешно. Затронуто строк: {result.rowcount}"
                
    except Exception as e:
        return f"Ошибка выполнения запроса: {str(e)}"
    
def natural_language_to_sql(user_query, agent_id=5):
    schema_info = get_database_schema()
    
    prompt = f"""
        {schema_info}

        Преобразуй следующий запрос на естественном языке в ОДИН корректный SQL запрос.

        Пользовательский запрос: "{user_query}"

        ВАЖНЫЕ ИНСТРУКЦИИ:
        1. Верни ТОЛЬКО ОДИН SQL запрос без каких-либо объяснений
        2. НЕ используй несколько SQL запросов в ответе
        3. Используй только существующие таблицы и колонки из схемы
        4. Для запросов на чтение используй SELECT
        5. Если запрос требует данных, которых нет в схеме, верни сообщение: "ERROR: Данные не найдены в схеме БД"

        SQL запрос:
        """
    
    response = model_chat(prompt, agent_id)
    
    try:
        response_data = json.loads(response)
        sql_query = response_data['choices'][0]['message']['content'].strip()
        
        if sql_query.startswith('"') and sql_query.endswith('"'):
            sql_query = sql_query[1:-1]
        if sql_query.startswith("'") and sql_query.endswith("'"):
            sql_query = sql_query[1:-1]
        
        if sql_query.startswith("ERROR:"):
            return sql_query
        
        queries = [q.strip() for q in sql_query.split(';') if q.strip()]
        
        if len(queries) > 1:
            logger.warning(f"Получено несколько запросов, выполняем первый: {queries[0]}")
            sql_query = queries[0]
        else:
            sql_query = queries[0] if queries else sql_query
        
        result = execute_sql_query(sql_query)
        return result
        
    except Exception as e:
        logger.error(f"Error processing query: {e}")
        return f"Ошибка при обработке запроса: {str(e)}"

def execute_sql_query(sql_query):
    engine = create_engine('sqlite:///db/db.db')
    
    try:
        with engine.connect() as conn:
            if sql_query.strip().upper().startswith('SELECT'):
                result = conn.execute(str(sql_query))
                df = pd.DataFrame(result.fetchall(), columns=result.keys())
                if df.empty:
                    return "Данные не найдены"
                return df.to_string(index=False)
            else:
                with conn.begin() as transaction:
                    result = conn.execute(str(sql_query))
                    return f"Запрос выполнен успешно. Затронуто строк: {result.rowcount}"
                
    except Exception as e:
        return f"Ошибка выполнения запроса: {str(e)}"

def start_periodic_tasks():
    try:
        periodic_thread = threading.Thread(target=my_function, daemon=True)
        periodic_thread.start()
        logger.info("Periodic tasks started successfully in background thread")
    except Exception as e:
        logger.error(f"Error starting periodic tasks: {e}")



@atexit.register
def shutdown_thread_pool():
    THREAD_POOL.shutdown(wait=False)
    logger.info("Thread pool shutdown")

if __name__ == '__main__':
    from models import DatabaseManager
    from connector import *
    with app.app_context():
        sqlitedb.create_all()
        try:
                if not User.query.filter_by(username='admin1').first():
                    admin1 = User(username='admin1', role='admin')
                    admin1.set_password('admin123')
                    sqlitedb.session.add(admin1)
                    logger.info("User 'admin1' added to sqlite.")
                else:
                    logger.info("User 'admin1' already exists")

                if not User.query.filter_by(username='admin2').first():
                    admin2 = User(username='admin2', role='admin')
                    admin2.set_password('admin123')
                    sqlitedb.session.add(admin2)
                    logger.info("User 'admin2' added to sqlite.")
                else:
                    logger.info("User 'admin2' already exists")

                sqlitedb.session.commit()

        except Exception as e:
            logger.error(f"Error on creating user 'admin' in sqlite: {e}")
        try:
            GLOBALS.VALIDATION_ENABLED = True
            Settings.save_setting('validate_requests', GLOBALS.VALIDATION_ENABLED)
        except Exception as e:
            logger.error(f"Error in adding validate_requests in sqlite: {e}")
        
        my_function()

        background_thread = threading.Thread(target=start_periodic_tasks, daemon=True)
        background_thread.start()
        logger.info("Background thread for periodic tasks started")

    app.run(host='0.0.0.0', port=5500, debug=True)