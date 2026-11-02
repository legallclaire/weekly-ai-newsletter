from __future__ import annotations

import httpx

from weekly_ai_newsletter.domain.errors import EmailDeliveryError
from weekly_ai_newsletter.domain.models import OutgoingEmail

RESEND_API_URL = "https://api.resend.com/emails"


class ResendEmailSender:
    """EmailSender for the Resend API; the idempotency key prevents duplicate sends."""

    def __init__(self, client: httpx.Client, *, api_key: str) -> None:
        self._client = client
        self._api_key = api_key

    def send(self, message: OutgoingEmail) -> None:
        try:
            response = self._client.post(
                RESEND_API_URL,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Idempotency-Key": message.idempotency_key,
                },
                json={
                    "from": message.sender,
                    "to": [message.recipient],
                    "subject": message.subject,
                    "html": message.html,
                    "text": message.text,
                },
            )
        except httpx.HTTPError as exc:
            raise EmailDeliveryError(f"could not reach Resend: {exc}") from exc
        if response.is_error:
            raise EmailDeliveryError(
                f"Resend rejected the email ({response.status_code}): {response.text[:300]}"
            )
