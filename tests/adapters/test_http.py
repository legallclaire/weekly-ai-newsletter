import httpx
import pytest

from weekly_ai_newsletter.adapters.http import get_with_retry


def client_returning(*statuses: int) -> tuple[httpx.Client, list[int]]:
    seen: list[int] = []
    queue = list(statuses)

    def handler(request: httpx.Request) -> httpx.Response:
        status = queue.pop(0)
        seen.append(status)
        return httpx.Response(status, text="ok")

    return httpx.Client(transport=httpx.MockTransport(handler)), seen


def test_retries_retryable_statuses_with_exponential_backoff() -> None:
    client, seen = client_returning(503, 429, 200)
    delays: list[float] = []
    response = get_with_retry(client, "https://x.example", sleep=delays.append)
    assert response.status_code == 200
    assert seen == [503, 429, 200]
    assert delays == [2.0, 4.0]


def test_gives_up_after_retries() -> None:
    client, _ = client_returning(500, 500, 500, 500)
    with pytest.raises(httpx.HTTPStatusError):
        get_with_retry(client, "https://x.example", sleep=lambda _: None)


def test_does_not_retry_client_errors() -> None:
    client, seen = client_returning(404)
    with pytest.raises(httpx.HTTPStatusError):
        get_with_retry(client, "https://x.example", sleep=lambda _: None)
    assert seen == [404]


def test_retries_transport_errors() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ConnectTimeout("slow", request=request)
        return httpx.Response(200)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert get_with_retry(client, "https://x.example", sleep=lambda _: None).status_code == 200
