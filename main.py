import logging
import os
from typing import Optional
from urllib.parse import quote_plus

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from twilio.request_validator import RequestValidator

from app.config import settings
from app.services.escalation_service import notify_human, should_escalate
from app.services.faq_service import FAQService
from app.services.gemini_service import GeminiService
from app.services.history_service import HistoryService
from app.services.privacy_service import redact_sensitive_data
from app.services.twilio_service import TwilioOutboundService, to_twiml


load_dotenv()

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger("whatsapp_chatbot")

app = FastAPI(title="WhatsApp AI Chatbot", version="0.1.0")

faq_service = FAQService()
gemini_service = GeminiService(settings.gemini_api_key, settings.gemini_model)
history_service = HistoryService(settings.db_path)
twilio_outbound_service = TwilioOutboundService(
    settings.twilio_account_sid,
    settings.twilio_auth_token,
    settings.twilio_whatsapp_from,
)


class HumanReplyRequest(BaseModel):
    phone: str
    message: str
    close_case: bool = False
    closing_message: Optional[str] = None


ADMIN_PANEL_HTML = """
<!doctype html>
<html lang=\"es\">
<head>
    <meta charset=\"utf-8\">
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
    <title>Panel de Asesores</title>
    <style>
        :root {
            --bg: #f7f9fc;
            --card: #ffffff;
            --text: #1e2a3b;
            --muted: #607089;
            --line: #d9e2ee;
            --primary: #0b63f6;
            --ok: #0d8a47;
            --danger: #c62828;
        }
        * { box-sizing: border-box; }
        body {
            margin: 0;
            font-family: Segoe UI, system-ui, -apple-system, sans-serif;
            background: linear-gradient(180deg, #f3f6fb 0%, #eef3f9 100%);
            color: var(--text);
        }
        .wrap {
            max-width: 1180px;
            margin: 24px auto;
            padding: 0 16px;
        }
        .grid {
            display: grid;
            grid-template-columns: 360px 1fr;
            gap: 16px;
        }
        .card {
            background: var(--card);
            border: 1px solid var(--line);
            border-radius: 14px;
            box-shadow: 0 6px 24px rgba(11, 99, 246, 0.08);
        }
        .card h2 {
            margin: 0;
            padding: 14px 16px;
            border-bottom: 1px solid var(--line);
            font-size: 16px;
        }
        .card .content {
            padding: 14px 16px;
        }
        input, textarea, button {
            width: 100%;
            border-radius: 10px;
            border: 1px solid var(--line);
            font: inherit;
            padding: 10px 12px;
        }
        textarea { min-height: 90px; resize: vertical; }
        button {
            border: none;
            background: var(--primary);
            color: white;
            cursor: pointer;
            font-weight: 600;
        }
        button.secondary {
            background: #dfe8f5;
            color: #22406f;
        }
        .row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
        .stack { display: grid; gap: 10px; }
        .muted { color: var(--muted); font-size: 13px; }
        .queue-item {
            border: 1px solid var(--line);
            border-radius: 10px;
            padding: 10px;
            margin-bottom: 8px;
            cursor: pointer;
        }
        .queue-item:hover { border-color: #b6c8e4; background: #f8fbff; }
        .msg-list {
            border: 1px solid var(--line);
            border-radius: 10px;
            padding: 10px;
            max-height: 380px;
            overflow: auto;
            background: #fbfdff;
        }
        .msg {
            margin-bottom: 10px;
            padding: 10px;
            border-radius: 10px;
            border: 1px solid #e6edf8;
            background: white;
        }
        .msg small { color: var(--muted); display: block; margin-top: 6px; }
        .status { font-weight: 600; }
        .ok { color: var(--ok); }
        .err { color: var(--danger); }
        @media (max-width: 960px) {
            .grid { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body>
    <div class=\"wrap\">
        <div class=\"grid\">
            <section class=\"card\">
                <h2>Bandeja de Escalados</h2>
                <div class=\"content stack\">
                    <input id=\"adminKey\" placeholder=\"X-Admin-Key\" />
                    <button class=\"secondary\" id=\"reloadQueue\">Actualizar bandeja</button>
                    <div id=\"queue\"></div>
                </div>
            </section>

            <section class=\"card\">
                <h2>Respuesta de Asesor</h2>
                <div class=\"content stack\">
                    <div class=\"row\">
                        <input id=\"phone\" placeholder=\"whatsapp:+549...\" />
                        <button class=\"secondary\" id=\"loadConversation\">Ver conversacion</button>
                    </div>
                    <div class=\"msg-list\" id=\"conversation\"></div>
                    <textarea id=\"message\" placeholder=\"Escribe la respuesta del asesor\"></textarea>
                    <label><input type=\"checkbox\" id=\"closeCase\" style=\"width:auto;\" /> Cerrar caso y devolver al bot</label>
                    <input id=\"closingMessage\" placeholder=\"Mensaje final opcional al cerrar\" />
                    <button id=\"sendReply\">Enviar respuesta</button>
                    <div id=\"status\" class=\"status\"></div>
                </div>
            </section>
        </div>
    </div>

    <script>
        const queueEl = document.getElementById('queue');
        const conversationEl = document.getElementById('conversation');
        const statusEl = document.getElementById('status');

        function adminHeaders() {
            const key = document.getElementById('adminKey').value.trim();
            return {
                'Content-Type': 'application/json',
                'X-Admin-Key': key,
            };
        }

        function setStatus(text, ok = true) {
            statusEl.textContent = text;
            statusEl.className = 'status ' + (ok ? 'ok' : 'err');
        }

        async function loadQueue() {
            queueEl.innerHTML = '<div class="muted">Cargando...</div>';
            try {
                const res = await fetch('/admin/human/queue', { headers: adminHeaders() });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || 'Error al cargar bandeja');

                if (!data.items.length) {
                    queueEl.innerHTML = '<div class="muted">No hay casos escalados.</div>';
                    return;
                }

                queueEl.innerHTML = '';
                data.items.forEach((item) => {
                    const div = document.createElement('div');
                    div.className = 'queue-item';
                    div.innerHTML = '<strong>' + item.phone + '</strong><div class="muted">' + (item.last_message || 'Sin mensajes') + '</div>';
                    div.addEventListener('click', () => {
                        document.getElementById('phone').value = item.phone;
                        loadConversation();
                    });
                    queueEl.appendChild(div);
                });
            } catch (err) {
                queueEl.innerHTML = '<div class="err">' + err.message + '</div>';
            }
        }

        async function loadConversation() {
            const phone = document.getElementById('phone').value.trim();
            if (!phone) {
                setStatus('Completa el telefono primero', false);
                return;
            }
            conversationEl.innerHTML = '<div class="muted">Cargando conversacion...</div>';
            try {
                const res = await fetch('/admin/human/conversation?phone=' + encodeURIComponent(phone), {
                    headers: adminHeaders(),
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || 'Error al cargar conversacion');

                conversationEl.innerHTML = '';
                if (!data.messages.length) {
                    conversationEl.innerHTML = '<div class="muted">Sin mensajes para este numero.</div>';
                    return;
                }

                data.messages.forEach((msg) => {
                    const div = document.createElement('div');
                    div.className = 'msg';
                    div.innerHTML = '<strong>' + msg.direction.toUpperCase() + '</strong>: ' + msg.content + '<small>' + msg.created_at + ' | source=' + msg.source + '</small>';
                    conversationEl.appendChild(div);
                });
            } catch (err) {
                conversationEl.innerHTML = '<div class="err">' + err.message + '</div>';
            }
        }

        async function sendReply() {
            const phone = document.getElementById('phone').value.trim();
            const message = document.getElementById('message').value.trim();
            const closeCase = document.getElementById('closeCase').checked;
            const closingMessage = document.getElementById('closingMessage').value.trim();

            if (!phone || !message) {
                setStatus('Debes completar telefono y mensaje', false);
                return;
            }

            try {
                const res = await fetch('/admin/human/reply', {
                    method: 'POST',
                    headers: adminHeaders(),
                    body: JSON.stringify({
                        phone,
                        message,
                        close_case: closeCase,
                        closing_message: closingMessage || null,
                    }),
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || 'No se pudo enviar');

                setStatus('Respuesta enviada correctamente');
                document.getElementById('message').value = '';
                if (closeCase) {
                    document.getElementById('closeCase').checked = false;
                    document.getElementById('closingMessage').value = '';
                }
                loadQueue();
                loadConversation();
            } catch (err) {
                setStatus(err.message, false);
            }
        }

        document.getElementById('reloadQueue').addEventListener('click', loadQueue);
        document.getElementById('loadConversation').addEventListener('click', loadConversation);
        document.getElementById('sendReply').addEventListener('click', sendReply);
        loadQueue();
    </script>
</body>
</html>
"""


