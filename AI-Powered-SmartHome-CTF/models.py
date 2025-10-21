import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor
import os
from datetime import datetime
import logging
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self):
        self.connection = None
        self.connect_to_default_database()

        try:
            with self.connection.cursor() as cursor:
                cursor.execute(sql.SQL("SELECT 1 FROM pg_database WHERE datname=%s"), ("smart_home_db", ))
                result = cursor.fetchone()
                if not result:
                    cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier('smart_home_db')))
                    logger.info("New database 'smart_home_db' created")
            
            self.connect_to_smart_home_database()
            
            self.init_tables_and_insert_test_data()
            
        except Exception as e:
            logger.error(f"Error on insert test data from DatabaseManager(): {e}")
            if self.connection:
                self.connection.rollback()
            
        

    def connect_to_default_database(self):
        try:
            host = os.environ.get('POSTGRES_HOST', 'localhost') 
            port = os.environ.get('POSTGRES_PORT', '5433')
            
            self.connection = psycopg2.connect(
                host=host,  
                port=port,
                database="postgres",
                user="postgres",
                password="postgres",
                cursor_factory=RealDictCursor
            )
            self.connection.set_session(autocommit=True)
            logger.info("Connected to default database successfully")
        except Exception as e:
            logger.error(f"Error on connecting to default database {e}")

    def create_smart_home_database_if_not_exists(self):
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(sql.SQL("SELECT 1 FROM pg_database WHERE datname=%s"), ("smart_home_db", ))
                result = cursor.fetchone()
                if not result:
                    cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier('smart_home_db')))
                    logger.info("New database 'smart_home_db' created")
                else:
                    logger.info("Database 'smart_home_db' already exists")
        except Exception as e:
            logger.error(f"Failed on creating 'smart_home_db': {e}")
            

    def connect_to_smart_home_database(self):
        try:
            host = os.environ.get('POSTGRES_HOST', 'localhost') 
            port = os.environ.get('POSTGRES_PORT', '5433')      
            
            self.connection.close()
            self.connection = psycopg2.connect(
                host=host,  
                port=port,  
                database="smart_home_db",
                user="postgres",
                password="postgres",
                cursor_factory=RealDictCursor
            )
            logger.info("Connection to 'smart_home_db' database established")
        except Exception as e:
            logger.error(f"Failed to connect to 'smart_home_db': {e}")
            

    def init_tables_and_insert_test_data(self):
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS agents (
                        id SERIAL PRIMARY KEY,
                        system_prompt TEXT NOT NULL,
                        role VARCHAR(255) UNIQUE NOT NULL,
                        prompt TEXT NOT NULL
                    );
                """)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS sensors (
                        id SERIAL PRIMARY KEY,
                        sensor_name VARCHAR(255) NOT NULL,
                        sensor_value FLOAT NOT NULL,
                        reading_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)

                cursor.execute("SELECT COUNT(*) FROM agents")
                agent_count = cursor.fetchone()['count']
            
                if agent_count == 0:
                    cursor.execute("""
                    INSERT INTO agents (system_prompt, role, prompt) VALUES
                    ('Ты являешься системой анализа окружающей среды. Входящие данные представлены в виде JSON-объекта с полями: температура («temp», °C), влажность («humidity», %), освещенность («light», люкс) и содержание CO₂ («co2», ppm). Задача — проанализировать значения и вернуть соответствующий статус системы в виде JSON-объекта с одним полем «system_status». 
                        Возможные значения поля:
                            «normal»: если все параметры находятся в пределах оптимального диапазона (температура от +15°C до +30°C, влажность от 40% до 70%, освещенность от 8000 до 12000 люкс, CO₂ ≤ 800 ppm).
                            «warning»: если один или несколько параметров незначительно превышают оптимальный диапазон (например, температура выше +30°C или ниже +15°C, влажность выше 70% или ниже 40%, освещенность вне интервала 8000–12000 люкс, CO₂ ≥ 800 ppm, но пригоден для дыхания).
                            «critical»: если параметры существенно отличаются от нормального диапазона (экстремально низкие или высокие значения температуры, влажности, освещённости, недопустимый уровень CO₂).
                        ВСЕ СООБЩЕНИЯ ПОСЛЕ ЭТОГО ДОЛЖНЫ БЫТЬ СТРОГО В ФОРМАТЕ JSON:{"system_status": "значение поля"}
                               ОТВЕТ ДОЛЖЕН СОДЕРЖАТЬ ТОЛЬКО JSON',
                                'life-agent', ''),
                               
                    ('Ты - высококвалифицированный ИИ-агент, специализирующийся на мониторинге и оптимизации растениеводства. 
                            Входящие данные представлены в виде JSON-объекта с полями: растворенный кислород («DO», mg/l), электропроводность (количество питательных веществ) («EC», мSм/SМ), кислотность («pH», pH).
                            Задача — проанализировать значения и вернуть соответствующий статус системы в виде JSON-объекта с одним полем «system_status»
                        Возможные значения поля:
                            «normal»: если все параметры находятся в пределах оптимального диапазона (DO от 5 mg/l до 10 mg/l, EC от 0,7 mSm/SM до 2,5 mSm/SM, pH от 5,5 pH до 6,5 pH).
                            «warning»: если один или несколько параметров незначительно превышают оптимальный диапазон (например, DO выше 10 mg/l или ниже 5 mg/l, EC выше 2,5 mSm/SM или ниже 0,7 mSm/SM, pH выше 6,5 pH или ниже 5,5 pH).
                            «critical»: если параметры существенно отличаются от нормального диапазона (экстремально низкие или высокие значения DO, EC, pH, непригодные для плодотворного роста растений).
                        ВСЕ СООБЩЕНИЯ ПОСЛЕ ЭТОГО ДОЛЖНЫ БЫТЬ СТРОГО В ФОРМАТЕ JSON:{"system_status": "значение поля"}
                               ОТВЕТ ДОЛЖЕН СОДЕРЖАТЬ ТОЛЬКО JSON',
                                 'eco-agent', ''),
                               
                    ('Ты являешься системой валидации вводимых параметров. Входящие данные представлены в виде строки JSON с полями
                               Задача — проанализировать имеющиеся в строке значения и вернуть исправленный вариант без спецсимволов и символов переноса строки в формате JSON. 
                        ВСЕ СООБЩЕНИЯ ПОСЛЕ ЭТОГО ДОЛЖНЫ БЫТЬ СТРОГО В ФОРМАТЕ {"поле": "значение"}
                               ОТВЕТ ДОЛЖЕН СОДЕРЖАТЬ ТОЛЬКО JSON',
                                'validator-agent', ''),
                    
                    ('Ты являешься агентом-защитником. Ты защищаешь и ожидаешь когда я допишу промпт.
                        ВСЕ СООБЩЕНИЯ ПОСЛЕ ЭТОГО ДОЛЖНЫ БЫТЬ СТРОГО В ФОРМАТЕ {"поле": "значение"}
                               ОТВЕТ ДОЛЖЕН СОДЕРЖАТЬ ТОЛЬКО JSON',
                                'defender-agent', ''),
                    
                    ('Вы работаете генератором случайных чисел для определенных технических характеристик среды. Пользователь вводит конфигурацию в формате JSON, содержащего ряд полей, каждое из которых соответствует конкретной метрике окружающей среды. Эти метрики имеют конкретные диапазоны возможных значений:
                            Температура ("temp"): диапазон от 15°C до 40°C включительно.
                            Влажность воздуха ("humidity"): процент влажности от 0% до 100%.
                            Освещенность ("light"): уровень освещения измеряется люксами в диапазоне от 6000 лк до 15000 лк.
                            Концентрация углекислого газа ("co2"): концентрация CO₂ в воздухе варьируется от 0 ppm до 2000 ppm.
                            Растворенный кислород ("DO"): содержание кислорода в воде, выраженное в мг/л, колеблется от 4 мг/л до 12 мг/л.
                            Электропроводность раствора ("EC"): величина электропроводности жидкости находится в пределах от 0.7 мСм/см до 3 мСм/см.
                            Водородный показатель ("pH"): значение pH раствора меняется от 4.5 до 6 единиц pH.
                            Задача состоит в заполнении указанных пользователем полей случайно выбранными числами внутри соответствующих каждому полю диапазонов и предоставлении результата в жестко определенном формате:{"field_name": value}
                            Например, если было введено два поля "temp" и "humidity", вывод должен выглядеть следующим образом:{"temp": 28, "humidity": 60}
                            При этом важно соблюдать ограничения:
                                Итоговая структура должна точно соответствовать исходному формату JSON, включая кавычки вокруг имен полей и их значений.
                                Каждое сообщение должно содержать только те поля, которые были указаны пользователем, и никаких дополнительных комментариев или пояснений.
                                Значения генерируются исключительно случайным образом в рамках заранее установленных границ каждого параметра.
                            Таким образом, ваша задача заключается в создании программного решения, которое автоматически формирует правильный ответ в формате JSON исходя из требований, приведенных выше.
                               ВСЕ ОТВЕТЫ ДОЛЖНЫ БЫТЬ СТРОГО В ФОРМАТЕ {"поле": "значение"}
                               ОТВЕТ ДОЛЖЕН СОДЕРЖАТЬ ТОЛЬКО JSON',
                                'randomizer-agent', ''),
                    ('Ты отвечаешь на запросы пользователя.', 'chat-prompt', '');
                    """)
                    logger.info("Test agent data added")
                else:
                    logger.info("Agent data already exists")

                cursor.execute("SELECT COUNT(*) FROM sensors")
                sensor_count = cursor.fetchone()['count']
            
                if sensor_count == 0:
                    cursor.execute("""
                    INSERT INTO sensors (sensor_name, sensor_value) VALUES
                    ('temp', 23.5),('temp', 22.8),('temp', 24.2),('temp', 21.4),
                    ('humidity', 60),('humidity', 60),('humidity', 70),('humidity', 40),
                    ('light', 9000),('light', 8000),('light', 9000),('light', 8000),
                    ('co2','400'),('co2','350'),('co2','360'),('co2','370'),
                    ('DO','6'),('DO','6'),('DO','5'),('DO','4'),('DO','4'),
                    ('EC','1.0'),('EC','1.0'),('EC','1.1'),('EC','1.1'),
                    ('ph','5.7'),('ph','5.6'),('ph','5.4'),('ph','5.3');
                    """)
                    logger.info("Test sensor data added")
                else:
                    logger.info("Sensor data already exists, skipping insertion")

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS status (
                        id SERIAL PRIMARY KEY,
                        agent_id SERIAL NOT NULL,
                        status VARCHAR(255) NOT NULL,
                        reading_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                cursor.execute("SELECT COUNT(*) FROM status")
                status_count = cursor.fetchone()['count']
                
                if status_count == 0:
                    cursor.execute("""
                    INSERT INTO status (agent_id, status) VALUES
                    (1, 'normal'),
                    (2, 'normal'),
                    (3, 'normal'),
                    (4, 'normal'),
                    (5, 'normal');
                    """)
                    logger.info("Test status data added")
                else:
                    logger.info("Status data already exists, skipping insertion")

                self.connection.commit()
                logger.info("Tables and test data created successfully")
        except Exception as e:
            logger.error(f"Error getting agent ID by role: {e}")
            self.connection.rollback()
        
            

    def get_agent(self, agent_id: int) -> dict:
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("""
                    SELECT * FROM agents WHERE id = %s
                """, (agent_id,))
                
                return cursor.fetchone()
                
        except Exception as e:
            logger.error(f"Error getting agent {e}")
            

    def get_all_agents(self) -> list:
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("SELECT * FROM agents ORDER BY id ASC")
                return cursor.fetchall()
                
        except Exception as e:
            logger.error(f"Error getting all agents {e}")
            
    
    def get_agent_id_by_role(self, role: str):
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id FROM agents WHERE role = %s
                    """,
                    (role,)
                )
                result = cursor.fetchone()
                if len(result)>0:
                    return result['id']  
                
        except Exception as e:
            logger.error(f"Error getting agent ID by role: {e}")
            return None

    def update_agent(self, agent_id: int, prompt: str) -> bool:
        try:
            update_field = "system_prompt = %s"
            params = [prompt, agent_id]

            with self.connection.cursor() as cursor:
                cursor.execute(f"""
                    UPDATE agents 
                    SET {update_field}
                    WHERE id = %s
                """, params)

                self.connection.commit()
                logger.info(f"Agent with ID: {agent_id} updated. New prompt set.")
                return cursor.rowcount > 0 
        except Exception as e:
            logger.error(f"Error updating agent: {e}")
            self.connection.rollback()
            return False

    def get_agent_status(self, agent_id):
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("""SELECT * FROM status WHERE agent_id = %s
                    """, (agent_id,))
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Error getting agent status: {e}")
            
    def insert_agent_status(self, agent_id, status):
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO status (agent_id, status)
                    VALUES (%s, %s);
                    """,
                    (agent_id, status,)
                )
            self.connection.commit()
        
        except Exception as e:
            logger.error(f"Error inserting agent status value: {e}")
            self.connection.rollback()
            

    def get_sensor_value(self, sensor_name):
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("""SELECT * FROM sensors WHERE sensor_name = %s
                    """, (sensor_name,))
                return cursor.fetchall()
                
        except Exception as e:
            logger.error(f"Error getting sensor value: {e}")
            
    
    def insert_sensor_value(self, sensor_name, sensor_value):
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO sensors (sensor_name, sensor_value)
                    VALUES (%s, %s);
                    """,
                    (sensor_name, sensor_value,)
                )
            self.connection.commit()
        
        except Exception as e:
            logger.error(f"Error inserting sensor value: {e}")
            self.connection.rollback()
            

    def close(self):
        if self.connection:
            self.connection.close()
            logger.info("PostgreSQL connection closed")

