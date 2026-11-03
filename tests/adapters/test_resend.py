import json

import httpx
import pytest

from weekly_ai_newsletter.adapters.resend import ResendEmailSender
from weekly_ai_newsletter.domain.errors import EmailDeliveryError
from weekly_ai_newsletter.domain.models import OutgoingEmail

EMAIL = OutgoingEmail(
    sender="onboarding@resend.dev",
    recipient="me@example.com",
    subject="Veille IA",
    html="<p>Hi</p>",
    text="Hi",
    idempotency_key="weekly-ai-newsletter-2026-11-04",
)


def test_posts_the_email_with_auth_and_idempotency_key() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"id": "abc"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    ResendEmailSender(client, api_key="re_key").send(EMAIL)
    [request] = captured
    assert str(request.url) == "https://api.resend.com/emails"
    assert request.headers["Authorization"] == "Bearer re_key"
    assert request.headers["Idempotency-Key"] == "weekly-ai-newsletter-2026-11-04"
    assert json.loads(request.content) == {
        "from": "onboarding@resend.dev",
        "to": ["me@example.com"],
        "subject": "Veille IA",
        "html": "<p>Hi</p>",
        "text": "Hi",
    }


def test_rejection_is_reported_without_leaking_the_key() -> None:
    transport = httpx.MockTransport(lambda r: httpx.Response(422, json={"message": "bad from"}))
    sender = ResendEmailSender(httpx.Client(transport=transport), api_key="re_secret")
    with pytest.raises(EmailDeliveryError, match="422") as excinfo:
        sender.send(EMAIL)
    assert "re_secret" not in str(excinfo.value)


def test_network_failure_is_a_delivery_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    sender = ResendEmailSender(client, api_key="k", sleep=lambda _: None)
    with pytest.raises(EmailDeliveryError, match="could not reach"):
        sender.send(EMAIL)


def test_transient_errors_are_retried() -> None:
    statuses = [429, 503, 200]
    delays: list[float] = []
    transport = httpx.MockTransport(lambda r: httpx.Response(statuses.pop(0), json={}))
    sender = ResendEmailSender(httpx.Client(transport=transport), api_key="k", sleep=delays.append)
    sender.send(EMAIL)
    assert statuses == []
    assert len(delays) == 2


def test_persistent_server_error_is_a_delivery_error() -> None:
    transport = httpx.MockTransport(lambda r: httpx.Response(500, json={}))
    sender = ResendEmailSender(httpx.Client(transport=transport), api_key="k", sleep=lambda _: None)
    with pytest.raises(EmailDeliveryError, match="500"):
        sender.send(EMAIL)


def test_idempotency_key_reused_with_new_content_is_a_delivery_error() -> None:
    # Resend answers 409 when the key was used with a *different* body: today's issue went out
    # with other content, so this one was not delivered and must not be recorded as sent.
    body = {"name": "invalid_idempotent_request", "message": "Same key, different payload"}
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(409, json=body)

    sender = ResendEmailSender(
        httpx.Client(transport=httpx.MockTransport(handler)), api_key="k", sleep=lambda _: None
    )
    with pytest.raises(EmailDeliveryError, match="already sent"):
        sender.send(EMAIL)
    assert len(requests) == 1


def test_rejection_names_the_error_without_echoing_the_response() -> None:
    body = {"name": "validation_error", "message": "You can only send to me@example.com"}
    transport = httpx.MockTransport(lambda r: httpx.Response(403, json=body))
    sender = ResendEmailSender(httpx.Client(transport=transport), api_key="k")
    with pytest.raises(EmailDeliveryError, match="403 validation_error") as excinfo:
        sender.send(EMAIL)
    assert "me@example.com" not in str(excinfo.value)