def _validate_twilio_signature(request: Request, form_data: dict) -> bool:
    if not settings.enable_twilio_signature_validation:
        return True

    signature = request.headers.get("X-Twilio-Signature", "")
    validator = RequestValidator(settings.twilio_auth_token)
    request_url = str(request.url)
    return validator.validate(request_url, form_data, signature)


def _build_escalation_message() -> str:
    return (
        "Te voy a pasar con un asesor humano para ayudarte mejor. "
        "En breve te contactamos por este mismo chat."
    )


def _build_busy_message() -> str:
    return (
        "Tu caso ya esta siendo revisado por un asesor humano. "
        "En breve continuamos por este medio."
    )


def _build_fallback_message() -> str:
    return (
        "No pude confirmar esa informacion con suficiente precision. "
        "Si quieres, te paso con un asesor humano ahora."
    )


def _build_menu_intro() -> str:
    return "Hola, soy el asistente virtual."


def _build_case_closed_message() -> str:
    return (
        "El asesor marco tu caso como resuelto. "
        "Si necesitas algo mas, escribe menu para continuar con el asistente automatico."
    )


def _validate_admin_key(x_admin_key: Optional[str]) -> None:
    if not settings.admin_api_key:
        raise HTTPException(status_code=503, detail="ADMIN_API_KEY no configurada")

    if x_admin_key != settings.admin_api_key:
        raise HTTPException(status_code=401, detail="No autorizado")


