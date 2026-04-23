"""
Logger Configuration Module
Provides unified logging management with output to both console and file.
Supports opt-in structured JSON output via AGORA_LOG_FORMAT=json.
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler


def _ensure_utf8_stdout():
    """
    Ensure stdout/stderr use UTF-8 encoding
    Solves Windows console Chinese character encoding issue
    """
    if sys.platform == 'win32':
        # Reconfigure standard output to UTF-8 on Windows
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')


# Log directory
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'logs')

# Read log format once at module import time; can be overridden in tests via env.
_LOG_FORMAT = os.getenv('AGORA_LOG_FORMAT', 'text').lower()


class JSONFormatter(logging.Formatter):
    """
    Structured JSON formatter for opt-in machine-readable log output.

    Each log record becomes a single-line JSON object with mandatory fields:
        timestamp, level, logger, message, module, function, line

    Optional fields (only included when present):
        simulation_id  — from LogRecord.simulation_id (pass via extra={})
        request_id     — from LogRecord.request_id    (pass via extra={})
        exception      — formatted traceback string when exc_info is set
    """

    MANDATORY_FIELDS = frozenset({
        'timestamp', 'level', 'logger', 'message', 'module', 'function', 'line',
    })

    def format(self, record: logging.LogRecord) -> str:
        # ISO-8601 UTC timestamp
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()

        payload: dict = {
            'timestamp': ts,
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }

        # Optional contextual fields
        sim_id = getattr(record, 'simulation_id', None)
        if sim_id is not None:
            payload['simulation_id'] = sim_id

        req_id = getattr(record, 'request_id', None)
        if req_id is not None:
            payload['request_id'] = req_id

        # Exception info
        if record.exc_info:
            payload['exception'] = self.formatException(record.exc_info)
        elif record.exc_text:
            payload['exception'] = record.exc_text

        return json.dumps(payload, ensure_ascii=False, default=str)


def _make_formatter(use_json: bool, detailed: bool = True) -> logging.Formatter:
    """Return the appropriate formatter instance."""
    if use_json:
        return JSONFormatter()
    if detailed:
        return logging.Formatter(
            '[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    return logging.Formatter(
        '[%(asctime)s] %(levelname)s: %(message)s',
        datefmt='%H:%M:%S'
    )


def setup_logger(name: str = 'agora', level: int = logging.DEBUG) -> logging.Logger:
    """
    Setup logger

    Args:
        name: Logger name
        level: Log level

    Returns:
        Configured logger
    """
    use_json = _LOG_FORMAT == 'json'

    # Ensure log directory exists
    os.makedirs(LOG_DIR, exist_ok=True)

    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Prevent logs from propagating to root logger to avoid duplicate output
    logger.propagate = False

    # If handlers already exist, don't add duplicates
    if logger.handlers:
        return logger

    # 1. File handler - detailed logs (named by date, with rotation)
    log_filename = datetime.now().strftime('%Y-%m-%d') + '.log'
    file_handler = RotatingFileHandler(
        os.path.join(LOG_DIR, log_filename),
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(_make_formatter(use_json, detailed=True))

    # 2. Console handler - concise logs (INFO and above)
    # Ensure UTF-8 encoding on Windows to avoid Chinese character issues
    _ensure_utf8_stdout()
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    # In JSON mode use the same formatter; in text mode use the simple variant.
    console_handler.setFormatter(_make_formatter(use_json, detailed=False))

    # Add handlers
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


def get_logger(name: str = 'agora') -> logging.Logger:
    """
    Get logger (create if not exists)

    Args:
        name: Logger name

    Returns:
        Logger instance
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        return setup_logger(name)
    return logger


# Create default logger
logger = setup_logger()


# Convenience functions
def debug(msg, *args, **kwargs):
    logger.debug(msg, *args, **kwargs)

def info(msg, *args, **kwargs):
    logger.info(msg, *args, **kwargs)

def warning(msg, *args, **kwargs):
    logger.warning(msg, *args, **kwargs)

def error(msg, *args, **kwargs):
    logger.error(msg, *args, **kwargs)

def critical(msg, *args, **kwargs):
    logger.critical(msg, *args, **kwargs)
