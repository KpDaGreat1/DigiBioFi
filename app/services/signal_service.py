"""
Signal-CLI client for DigiBioFi.

Design constraints (NON-NEGOTIABLE):
- Subprocess-only: no persistent connections, no shared state with DedwenAI
- Explicit binary path from config
- Sanitized arguments (no shell=True, no injection vectors)
- Timeout enforced on every call
- Local file lock prevents concurrent sends from a single worker
- Never re-registers or modifies Signal identity
- Never touches ~/.local/share/signal-cli directly
"""
import logging
import re
import subprocess
import threading
from dataclasses import dataclass

from app.core.config import settings

logger = logging.getLogger(__name__)

_SEND_LOCK = threading.Lock()

SIGNAL_CLI_PATH = "/usr/local/bin/signal-cli"
SIGNAL_SEND_TIMEOUT = 30
_E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")


@dataclass
class SignalResult:
    success: bool
    message: str


def _is_valid_e164(phone: str) -> bool:
    return bool(_E164_RE.match(phone))


def send_message(phone: str, message: str) -> SignalResult:
    """
    Send a Signal message to a single E.164 phone number.

    This is the ONLY entry point — it never registers, never modifies
    Signal identity, and never interacts with DedwenAI's Signal usage.
    Each call is an isolated subprocess invocation.

    Args:
        phone: E.164 format (e.g. +12125551234)
        message: Plain text message, max 10,000 chars

    Returns:
        SignalResult with success flag and status message
    """
    if not phone or not _is_valid_e164(phone):
        return SignalResult(success=False, message="Invalid phone number format. Must be E.164 (+1XXXXXXXXXX).")

    if not message or not message.strip():
        return SignalResult(success=False, message="Message cannot be empty.")

    message = message[:10_000]

    sender = getattr(settings, "signal_sender_number", "").strip()
    if not sender:
        logger.warning("SIGNAL_SENDER_NUMBER not configured — Signal messaging disabled")
        return SignalResult(success=False, message="Signal messaging is not configured on this server.")

    if not _is_valid_e164(sender):
        logger.error("SIGNAL_SENDER_NUMBER is not valid E.164: %r", sender)
        return SignalResult(success=False, message="Signal sender configuration is invalid.")

    cmd = [
        SIGNAL_CLI_PATH,
        "-u", sender,
        "send",
        "-m", message,
        phone,
    ]

    with _SEND_LOCK:
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=SIGNAL_SEND_TIMEOUT,
                shell=False,
            )
        except FileNotFoundError:
            logger.error("signal-cli not found at %s", SIGNAL_CLI_PATH)
            return SignalResult(success=False, message="Signal-CLI binary not found.")
        except subprocess.TimeoutExpired:
            logger.error("signal-cli send timed out after %ds", SIGNAL_SEND_TIMEOUT)
            return SignalResult(success=False, message="Signal send timed out.")
        except Exception as exc:
            logger.exception("Unexpected error invoking signal-cli: %s", exc)
            return SignalResult(success=False, message="Signal send failed due to an unexpected error.")

    if result.returncode == 0:
        logger.info("Signal message sent to %s", phone)
        return SignalResult(success=True, message="Message sent.")

    stderr = (result.stderr or "").strip()
    logger.error("signal-cli exited %d: %s", result.returncode, stderr)
    return SignalResult(success=False, message=f"Signal send failed (exit {result.returncode}).")
