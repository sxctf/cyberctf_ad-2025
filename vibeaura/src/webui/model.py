import sqlite3, os.path, uuid, hashlib
from logs import *
from datetime import datetime, timedelta
import time

setup_logging()
logger = logging.getLogger("db_logs")

def create_table():
    if os.path.exists('./data.db'):
        return "Database exist"
    else:
        # Create table
        try:
            
            # Users 
            sqliteConnection = sqlite3.connect('./data.db')
            sqlite_create_table_query = '''CREATE TABLE IF NOT EXISTS users (
                                            id INTEGER PRIMARY KEY,
                                            username VARCHAR(255) NOT NULL UNIQUE,
                                            password VARCHAR(255) NOT NULL
                                            );'''
            cursor = sqliteConnection.cursor()
            logger.debug('Successfully Connected to SQLite')
            cursor.execute(sqlite_create_table_query)
            sqliteConnection.commit()
            logger.debug('SQLite table users created')
            
            # vibetask 
            sqlite_create_table_query = '''CREATE TABLE IF NOT EXISTS vibetask (
                                            id VARCHAR(255) PRIMARY KEY,
                                            name VARCHAR(255) NOT NULL,
                                            task VARCHAR(255) NOT NULL,
                                            std_out VARCHAR(255) NOT NULL DEFAULT '',
                                            std_err VARCHAR(255) NOT NULL DEFAULT '',
                                            task_owner VARCHAR(255) NOT NULL
                                            );'''
            cursor = sqliteConnection.cursor()
            logger.debug('Successfully Connected to SQLite')
            cursor.execute(sqlite_create_table_query)
            sqliteConnection.commit()
            logger.debug('SQLite table vibetask created')
            
            # container map
            sqlite_create_table_query = '''CREATE TABLE IF NOT EXISTS containter_map (
                                            id VARCHAR(255) PRIMARY KEY,
                                            container_name VARCHAR(255) NOT NULL,
                                            task_owner VARCHAR(255) NOT NULL
                                            );'''
            cursor = sqliteConnection.cursor()
            logger.debug('Successfully Connected to SQLite')
            cursor.execute(sqlite_create_table_query)
            sqliteConnection.commit()
            logger.debug('SQLite table container_map created')
            
            # prompt_cache
            sqlite_create_table_query = '''CREATE TABLE IF NOT EXISTS prompt_cache (
                                            prompt_hash TEXT PRIMARY KEY,
                                            user_prompt TEXT NOT NULL,
                                            python_code TEXT NOT NULL,
                                            dockerfile_code TEXT NOT NULL,
                                            html_code TEXT NOT NULL,
                                            image_name TEXT NOT NULL,
                                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                            last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                            use_count INTEGER DEFAULT 1
                                            );'''
            cursor = sqliteConnection.cursor()
            cursor.execute(sqlite_create_table_query)
            sqliteConnection.commit()
            logger.debug('SQLite table prompt_cache created')
            
        except sqlite3.Error as error:
            logger.error(f'Error while creating a sqlite table {error}')
        finally:
            if sqliteConnection:
                sqliteConnection.close()
                logger.debug('sqlite connection is closed')


def _calculate_prompt_hash(user_prompt: str) -> str:
   
    return hashlib.md5(user_prompt.encode()).hexdigest()

def get_cached_prompt(user_prompt: str):
    
    prompt_hash = _calculate_prompt_hash(user_prompt)
    
    try:
        sqliteConnection = sqlite3.connect('./data.db')
        sqliteConnection.row_factory = sqlite3.Row
        cursor = sqliteConnection.cursor()
        
        cursor.execute('''
            SELECT * FROM prompt_cache 
            WHERE prompt_hash = ?
        ''', (prompt_hash,))
        
        result = cursor.fetchone()
        
        if result:
            
            cursor.execute('''
                UPDATE prompt_cache 
                SET last_used = CURRENT_TIMESTAMP, use_count = use_count + 1
                WHERE prompt_hash = ?
            ''', (prompt_hash,))
            sqliteConnection.commit()
            
            logger.info(f"Using cached prompt (used {result['use_count'] + 1} times)")
            
            return {
                'python_code': result['python_code'],
                'dockerfile_code': result['dockerfile_code'],
                'html_code': result['html_code'],
                'image_name': result['image_name'],
                'prompt_hash': result['prompt_hash'],
                'use_count': result['use_count'] + 1
            }
        
        return None
        
    except sqlite3.Error as error:
        logger.error(f'Error while getting cached prompt: {error}')
        return None
    finally:
        if sqliteConnection:
            sqliteConnection.close()