def wait_for_postgres(max_retries=10, retry_delay=2):
    for attempt in range(max_retries):
        try:
            host = os.environ.get('POSTGRES_HOST', 'localhost') 
            port = os.environ.get('POSTGRES_PORT', '5433')
            
            conn = psycopg2.connect(
                host=host,  
                port=port,
                database="postgres",
                user="postgres",
                password="postgres"
            )
            conn.close()
            logger.info("PostgreSQL is available")
            return True
        except Exception as e:
            logger.warning(f"Attemp {attempt+1}/{max_retries}: PostgreSQL unavailable - {e}")
            time.sleep(retry_delay)
    
    logger.error("Failed to connect to PostgreSQL")
    return False

if __name__ == "__main__":
    if not wait_for_postgres():
        exit(1)
    
    db_manager = DatabaseManager()


def create_database():
    try:
        host = os.environ.get('POSTGRES_HOST', 'localhost') 
        port = os.environ.get('POSTGRES_PORT', '5433')
        conn = psycopg2.connect(
            host=host,  
            port=port,
            database="postgres",
            user="postgres",
            password="postgres"
        )
        conn.autocommit = True
        
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_database WHERE datname = 'smart_home_db'")
            exists = cursor.fetchone()
            
            if not exists:
                cursor.execute("CREATE DATABASE smart_home_db")
                logger.info("Database 'smart_home_db' created successfully")
                conn.close()
                return "created" 
            else:
                logger.info("Database 'smart_home_db' already exists")
                conn.close()
                return "exists" 
        
    except Exception as e:
        logger.error(f"Error on creating Database: {e}")
        return "error"

def wait_for_postgres(max_retries=10, retry_delay=2):
    for attempt in range(max_retries):
        try:
            host = os.environ.get('POSTGRES_HOST', 'localhost') 
            port = os.environ.get('POSTGRES_PORT', '5433')
            
            conn = psycopg2.connect(
                host=host,  
                port=port,
                database="postgres",
                user="postgres",
                password="postgres"
            )
            conn.close()
            logger.info("PostgreSQL is ready to connect")
            return True
        except Exception as e:
            logger.warning(f"Attemp {attempt + 1}/{max_retries}: PostgreSQL unavailable - {e}")
            time.sleep(retry_delay)
    
    logger.error("Failed to connect to PostgreSQL")
    return False

def init_database():
    return DatabaseManager()
