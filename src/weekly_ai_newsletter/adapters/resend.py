from __future__ import annotations

import time
from collections.abc import Callable

import httpx

from weekly_ai_newsletter.domain.errors import EmailDeliveryError
from weekly_ai_newsletter.domain.models import OutgoingEmail

RESEND_API_URL = "https://api.resend.com/emails"
_RETRY_STATUSES = frozenset({409, 429, 500, 502, 503, 504})
# Same idempotency key with a different body: this issue was already delivered.
_ALREADY_SENT = "invalid_idempotent_request"


class ResendEmailSender:
    """EmailSender for the Resend API; the idempotency key makes retries safe."""

    def __init__(
        self,
        client: httpx.Client,
        *,
        api_key: str,
        attempts: int = 4,
        backoff_seconds: float = 2.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = client
        self._api_key = api_key
        self._attempts = attempts
        self._backoff = backoff_seconds
        self._sleep = sleep

    def send(self, message: OutgoingEmail) -> None:
        error = "no attempt made"
        for attempt in range(self._attempts):
            if attempt:
                self._sleep(self._backoff * 2 ** (attempt - 1))
            try:
                response = self._post(message)
            except httpx.TransportError as exc:
                error = f"could not reach Resend: {exc}"
                continue
            if not response.is_error:
                return
            error = f"Resend rejected the email ({response.status_code}): {response.text[:300]}"
            if response.status_code == 409 and _error_name(response) == _ALREADY_SENT:
                return
            if response.status_code not in _RETRY_STATUSES:
                break
        raise EmailDeliveryError(error)

    def _post(self, message: OutgoingEmail) -> httpx.Response:
        return self._client.post(
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


def _error_name(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return ""
    return str(body.get("name", "")) if isinstance(body, dict) else ""