def cache_prompt_response(user_prompt: str, python_code: str, dockerfile_code: str, html_code: str,image_name: str):
    
    prompt_hash = _calculate_prompt_hash(user_prompt)
    
    try:
        sqliteConnection = sqlite3.connect('./data.db')
        cursor = sqliteConnection.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO prompt_cache 
            (prompt_hash, user_prompt, python_code, dockerfile_code, html_code, image_name)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (prompt_hash, user_prompt, python_code, dockerfile_code, html_code, image_name))
        
        sqliteConnection.commit()
        logger.info(f"Prompt cached successfully (hash: {prompt_hash[:8]}...)")
        
    except sqlite3.Error as error:
        logger.error(f'Error while caching prompt: {error}')
    finally:
        if sqliteConnection:
            sqliteConnection.close()

def _get_ttl_minutes(use_count: int) -> int:
   
    if use_count <= 3:
        return 15    
    elif use_count <= 10:
        return 45    
    else:
        return 90

def cleanup_unpopular_prompts():

    try:
        sqliteConnection = sqlite3.connect('./data.db')
        cursor = sqliteConnection.cursor()
        
        
        cursor.execute('''
            SELECT prompt_hash, use_count, last_used 
            FROM prompt_cache
        ''')
        
        all_records = cursor.fetchall()
        deleted_count = 0
        
        for record in all_records:
            prompt_hash = record[0]
            use_count = record[1]
            last_used = record[2]
            
            
            ttl_minutes = _get_ttl_minutes(use_count)
            
            
            cursor.execute('''
                SELECT COUNT(*) FROM prompt_cache 
                WHERE prompt_hash = ? 
                AND last_used < datetime('now', ?)
            ''', (prompt_hash, f'-{ttl_minutes} minutes'))
            
            should_delete = cursor.fetchone()[0] > 0
            
            if should_delete:
                cursor.execute('DELETE FROM prompt_cache WHERE prompt_hash = ?', (prompt_hash,))
                deleted_count += 1
                logger.debug(f"Deleted prompt (used {use_count} times, TTL: {ttl_minutes}min)")
        
        sqliteConnection.commit()
        
        if deleted_count > 0:
            logger.info(f"Smart cleanup: removed {deleted_count} expired prompts")
        else:
            logger.debug("Smart cleanup: no expired prompts to remove")
            
        return deleted_count
        
    except sqlite3.Error as error:
        logger.error(f'Error while cleaning up prompts: {error}')
        return 0
    finally:
        if sqliteConnection:
            sqliteConnection.close()

def get_cache_stats():
    
    try:
        sqliteConnection = sqlite3.connect('./data.db')
        cursor = sqliteConnection.cursor()
        
        
        cursor.execute('''
            SELECT 
                COUNT(*) as total_entries,
                SUM(use_count) as total_uses,
                AVG(use_count) as avg_uses,
                MAX(use_count) as max_uses
            FROM prompt_cache
        ''')
        stats = cursor.fetchone()
        
        # TTL groups
        cursor.execute('''
            SELECT 
                COUNT(*) as count,
                AVG(use_count) as avg_uses,
                CASE 
                    WHEN use_count <= 3 THEN '15min'
                    WHEN use_count <= 10 THEN '45min' 
                    ELSE '90min'
                END as ttl_group
            FROM prompt_cache 
            GROUP BY ttl_group
        ''')
        
        ttl_groups = {}
        for row in cursor.fetchall():
            ttl_groups[row[2]] = {
                'count': row[0],
                'avg_uses': round(row[1] or 0, 2)
            }
        
        return {
            'total_entries': stats[0],
            'total_uses': stats[1] or 0,
            'average_uses': round(stats[2] or 0, 2),
            'max_uses': stats[3] or 0,
            'ttl_groups': ttl_groups
        }
        
    except sqlite3.Error as error:
        logger.error(f'Error while getting cache stats: {error}')
        return {}
    finally:
        if sqliteConnection:
            sqliteConnection.close()

def insert_user(username: str, password: str):
    
    try:
        sqliteConnection = sqlite3.connect('./data.db')
        cursor = sqliteConnection.cursor()
        logger.debug('Successfully Connected to SQLite')
        cursor.execute("INSERT INTO users (username, password) VALUES ((?), (?))", (username, password, ) )
        sqliteConnection.commit()
        logger.debug(f'Data successfully inserted {cursor.rowcount}')
        cursor.close()
        return True

    except sqlite3.Error as error:
        logger.error(f'Error while inserting data in users table {error} trying insert username:{username}')
        return False
    finally:
        if sqliteConnection:
            sqliteConnection.close()
            logger.debug('sqlite connection is closed')
            
            
