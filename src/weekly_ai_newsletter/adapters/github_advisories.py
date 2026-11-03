from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

import httpx

from weekly_ai_newsletter.adapters.http import get_with_retry, github_headers
from weekly_ai_newsletter.domain.errors import SourceError, describe_error
from weekly_ai_newsletter.domain.models import Vulnerability
from weekly_ai_newsletter.domain.window import TimeWindow

ADVISORIES_URL = "https://api.github.com/advisories"
ADVISORY_PAGE = "https://github.com/advisories/"
# About a dozen critical advisories are reviewed each week, so one page is plenty.
PER_PAGE = 100


class GithubAdvisorySource:
    """Critical advisories reviewed by GitHub, across every package ecosystem."""

    name = "GitHub advisories"

    def __init__(
        self,
        client: httpx.Client,
        *,
        token: str | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = client
        self._sleep = sleep
        self._headers = github_headers(token)

    def fetch(self, window: TimeWindow) -> list[Vulnerability]:
        last_day = (window.end - timedelta(days=1)).date()
        try:
            response = get_with_retry(
                self._client,
                ADVISORIES_URL,
                params={
                    "type": "reviewed",
                    "severity": "critical",
                    "published": f"{window.start.date().isoformat()}..{last_day.isoformat()}",
                    "per_page": PER_PAGE,
                },
                headers=self._headers,
                sleep=self._sleep,
            )
            advisories = [
                raw
                for raw in response.json()
                if window.contains(_published(raw))
                and str(raw["html_url"]).startswith(ADVISORY_PAGE)
            ]
            return [_to_vulnerability(raw) for raw in advisories]
        except httpx.HTTPError as exc:
            raise SourceError(f"GitHub advisories unavailable: {describe_error(exc)}") from exc
        except (ValueError, KeyError, TypeError) as exc:
            raise SourceError(f"GitHub advisories have an unexpected format: {exc!r}") from exc


def _published(raw: dict[str, Any]) -> datetime:
    return datetime.fromisoformat(str(raw["published_at"]).replace("Z", "+00:00"))


def _to_vulnerability(raw: dict[str, Any]) -> Vulnerability:
    packages = raw.get("vulnerabilities") or []
    affected = ", ".join(
        f"{p['package']['ecosystem']} {p['package']['name']} {p['vulnerable_version_range']}"
        for p in packages
    )
    fixes = ", ".join(
        str(p["first_patched_version"]) for p in packages if p["first_patched_version"]
    )
    return Vulnerability(
        id=str(raw.get("cve_id") or raw["ghsa_id"]),
        title=str(raw["summary"]),
        description=str(raw.get("description") or ""),
        url=str(raw["html_url"]),
        affected=affected,
        exploited=False,
        fixed_in=fixes,
    )
