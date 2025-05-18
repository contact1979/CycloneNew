# hydrobot/utils/logger_setup.py

import logging
import logging.handlers
import os
import sys

# --- Configuration using environment variables or defaults ---
LOG_LEVEL = os.environ.get("HYDROBOT_LOG_LEVEL", "INFO").upper()
LOG_DIR = os.environ.get("HYDROBOT_LOG_DIR", "logs")
APP_NAME = os.environ.get("HYDROBOT_APP_NAME", "hydrobot").lower().replace(" ", "_")
LOG_FILENAME = os.path.join(LOG_DIR, f"{APP_NAME}.log")

# Create log directory if it doesn't exist
try:
    os.makedirs(LOG_DIR, exist_ok=True)
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
    # Dynamically import settings to avoid circular dependency
    # Only use settings for app_name override if explicitly requested
    if name == APP_NAME:
        try:
            from ..config.settings import settings
            if settings and hasattr(settings, 'app_name'):
                return logging.getLogger(settings.app_name)
        except (ImportError, AttributeError):
            # If settings import fails, just use the default name
            pass
    return logging.getLogger(name)
