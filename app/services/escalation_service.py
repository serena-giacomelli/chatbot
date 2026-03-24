import json
import logging
from typing import Optional
from urllib import request


logger = logging.getLogger(__name__)


ESCALATION_KEYWORDS = {
    "asesor",
    "humano",
    "agente",
    "persona",
    "representante",
    "llamar",
    "reclamo",
}


def should_escalate(user_text: str, model_answer: Optional[str], faq_score: float) -> bool:
    normalized = (user_text or "").lower()
    if any(keyword in normalized for keyword in ESCALATION_KEYWORDS):
        return True

    if faq_score < 0.20 and not model_answer:
        return True

    if model_answer:
        low_confidence_markers = [
            "no tengo informacion",
            "no cuento con informacion",
            "no puedo confirmar",
            "te recomiendo contactar",
        ]
        if any(marker in model_answer.lower() for marker in low_confidence_markers):
            return True

    return False


def notify_human(webhook_url: str, phone: str, user_text: str) -> None:
    if not webhook_url:
        return

    payload = json.dumps(
        {
            "event": "escalation_requested",
            "phone": phone,
            "message": user_text,
        }
    ).encode("utf-8")

    req = request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=5) as response:
            logger.info("Notificacion de escalamiento enviada. status=%s", response.status)
    except Exception as exc:
        logger.exception("Fallo notificando escalamiento humano: %s", exc)
