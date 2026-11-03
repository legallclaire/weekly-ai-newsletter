from __future__ import annotations

import re
import time
from collections.abc import Callable
from datetime import UTC, datetime

import httpx

from weekly_ai_newsletter.adapters.http import get_with_retry
from weekly_ai_newsletter.domain.errors import SourceError, describe_error
from weekly_ai_newsletter.domain.models import Vulnerability
from weekly_ai_newsletter.domain.window import TimeWindow

KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
_CVE_ID = re.compile(r"CVE-\d{4}-\d{4,}")


class CisaKevSource:
    """Vulnerabilities CISA added this week to its catalog of known exploited ones."""

    name = "CISA KEV"

    def __init__(
        self, client: httpx.Client, *, sleep: Callable[[float], None] = time.sleep
    ) -> None:
        self._client = client
        self._sleep = sleep

    def fetch(self, window: TimeWindow) -> list[Vulnerability]:
        try:
            response = get_with_retry(self._client, KEV_URL, sleep=self._sleep)
            entries = response.json()["vulnerabilities"]
            vulns = [_to_vulnerability(raw) for raw in entries if _added_in(raw, window)]
        except httpx.HTTPError as exc:
            raise SourceError(f"CISA catalog unavailable: {describe_error(exc)}") from exc
        except (ValueError, KeyError, TypeError) as exc:
            raise SourceError(f"CISA catalog has an unexpected format: {exc!r}") from exc
        # The NVD link is built from the id, so only well-formed CVE ids are kept.
        return [vuln for vuln in vulns if _CVE_ID.fullmatch(vuln.id)]


def _added_in(raw: dict[str, str], window: TimeWindow) -> bool:
    added = datetime.fromisoformat(raw["dateAdded"]).replace(tzinfo=UTC)
    return window.contains(added)


def _to_vulnerability(raw: dict[str, str]) -> Vulnerability:
    cve, vendor, product = raw["cveID"], raw["vendorProject"], raw["product"]
    return Vulnerability(
        id=cve,
        title=raw["vulnerabilityName"],
        description=raw["shortDescription"],
        url=f"https://nvd.nist.gov/vuln/detail/{cve}",
        # Products often repeat the vendor ("WordPress" / "WordPress Core").
        affected=product if product.startswith(vendor) else f"{vendor} {product}",
        exploited=True,
    )
