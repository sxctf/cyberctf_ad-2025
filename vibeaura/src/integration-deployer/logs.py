import logging
import logging.config
import yaml
import os
from pathlib import Path


class OnlyInfoFilter(logging.Filter):
    def filter(self, record):
        return record.levelno == logging.INFO

def setup_logging(
    default_path='logging_config.yml',
    default_level=logging.INFO,
    env_key='LOG_CFG'
):
    path = os.getenv(env_key, default_path)
    if os.path.exists(path):
        with open(path, 'rt') as f:
            config = yaml.safe_load(f)

        log_dir = Path('log')
        log_dir.mkdir(exist_ok=True)
        

        logging.config.dictConfig(config)
    else:
        logging.basicConfig(level=default_level)