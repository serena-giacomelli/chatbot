import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    app_env: str = os.getenv("APP_ENV", "dev")
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))
    db_path: str = os.getenv("DB_PATH", "chatbot.db")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    twilio_auth_token: str = os.getenv("TWILIO_AUTH_TOKEN", "")
    twilio_account_sid: str = os.getenv("TWILIO_ACCOUNT_SID", "")
    twilio_whatsapp_from: str = os.getenv("TWILIO_WHATSAPP_FROM", "")
    public_whatsapp_number: str = os.getenv("PUBLIC_WHATSAPP_NUMBER", "")
    enable_twilio_signature_validation: bool = (
        os.getenv("ENABLE_TWILIO_SIGNATURE_VALIDATION", "false").lower() == "true"
    )
    admin_api_key: str = os.getenv("ADMIN_API_KEY", "")

    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

    faq_match_threshold: float = float(os.getenv("FAQ_MATCH_THRESHOLD", "0.78"))
    faq_min_similarity_for_gemini: float = float(
        os.getenv("FAQ_MIN_SIMILARITY_FOR_GEMINI", "0.35")
    )

    human_notification_webhook: str = os.getenv("HUMAN_NOTIFICATION_WEBHOOK", "")
    company_name: str = os.getenv("COMPANY_NAME", "Tu Empresa")


settings = Settings()