def insert_task(id: str, name: str, task: str, task_owner:str):
    
    try:
            sqliteConnection = sqlite3.connect('./data.db')
            cursor = sqliteConnection.cursor()
            logger.debug('Connected to SQLite')

            insert_query = """
                INSERT INTO vibetask (id, name, task, task_owner)
                VALUES (?, ?, ?, ?)
            """
            cursor.execute(insert_query, (
                id,
                name,
                task,
                task_owner
            ))
            sqliteConnection.commit()
            logger.debug(f"Vibetask '{name}' inserted successfully")
            cursor.close()
            
    except sqlite3.Error as error:
        logger.error(f'Error while inserting data in vibetask table {error} data:{"name: ", name, " task: ", task, " owner: ", task_owner}')
        return False
    finally:
        if sqliteConnection:
            sqliteConnection.close()
            logger.debug('sqlite connection is closed')
        
            
def insert_comtainerMap(id: str, container_name: str, task_owner: str):
    try:
            sqliteConnection = sqlite3.connect('./data.db')
            cursor = sqliteConnection.cursor()
            logger.debug('Connected to SQLite')

            insert_query = """
                INSERT INTO containter_map (id, container_name, task_owner)
                VALUES (?, ?, ?)
            """
            cursor.execute(insert_query, (
                id,
                container_name,
                task_owner
            ))
            sqliteConnection.commit()
            logger.debug(f"ContainerMap '{id}' inserted successfully")
            cursor.close()
            
    except sqlite3.Error as error:
        logger.error(f'Error while inserting data in containerMap table {error} data:{"id: ", id, " container_name: ", container_name, " owner: ", task_owner}')
        return False
    finally:
        if sqliteConnection:
            sqliteConnection.close()
            logger.debug('sqlite connection is closed')


def update_task_logs_by_container(container_name: str, stdout: str, stderr: str):
    try:
        sqliteConnection = sqlite3.connect('./data.db')
        cursor = sqliteConnection.cursor()
        logger.debug(f"Connected to SQLite for updating logs for container {container_name}")

        cursor.execute(
            "SELECT id FROM containter_map WHERE container_name = ?",
            (container_name,)
        )
        result = cursor.fetchone()
        if not result:
            logger.error(f"No task found for container {container_name}")
            return False

        task_id = result[0]

        cursor.execute(
            "UPDATE vibetask SET std_out = std_out  || '\n' || ?, std_err = std_err || '\n' || ? WHERE id = ?",
            (stdout, stderr, task_id)
        )
        sqliteConnection.commit()
        logger.info(f"Logs for task {task_id} appended successfully")
        cursor.close()
        return True

    except sqlite3.Error as error:
        logger.error(f"Error while updating logs for container {container_name}: {error}")
        return False
    finally:
        if sqliteConnection:
            sqliteConnection.close()
            logger.debug("SQLite connection closed")


def get_passwd(username):
    
    try:
        sqliteConnection = sqlite3.connect('./data.db')
        cursor = sqliteConnection.cursor()
        logger.debug('Successfully Connected to SQLite')
        cursor.execute("SELECT * FROM users WHERE username = ?", (username, ))
        records = cursor.fetchall()
        cursor.close()
        
        return records
    
    except sqlite3.Error as error:
        logger.error(f'Error while getting data from users {error} trying get data for username:{username}')
    finally:
        if sqliteConnection:
            sqliteConnection.close()
            logger.debug('sqlite connection is closed')


def get_task_logs_by_task_id(task_id: str):
    try:
        sqliteConnection = sqlite3.connect('./data.db')
        cursor = sqliteConnection.cursor()
        logger.debug(f"Connected to SQLite to fetch data for task_id: {task_id}")

        cursor.execute("""
            SELECT id, name, task, std_out, std_err
            FROM vibetask
            WHERE id = '%s'
        """ % (task_id))
        results = cursor.fetchall()

        if not results:
            return []

        tasks = []
        for result in results:
            task_data = {
                "taskID": result[0],
                "name": result[1],
                "task_description": result[2],
                "stdout": result[3],
                "stderr": result[4]
            }
            tasks.append(task_data)

        return tasks

    except sqlite3.Error as error:
        logger.error(f"Error while fetching task logs for task_id {task_id}: {error}")
        return []

    finally:
        if sqliteConnection:
            sqliteConnection.close()
            logger.debug("SQLite connection closed")