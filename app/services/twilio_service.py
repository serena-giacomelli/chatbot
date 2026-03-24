from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client


def to_twiml(message: str) -> str:
    response = MessagingResponse()
    response.message(message)
    return str(response)


class TwilioOutboundService:
    def __init__(self, account_sid: str, auth_token: str, whatsapp_from: str) -> None:
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.whatsapp_from = whatsapp_from
        self.enabled = bool(account_sid and auth_token and whatsapp_from)
        self._client = Client(account_sid, auth_token) if self.enabled else None

    def send_whatsapp_message(self, to_phone: str, body: str) -> str:
        if not self.enabled or self._client is None:
            raise RuntimeError("Twilio outbound no esta configurado")

        to_value = to_phone if to_phone.startswith("whatsapp:") else f"whatsapp:{to_phone}"
        from_value = (
            self.whatsapp_from
            if self.whatsapp_from.startswith("whatsapp:")
            else f"whatsapp:{self.whatsapp_from}"
        )

        message = self._client.messages.create(
            body=body,
            from_=from_value,
            to=to_value,
        )
        return str(message.sid)
