from __future__ import annotations

import time
from collections.abc import Callable, Mapping

import httpx

RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})
USER_AGENT = "weekly-ai-newsletter (+https://github.com/legallclaire/weekly-ai-newsletter)"


def make_http_client(timeout: float = 30.0) -> httpx.Client:
    return httpx.Client(timeout=timeout, follow_redirects=True, headers={"User-Agent": USER_AGENT})


def github_headers(token: str | None) -> dict[str, str]:
    """Headers for the GitHub REST API; a token raises the rate limit from 60 to 5000/h."""
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def get_with_retry(
    client: httpx.Client,
    url: str,
    *,
    params: Mapping[str, str | int] | None = None,
    headers: Mapping[str, str] | None = None,
    retries: int = 3,
    backoff: float = 2.0,
    sleep: Callable[[float], None] = time.sleep,
) -> httpx.Response:
    """GET with exponential backoff on transient failures; other errors raise at once."""
    error: httpx.HTTPError | None = None
    for attempt in range(retries + 1):
        if attempt:
            sleep(backoff * 2 ** (attempt - 1))
        try:
            response = client.get(url, params=params, headers=headers)
        except httpx.TransportError as exc:
            error = exc
            continue
        if response.status_code not in RETRYABLE_STATUSES:
            response.raise_for_status()
            return response
        error = httpx.HTTPStatusError(
            f"retryable status {response.status_code} for {url}",
            request=response.request,
            response=response,
        )
    assert error is not None
    raise error
