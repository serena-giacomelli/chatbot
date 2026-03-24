# Chatbot WhatsApp con Gemini + Twilio (Python)

MVP para atencion de clientes por WhatsApp con:
- FAQ local con coincidencia aproximada
- Menu de preguntas frecuentes por numero (1, 2, 3...)
- Fallback a Gemini (free tier) para preguntas abiertas
- Filtro de datos sensibles antes de enviar a Gemini
- Escalamiento a humano por reglas de baja confianza
- Historial en SQLite

## 1. Requisitos

- Python 3.11+
- Cuenta de Twilio con WhatsApp Sandbox habilitado
- API key de Gemini

## 2. Instalacion

```bash
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Crear archivo `.env` desde `.env.example` y completar claves.

## 3. Ejecutar local

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Healthcheck:
- `GET /health`

Front de usuario:
- `GET /` (boton "Comunicarme por WhatsApp")

Front admin:
- `GET /admin` o `GET /admin/human/panel`

Webhook de Twilio:
- `POST /webhook/whatsapp`

## 4. Conectar con Twilio Sandbox

1. Exponer local con ngrok o Cloudflared si estas en local:
   - `ngrok http 8000`
2. Copiar URL publica y configurar en Twilio Sandbox:
   - `WHEN A MESSAGE COMES IN` -> `https://TU-URL/webhook/whatsapp`
   - Metodo `HTTP POST`
3. Enviar mensaje desde WhatsApp al numero sandbox y validar respuesta.

## 5. Variables importantes

- `TWILIO_ACCOUNT_SID`: SID de cuenta Twilio
- `GEMINI_API_KEY`: clave de Gemini
- `TWILIO_AUTH_TOKEN`: token de Twilio para validar firma
- `TWILIO_WHATSAPP_FROM`: remitente WhatsApp de Twilio (sandbox o numero aprobado)
- `PUBLIC_WHATSAPP_NUMBER`: numero que usa el boton de la landing de usuario
- `ENABLE_TWILIO_SIGNATURE_VALIDATION`: en produccion poner `true`
- `ADMIN_API_KEY`: clave para endpoint admin de respuesta humana
- `FAQ_MATCH_THRESHOLD`: umbral para responder directo con FAQ
- `FAQ_MIN_SIMILARITY_FOR_GEMINI`: controla cuando invocar Gemini
- `HUMAN_NOTIFICATION_WEBHOOK`: webhook opcional para avisar a equipo humano

## 6. Flujo de escalamiento

Se escala a humano cuando:
- El cliente lo pide explicitamente (`asesor`, `humano`, `agente`, etc.)
- No hay respuesta confiable
- Gemini devuelve frases de baja confianza

Comandos de control del cliente:
- `menu` / `faq` / `opciones` / `ayuda` / `reiniciar` / `salir`: muestra el menu FAQ.

## 7. Menu FAQ

- Si el cliente escribe `hola`, el bot responde con un menu de FAQ.
- Si el cliente responde con un numero (`1`, `2`, `3`...), el bot contesta con la respuesta FAQ correspondiente.
- Si el numero no existe, el bot vuelve a mostrar el menu.
- El contenido del menu se toma desde `data/faq.json` en el mismo orden de las preguntas.

## 8. Despliegue (Render / Railway / Fly.io)

- Comando de inicio recomendado:
  - `uvicorn main:app --host 0.0.0.0 --port $PORT`
- Configurar variables de entorno del `.env`
- Activar `ENABLE_TWILIO_SIGNATURE_VALIDATION=true`
- Configurar URL publica en Twilio

### Render (paso a paso)

1. En Render, elegir **New +** -> **Blueprint**.
2. Conectar el repositorio de GitHub de este proyecto.
3. Render detecta `render.yaml` y crea el servicio web automaticamente.
4. En el servicio creado, abrir **Environment** y completar los valores `sync: false`.
5. Hacer deploy y esperar a que termine el build.
6. Probar la URL publica en `/health`.
7. En Twilio, actualizar `WHEN A MESSAGE COMES IN` con:
    - `https://TU-SERVICIO-RENDER.onrender.com/webhook/whatsapp`
    - Metodo `HTTP POST`
8. Probar WhatsApp de nuevo con `hola` y una opcion numerica del menu.

## 9. Respuesta humana por Twilio (handoff)

Cuando un caso escala, puedes responder como asesor con este endpoint:

- `POST /admin/human/reply`
- Header: `X-Admin-Key: <ADMIN_API_KEY>`
- Body JSON:

```json
{
   "phone": "whatsapp:+5491111111111",
   "message": "Hola, soy Ana del equipo de soporte. Ya reviso tu caso.",
   "close_case": false
}
```

Si quieres cerrar el caso y devolver el control al bot en el mismo paso:

```json
{
   "phone": "whatsapp:+5491111111111",
   "message": "Perfecto, ya quedo resuelto.",
   "close_case": true,
   "closing_message": "Gracias por contactarnos. Si necesitas algo mas, escribe menu."
}
```

Con `close_case=true` el contacto sale del modo humano y vuelve al asistente automatico.

### Panel web interno para asesores

Tambien puedes usar un panel en navegador para responder sin curl:

- URL: `/admin/human/panel`
- El panel pide `X-Admin-Key` para operar.
- Funciones del panel:
   - Ver bandeja de contactos escalados
   - Ver conversacion reciente por telefono
   - Responder como asesor por Twilio
   - Cerrar caso y devolver control al bot automatico

Endpoints usados por el panel:

- `GET /admin/human/queue`
- `GET /admin/human/conversation?phone=...`
- `POST /admin/human/reply`

## 10. Siguientes mejoras recomendadas

- Reemplazar SQLite por PostgreSQL en produccion
- Panel interno para bandeja de casos escalados
- Métricas (tasa de resolucion y escalamiento)
- Pruebas unitarias y e2e
