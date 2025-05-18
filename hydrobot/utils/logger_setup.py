# hydrobot/utils/logger_setup.py

import logging
import logging.handlers
import os
import sys
# --- FIX: Use relative import ---
from ..config.settings import get_config # Use the helper function

# --- Configuration ---
try:
    CONFIG = get_config()
    # Make sure CONFIG is not None before accessing attributes
    if CONFIG is None:
        raise ValueError("Configuration object is None")
    LOG_LEVEL = CONFIG.log_level.upper() # Get log level from config
    LOG_DIR = CONFIG.paths.log_dir         # Get log directory from config
    APP_NAME = CONFIG.app_name.lower().replace(" ", "_") # Use app name for log file
    LOG_FILENAME = os.path.join(LOG_DIR, f"{APP_NAME}.log")
except Exception as e:
    # Fallback if config loading fails during setup
    logging.basicConfig(level=logging.WARNING) # Basic config as fallback
    logging.warning(f"Could not load config for logger setup: {e}. Using basic logging.")
    LOG_LEVEL = "INFO"
    LOG_DIR = "logs"
    APP_NAME = "hydrobot"
    LOG_FILENAME = os.path.join(LOG_DIR, f"{APP_NAME}_fallback.log")
    # Try creating fallback log dir
    try:
        os.makedirs(LOG_DIR, exist_ok=True) # Ensure fallback log dir exists
    except OSError as dir_e:
         logging.error(f"Could not create fallback log directory '{LOG_DIR}': {dir_e}")


# --- Global Logger Instance ---
logger = logging.getLogger(APP_NAME)
logger.setLevel(LOG_LEVEL)

if not logger.handlers:
    log_format = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(LOG_LEVEL)
    console_handler.setFormatter(log_format)
    logger.addHandler(console_handler)
    try:
        file_handler = logging.handlers.TimedRotatingFileHandler(
            LOG_FILENAME, when='midnight', interval=1, backupCount=7, encoding='utf-8'
        )
        file_handler.setLevel(LOG_LEVEL)
        file_handler.setFormatter(log_format)
        logger.addHandler(file_handler)
        logger.info(f"File logging configured to: {LOG_FILENAME}")
    except Exception as e:
        logger.exception(f"Failed to configure file logging to {LOG_FILENAME}: {e}")
    logger.info(f"Logger '{APP_NAME}' initialized with level {LOG_LEVEL}.")
    logger.info(f"Log directory: {os.path.abspath(LOG_DIR)}")
else:
    logger.debug("Logger already initialized.")

def get_logger(name: str = APP_NAME) -> logging.Logger:
    """Returns the configured logger instance."""
    return logging.getLogger(name)