import json
import os
from difflib import SequenceMatcher
from typing import Optional, Tuple


FAQ_FILE = os.getenv("FAQ_FILE", "data/faq.json")


class FAQService:
    def __init__(self, faq_file: str = FAQ_FILE) -> None:
        self.faq_file = faq_file
        self.items = self._load()

    def _load(self) -> list[dict]:
        if not os.path.exists(self.faq_file):
            return []
        with open(self.faq_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            return []

    @staticmethod
    def _normalize(text: str) -> str:
        return " ".join((text or "").lower().strip().split())

    def best_match(self, user_text: str) -> Tuple[Optional[str], float]:
        normalized_user_text = self._normalize(user_text)
        if not normalized_user_text:
            return None, 0.0

        best_answer = None
        best_score = 0.0
        for item in self.items:
            question = self._normalize(item.get("question", ""))
            answer = item.get("answer", "")
            if not question or not answer:
                continue

            score = SequenceMatcher(None, normalized_user_text, question).ratio()
            if score > best_score:
                best_score = score
                best_answer = answer

        return best_answer, best_score

    def build_menu(self, max_items: int = 9) -> str:
        if not self.items:
            return "Todavia no tengo preguntas frecuentes cargadas."

        lines = ["Estas son las consultas mas frecuentes. Responde con el numero:"]
        for index, item in enumerate(self.items[:max_items], start=1):
            question = str(item.get("question", "")).strip()
            if question:
                lines.append(f"{index}. {question}")

        lines.append("Tambien puedes escribir tu consulta directamente.")
        return "\n".join(lines)

    def answer_by_number(self, selection: int) -> Optional[str]:
        if selection < 1 or selection > len(self.items):
            return None

        answer = self.items[selection - 1].get("answer", "")
        if not answer:
            return None
        return str(answer)
