import re


EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_PATTERN = re.compile(r"\+?\d[\d\s\-()]{7,}\d")
ID_PATTERN = re.compile(r"\b\d{7,12}\b")


def redact_sensitive_data(text: str) -> str:
    if not text:
        return ""

    redacted = EMAIL_PATTERN.sub("[EMAIL_REDACTED]", text)
    redacted = PHONE_PATTERN.sub("[PHONE_REDACTED]", redacted)
    redacted = ID_PATTERN.sub("[ID_REDACTED]", redacted)
    return redacted
