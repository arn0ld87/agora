"""
Logger Configuration Module
Provides unified logging management with output to both console and file.
Supports opt-in structured JSON output via AGORA_LOG_FORMAT=json.

Includes a default :class:`RedactionFilter` that scrubs tokens, tickets,
bearer credentials, API keys and passwords from formatted messages before
they hit any handler. Active on every Agora logger and on the werkzeug
access logger (P2: Logging-Review auf Secret-Redaction und Token-Schutz).
"""

import json
import logging
import os
import re
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


REDACTED = "***"

# Patterns sind absichtlich konservativ: lieber einmal zu viel maskieren als
# einmal ein Token im Log stehen lassen. Reihenfolge ist relevant — spezifische
# Patterns vor generischen.
_REDACTION_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # Authorization: Bearer <token>
    (re.compile(r"(?i)(bearer\s+)([A-Za-z0-9\-._~+/=]{6,})"), r"\1" + REDACTED),
    # Header X-Agora-Token: <value>
    (
        re.compile(r"(?i)(x[-_]agora[-_]token['\"\s:=]+)([A-Za-z0-9\-._~+/=]{4,})"),
        r"\1" + REDACTED,
    ),
    # Query- oder Form-Parameter: token=, ticket=, api_key=, password=, secret=
    (
        re.compile(
            r"(?i)\b(token|ticket|api[_-]?key|access[_-]?key|secret(?:[_-]?key)?|password|passwd|pwd)"
            r"(\s*[=:]\s*)"
            r"([^\s,&;'\"<>]{3,})"
        ),
        r"\1\2" + REDACTED,
    ),
    # JSON-Style "password": "value"
    (
        re.compile(
            r"(?i)([\"'](?:token|ticket|api[_-]?key|access[_-]?key|secret(?:[_-]?key)?|password|passwd|pwd)[\"']\s*:\s*[\"'])"
            r"([^\"']+)"
            r"([\"'])"
        ),
        r"\1" + REDACTED + r"\3",
    ),
    # Env-Style LLM_API_KEY=foo
    (
        re.compile(
            r"(?i)\b([A-Z][A-Z0-9_]*(?:API_KEY|TOKEN|SECRET|PASSWORD|PASSWD))"
            r"(\s*[=:]\s*)"
            r"([^\s,;'\"]+)"
        ),
        r"\1\2" + REDACTED,
    ),
)


def _scrub(text: str) -> str:
    if not text or not isinstance(text, str):
        return text
    out = text
    for pattern, replacement in _REDACTION_PATTERNS:
        out = pattern.sub(replacement, out)
    return out


class RedactionFilter(logging.Filter):
    """Maskiert bekannte Secret-Muster im finalen Log-Output.

    Greift nach :meth:`logging.LogRecord.getMessage`, weil wir auch ``%s``-
    interpolierte Argumente und ``f``-Strings abdecken müssen. Das Original-
    Record wird *nicht* mutiert, sondern eine vorgerenderte Message in
    ``record.msg`` mit leeren ``args`` gesetzt — alle Formatter darunter
    sehen damit den maskierten Text.

    Why: SSE/Download-Endpoints akzeptieren weiterhin ``?token=`` als
    Deprecation-Pfad, und Werkzeugs Access-Log enthält die volle Request-Line
    inklusive Query-String. Ohne Filter würden Bearer-Tokens und ablaufende
    Tickets im Klartext in ``backend/logs/*.log`` landen.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            rendered = record.getMessage()
        except Exception:  # noqa: BLE001 — Logging darf niemals werfen
            return True
        scrubbed = _scrub(rendered)
        if scrubbed != rendered:
            record.msg = scrubbed
            record.args = ()
        # exc_text wird vom Formatter on-demand gerendert; falls schon
        # gesetzt, ebenfalls scrubben.
        if record.exc_text:
            record.exc_text = _scrub(record.exc_text)
        return True


_REDACTION_FILTER = RedactionFilter()


def install_redaction_filter(logger: logging.Logger) -> None:
    """Hängt den Redaction-Filter idempotent an Logger und alle Handler.

    Zusätzlich zu Loggern selbst werden Filter auf die Handler gesetzt, damit
    auch Subloggern, die ihre Records nach oben propagieren, die Maskierung
    nicht entgeht.
    """
    if _REDACTION_FILTER not in logger.filters:
        logger.addFilter(_REDACTION_FILTER)
    for handler in logger.handlers:
        if _REDACTION_FILTER not in handler.filters:
            handler.addFilter(_REDACTION_FILTER)


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

    # Secret-Redaction auf Logger + Handler. Ohne diesen Filter würden
    # ?token=, ?ticket=, Bearer-Tokens und API-Keys im Klartext in
    # backend/logs landen.
    install_redaction_filter(logger)

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
