import logging
from typing import Optional

import google.generativeai as genai


logger = logging.getLogger(__name__)


class GeminiService:
    def __init__(self, api_key: str, model_name: str) -> None:
        self.enabled = bool(api_key)
        self.model_name = model_name
        self._model = None

        if self.enabled:
            genai.configure(api_key=api_key)
            self._model = genai.GenerativeModel(model_name=model_name)

    def generate_answer(self, user_text: str, company_name: str) -> Optional[str]:
        if not self.enabled or self._model is None:
            return None

        prompt = (
            "Eres un asistente de atencion al cliente por WhatsApp. "
            "Responde siempre en espanol, de forma breve, clara y amable. "
            "Si no tienes informacion confiable, dilo explicitamente en una frase corta. "
            f"Empresa: {company_name}. "
            f"Pregunta del cliente: {user_text}"
        )

        try:
            response = self._model.generate_content(prompt)
            text = (response.text or "").strip()
            return text or None
        except Exception as exc:
            logger.exception("Gemini fallo al generar respuesta: %s", exc)
            return None
