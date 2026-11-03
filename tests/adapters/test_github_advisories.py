from datetime import date
from typing import Any

import httpx
import pytest

from weekly_ai_newsletter.adapters.github_advisories import ADVISORIES_URL, GithubAdvisorySource
from weekly_ai_newsletter.domain.errors import SourceError
from weekly_ai_newsletter.domain.window import TimeWindow

WINDOW = TimeWindow.week_before(date(2026, 11, 4))


def advisory(ghsa: str, cve: str | None, published: str, **extra: Any) -> dict[str, Any]:
    return {
        "ghsa_id": ghsa,
        "cve_id": cve,
        "html_url": f"https://github.com/advisories/{ghsa}",
        "summary": "Sandbox escape to arbitrary code execution",
        "description": "### Summary\n\nAn attacker can run code.",
        "published_at": published,
        "vulnerabilities": [
            {
                "package": {"ecosystem": "npm", "name": "@enspirit/elo"},
                "vulnerable_version_range": "<= 1.0.0",
                "first_patched_version": "1.0.1",
            }
        ],
        **extra,
    }


def source(payload: object, requests: list[httpx.Request] | None = None) -> GithubAdvisorySource:
    def handler(request: httpx.Request) -> httpx.Response:
        if requests is not None:
            requests.append(request)
        return httpx.Response(200, json=payload)

    return GithubAdvisorySource(
        httpx.Client(transport=httpx.MockTransport(handler)), token="t0k", sleep=lambda _: None
    )


def test_asks_for_reviewed_critical_advisories_of_the_week() -> None:
    requests: list[httpx.Request] = []
    source([], requests).fetch(WINDOW)

    [request] = requests
    assert str(request.url).startswith(ADVISORIES_URL)
    assert dict(request.url.params) == {
        "type": "reviewed",
        "severity": "critical",
        "published": "2026-10-28..2026-11-03",
        "per_page": "100",
    }
    assert request.headers["Authorization"] == "Bearer t0k"


def test_maps_advisories_and_prefers_the_cve_id() -> None:
    payload = [
        advisory("GHSA-aaaa-bbbb-cccc", "CVE-2026-44267", "2026-11-03T17:53:42Z"),
        advisory("GHSA-dddd-eeee-ffff", None, "2026-10-29T08:00:00Z"),
    ]
    first, second = source(payload).fetch(WINDOW)

    assert first.id == "CVE-2026-44267"
    assert first.url == "https://github.com/advisories/GHSA-aaaa-bbbb-cccc"
    assert first.title == "Sandbox escape to arbitrary code execution"
    assert first.affected == "npm @enspirit/elo <= 1.0.0"
    assert first.fixed_in == "1.0.1"
    assert not first.exploited
    assert second.id == "GHSA-dddd-eeee-ffff"


def test_lists_every_affected_package_and_tolerates_missing_fixes() -> None:
    packages = [
        {
            "package": {"ecosystem": "pip", "name": "vllm"},
            "vulnerable_version_range": "< 0.9.0",
            "first_patched_version": "0.9.0",
        },
        {
            "package": {"ecosystem": "pip", "name": "vllm-extra"},
            "vulnerable_version_range": "<= 2.0",
            "first_patched_version": None,
        },
    ]
    payload = [
        advisory("GHSA-aaaa-bbbb-cccc", None, "2026-10-30T00:00:00Z", vulnerabilities=packages)
    ]
    [vuln] = source(payload).fetch(WINDOW)
    assert vuln.affected == "pip vllm < 0.9.0, pip vllm-extra <= 2.0"
    assert vuln.fixed_in == "0.9.0"


def test_drops_advisories_outside_the_window_or_with_a_foreign_link() -> None:
    payload = [
        advisory("GHSA-aaaa-bbbb-cccc", None, "2026-11-04T00:00:00Z"),
        advisory(
            "GHSA-dddd-eeee-ffff", None, "2026-10-30T00:00:00Z", html_url="https://evil.example/"
        ),
    ]
    assert source(payload).fetch(WINDOW) == []


def test_failure_is_a_source_error_without_the_response_body() -> None:
    transport = httpx.MockTransport(lambda r: httpx.Response(422, json={"message": "secret"}))
    advisories = GithubAdvisorySource(httpx.Client(transport=transport), sleep=lambda _: None)
    with pytest.raises(SourceError, match="GitHub advisories") as excinfo:
        advisories.fetch(WINDOW)
    assert "secret" not in str(excinfo.value)