def _normalize_phone_for_wa(phone: str) -> str:
        allowed = "+0123456789"
        filtered = "".join(ch for ch in phone if ch in allowed)
        if filtered.startswith("+"):
                filtered = filtered[1:]
        return filtered


def _resolve_public_whatsapp_number() -> str:
        explicit = settings.public_whatsapp_number.strip()
        if explicit:
                return _normalize_phone_for_wa(explicit)

        fallback = settings.twilio_whatsapp_from.strip().replace("whatsapp:", "")
        return _normalize_phone_for_wa(fallback)


def _build_user_landing_html() -> str:
        wa_number = _resolve_public_whatsapp_number()
        prefilled = quote_plus("Hola! Quiero hacer una consulta.")
        wa_link = f"https://wa.me/{wa_number}?text={prefilled}" if wa_number else "#"
        disabled = "" if wa_number else "disabled"
        note = "" if wa_number else "Configura PUBLIC_WHATSAPP_NUMBER o TWILIO_WHATSAPP_FROM en .env"

        return f"""
<!doctype html>
<html lang=\"es\">
<head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>{settings.company_name} | Atencion por WhatsApp</title>
    <style>
        :root {{
            --bg0: #0f172a;
            --bg1: #111827;
            --card: #ffffff;
            --text: #14213d;
            --muted: #6b7280;
            --wa: #1fa463;
            --wa-hover: #168952;
        }}
        * {{ box-sizing: border-box; }}
        body {{
            margin: 0;
            min-height: 100vh;
            font-family: Segoe UI, system-ui, -apple-system, sans-serif;
            color: var(--text);
            background:
                radial-gradient(circle at 20% 10%, #273f73 0%, transparent 35%),
                radial-gradient(circle at 80% 85%, #173561 0%, transparent 32%),
                linear-gradient(140deg, var(--bg0), var(--bg1));
            display: grid;
            place-items: center;
            padding: 18px;
        }}
        .card {{
            width: 100%;
            max-width: 760px;
            background: var(--card);
            border-radius: 22px;
            padding: 34px 26px;
            box-shadow: 0 28px 80px rgba(0, 0, 0, 0.35);
        }}
        h1 {{ margin: 0 0 8px 0; font-size: clamp(28px, 4.3vw, 46px); }}
        p {{ margin: 0 0 20px 0; color: var(--muted); font-size: 18px; line-height: 1.5; }}
        .button {{
            display: inline-block;
            text-decoration: none;
            background: var(--wa);
            color: white;
            font-weight: 700;
            font-size: 19px;
            border-radius: 14px;
            padding: 14px 22px;
            transition: transform 0.15s ease, background 0.15s ease;
        }}
        .button:hover {{ background: var(--wa-hover); transform: translateY(-1px); }}
        .button.disabled {{
            background: #b7bfca;
            pointer-events: none;
            cursor: not-allowed;
        }}
        .note {{ margin-top: 14px; font-size: 13px; color: #b91c1c; }}
        .admin-link {{ display: inline-block; margin-top: 22px; color: #1d4ed8; font-size: 14px; }}
    </style>
</head>
<body>
    <main class=\"card\">
        <h1>{settings.company_name}</h1>
        <p>Atencion automatica por WhatsApp con soporte de asesor humano cuando lo necesites.</p>
        <a class=\"button {disabled and 'disabled' or ''}\" href=\"{wa_link}\" target=\"_blank\" rel=\"noopener noreferrer\">Comunicarme por WhatsApp</a>
        <div class=\"note\">{note}</div>
        <a class=\"admin-link\" href=\"/admin/human/panel\">Ir al panel interno de asesores</a>
    </main>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def root() -> HTMLResponse:
    return HTMLResponse(content=_build_user_landing_html())


@app.get("/health")
def health() -> dict:
    return {"status": "healthy"}


@app.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request) -> Response:
    form = await request.form()
    form_data = dict(form)

    if not _validate_twilio_signature(request, form_data):
        logger.warning("Firma Twilio invalida")
        return Response(content=to_twiml("Solicitud no valida."), media_type="application/xml")

    phone = str(form_data.get("From", ""))
    user_text = str(form_data.get("Body", "")).strip()

    logger.info("Mensaje entrante phone=%s body=%s", phone, user_text)

    if not phone:
        return Response(content=to_twiml("No se pudo identificar el remitente."), media_type="application/xml")

    if not user_text:
        response_text = "Recibi tu mensaje vacio. Puedes escribirme tu consulta y te ayudo."
        history_service.save_message(phone, "out", response_text, "system")
        return Response(content=to_twiml(response_text), media_type="application/xml")

    history_service.save_message(phone, "in", user_text, "user")

    response_text = f"{_build_menu_intro()}\n\n{faq_service.build_menu()}"
    history_service.save_message(phone, "out", response_text, "faq_menu")
    return Response(content=to_twiml(response_text), media_type="application/xml")

    normalized_text = user_text.lower()

    if normalized_text in {"hola", "buenas", "buen dia", "buenas tardes", "buenas noches"}:
        response_text = f"{_build_menu_intro()}\n\n{faq_service.build_menu()}"
        history_service.save_message(phone, "out", response_text, "faq_menu")
        return Response(content=to_twiml(response_text), media_type="application/xml")

    if normalized_text in {"menu", "faq", "opciones", "ayuda", "reiniciar", "salir"}:
        history_service.set_escalated(phone, False)
        response_text = f"Listo, volvemos al asistente automatico.\n\n{faq_service.build_menu()}"
        history_service.save_message(phone, "out", response_text, "faq_menu")
        return Response(content=to_twiml(response_text), media_type="application/xml")

    if normalized_text.isdigit():
        selection = int(normalized_text)
        selected_answer = faq_service.answer_by_number(selection)
        if selected_answer:
            response_text = selected_answer
            history_service.save_message(phone, "out", response_text, "faq_menu")
        else:
            response_text = (
                "No reconozco ese numero de opcion.\n\n"
                f"{faq_service.build_menu()}"
            )
            history_service.save_message(phone, "out", response_text, "faq_menu")
        return Response(content=to_twiml(response_text), media_type="application/xml")

    if history_service.is_escalated(phone):
        response_text = _build_busy_message()
        history_service.save_message(phone, "out", response_text, "human_queue")
        return Response(content=to_twiml(response_text), media_type="application/xml")

    faq_answer, faq_score = faq_service.best_match(user_text)

    if faq_answer and faq_score >= settings.faq_match_threshold:
        response_text = faq_answer
        source = "faq"
    else:
        safe_text = redact_sensitive_data(user_text)

        use_gemini = faq_score >= settings.faq_min_similarity_for_gemini or not faq_answer
        model_answer = gemini_service.generate_answer(safe_text, settings.company_name) if use_gemini else None

        if should_escalate(user_text, model_answer, faq_score):
            response_text = _build_escalation_message()
            source = "escalation"
            history_service.set_escalated(phone, True)
            notify_human(settings.human_notification_webhook, phone, user_text)
        elif model_answer:
            response_text = model_answer
            source = "gemini"
        else:
            response_text = _build_fallback_message()
            source = "fallback"

    history_service.save_message(phone, "out", response_text, source)
    return Response(content=to_twiml(response_text), media_type="application/xml")


@app.post("/admin/human/reply")
def human_reply(
    payload: HumanReplyRequest,
    x_admin_key: Optional[str] = Header(default=None, alias="X-Admin-Key"),
) -> dict:
    _validate_admin_key(x_admin_key)

    if not twilio_outbound_service.enabled:
        raise HTTPException(
            status_code=503,
            detail=(
                "Twilio outbound no configurado. Define TWILIO_ACCOUNT_SID, "
                "TWILIO_AUTH_TOKEN y TWILIO_WHATSAPP_FROM"
            ),
        )

    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="message no puede estar vacio")

    message_sid = twilio_outbound_service.send_whatsapp_message(
        payload.phone,
        payload.message.strip(),
    )
    history_service.save_message(payload.phone, "out", payload.message.strip(), "human_agent")

    closed = False
    if payload.close_case:
        history_service.set_escalated(payload.phone, False)
        closed = True

        closing_text = (payload.closing_message or "").strip() or _build_case_closed_message()
        closing_sid = twilio_outbound_service.send_whatsapp_message(payload.phone, closing_text)
        history_service.save_message(payload.phone, "out", closing_text, "system")
        return {
            "ok": True,
            "messageSid": message_sid,
            "closeMessageSid": closing_sid,
            "caseClosed": closed,
        }

    return {
        "ok": True,
        "messageSid": message_sid,
        "caseClosed": closed,
    }


@app.get("/admin/human/panel", response_class=HTMLResponse)
def human_panel() -> HTMLResponse:
    return HTMLResponse(content=ADMIN_PANEL_HTML)


@app.get("/admin", response_class=HTMLResponse)
def admin_shortcut() -> HTMLResponse:
    return HTMLResponse(content=ADMIN_PANEL_HTML)


@app.get("/admin/human/queue")
def human_queue(
    x_admin_key: Optional[str] = Header(default=None, alias="X-Admin-Key"),
) -> dict:
    _validate_admin_key(x_admin_key)
    return {"items": history_service.get_escalated_contacts()}


@app.get("/admin/human/conversation")
def human_conversation(
    phone: str,
    x_admin_key: Optional[str] = Header(default=None, alias="X-Admin-Key"),
) -> dict:
    _validate_admin_key(x_admin_key)
    return {
        "phone": phone,
        "messages": history_service.get_recent_messages(phone),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=(settings.app_env == "dev" and os.getenv("RELOAD", "true").lower() == "true"),
    )
