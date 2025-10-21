import os
import time
import requests
import yaml
import logging
from logs import *


setup_logging()
logger = logging.getLogger("integration")

path = "integration_config.yml"

if os.path.exists(path):
        with open(path, 'rt') as f:
            config = yaml.safe_load(f)

_token_cache = {
    "access_token": None,
    "expires_at": 0
}

def get_token(force_refresh=False):
        
    global _token_cache

    if not force_refresh and _token_cache["access_token"] and _token_cache["expires_at"] > time.time():
        return _token_cache["access_token"]
    
    try:
        headers = {"Content-Type": "application/json"}
        response = requests.post(config["urls"]["oauth"], headers=headers)
        response.raise_for_status()
        data = response.json()

        access_token = data["access_token"]
        expires_at = data.get("expires_at", 3600)

        _token_cache["access_token"] = access_token
        _token_cache["expires_at"] = expires_at - 60

        return access_token

    except requests.RequestException as e:
        logger.error(f"Failed to get token /oauth: {e}")
        raise