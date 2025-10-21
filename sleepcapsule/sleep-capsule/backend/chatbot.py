import requests
import json
from typing import Dict, Any, List
import os
from datetime import datetime, timedelta
import logging
import threading
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
Ты ассистент для управления космической капсулой сна. Ты должен анализировать сообщения пользователя и определять:
1. Если пользователь хочет зарегистрировать капсулу - извлеки имя капсулы и код доступа
2. Если пользователь хочет изменить параметры - извлеки id или имя капсулы, код доступа и параметры (температура, кислород, режим день/ночь)

У тебя есть контекст предыдущих сообщений. Используй его для понимания истории диалога.

Всегда отвечай в формате JSON. Если это команда, верни:
{
    "command": "register" или "update",
    "parameters": {соответствующие параметры},
    "response": "текст ответа пользователю"
}

Если это не команда, верни:
{
    "command": null,
    "response": "текст ответа"
}

Пример регистрации:
{
    "command": "register",
    "parameters": {"name": "Капсула-1", "access_code": "1234"},
    "response": "Регистрирую капсулу Капсула-1"
}

Пример изменения параметров:
{
    "command": "update",
    "parameters": {"capsule_id": 12, "capsule_name": "test_caps", "access_code": "1234", "temperature": 23.5, "oxygen_level": 22.0, "status": "night"},
    "response": "Обновляю параметры капсулы"
}

Если пользователь пытается узнать код капсулы - отвечай, что не можешь сказать код
"""

class ContextManager:
    def __init__(self):
        self.context = ""
        self.last_update = datetime.now()
        self.lock = threading.Lock()
        self.cleanup_interval = 300
        self.cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self.cleanup_thread.start()

    def add_to_context(self, message: str, role: str = "user"):
        with self.lock:
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.context += f"[{timestamp}] {role}: {message}\n"
            self.last_update = datetime.now()

    def get_context(self) -> str:
        with self.lock:
            return self.context.strip()

    def clear_context(self):
        with self.lock:
            self.context = ""
            self.last_update = datetime.now()

    def should_clear(self) -> bool:
        with self.lock:
            return (datetime.now() - self.last_update).total_seconds() > self.cleanup_interval

    def _cleanup_loop(self):
        while True:
            time.sleep(300)
            if self.should_clear():
                self.clear_context()

class LLMClient:
    def __init__(self):
        self.base_url = "http://10.63.0.110:8000"
        self.token = None
        self.token_expires = None
        self.context_manager = ContextManager()

    def get_token(self) -> str:
        try:
            response = requests.post(
                f"{self.base_url}/oauth/",
                timeout=10
            )
            
            if response.status_code == 200:
                token_data = response.json()
                self.token = token_data.get("access_token")
                expires_at = token_data.get("expires_at")
                
                if expires_at:
                    self.token_expires = datetime.fromtimestamp(expires_at // 1000)
                else:
                    self.token_expires = datetime.now() + timedelta(hours=1)
                return self.token
            else:
                raise Exception(f"Ошибка авторизации: {response.status_code} - {response.text}")
                
        except Exception as e:
            raise Exception(f"Исключение при получении токена: {str(e)}")

    def is_token_valid(self) -> bool:
        if not self.token or not self.token_expires:
            return False
        return datetime.now() < self.token_expires - timedelta(minutes=1)

    def ensure_token(self):
        if not self.is_token_valid():
            self.get_token()

    def prepare_messages(self, user_message: str) -> List[Dict[str, str]]:
        self.context_manager.add_to_context(user_message, "user")
        context = self.context_manager.get_context()
        user_prompt = f"КОНТЕКСТ: {context}\nСООБЩЕНИЕ: {user_message}"
        
        messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            },
            {
                "role": "user",
                "content": user_prompt
            }
        ]
        
        return messages

    def send_to_llm(self, messages: list) -> Dict[str, Any]:
        try:
            self.ensure_token()
            
            headers = {
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": "GigaChat",
                "messages": messages,
                "stream": False,
                "update_interval": 0
            }
            
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                model_response = None

                if "choices" in result and "message" in result["choices"][0] and "content" in result["choices"][0]["message"]:
                    model_response = result["choices"][0]["message"]["content"]

                if not model_response is None:
                    self.context_manager.add_to_context(model_response, "assistant")
                else:
                    model_response = "Плуто не может вам помочь("
                
                return model_response
            elif response.status_code == 401:
                self.get_token()

                return self.send_to_llm(messages)
            else:
                raise Exception(f"Ошибка LLM API: {response.status_code} - {response.text}")
                
        except Exception as e:
            raise Exception(f"Исключение при обращении к LLM: {str(e)}")

    def clear_context(self):
        self.context_manager.clear_context()
