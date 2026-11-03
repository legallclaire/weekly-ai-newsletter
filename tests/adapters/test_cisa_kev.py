from datetime import date

import httpx
import pytest

from weekly_ai_newsletter.adapters.cisa_kev import KEV_URL, CisaKevSource
from weekly_ai_newsletter.domain.errors import SourceError
from weekly_ai_newsletter.domain.window import TimeWindow

WINDOW = TimeWindow.week_before(date(2026, 11, 4))


def entry(cve: str, added: str, **extra: str) -> dict[str, str]:
    return {
        "cveID": cve,
        "vendorProject": "WordPress",
        "product": "WordPress Core",
        "vulnerabilityName": "WordPress Core Race Condition Vulnerability",
        "dateAdded": added,
        "shortDescription": "Lets unauthenticated attackers execute code.",
        **extra,
    }


def source(payload: object, status: int = 200) -> CisaKevSource:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == KEV_URL
        return httpx.Response(status, json=payload)

    return CisaKevSource(httpx.Client(transport=httpx.MockTransport(handler)), sleep=lambda _: None)


def test_keeps_entries_added_during_the_week_as_exploited() -> None:
    catalog = {
        "vulnerabilities": [
            entry("CVE-2026-1001", "2026-10-28"),  # first day of the window
            entry("CVE-2026-1002", "2026-11-03"),  # last day
            entry("CVE-2026-1003", "2026-10-27"),  # the week before
            entry("CVE-2026-1004", "2026-11-04"),  # run day, next week's issue
        ]
    }
    vulns = source(catalog).fetch(WINDOW)

    assert [v.id for v in vulns] == ["CVE-2026-1001", "CVE-2026-1002"]
    first = vulns[0]
    assert first.exploited
    assert first.url == "https://nvd.nist.gov/vuln/detail/CVE-2026-1001"
    assert first.affected == "WordPress Core"  # not "WordPress WordPress Core"
    assert first.title == "WordPress Core Race Condition Vulnerability"
    assert first.description == "Lets unauthenticated attackers execute code."
    assert first.fixed_in == ""


def test_affected_names_the_vendor_when_the_product_does_not() -> None:
    catalog = {"vulnerabilities": [entry("CVE-2026-1001", "2026-10-30", product="Connect Secure")]}
    catalog["vulnerabilities"][0]["vendorProject"] = "Ivanti"
    [vuln] = source(catalog).fetch(WINDOW)
    assert vuln.affected == "Ivanti Connect Secure"


def test_skips_entries_whose_id_is_not_a_cve() -> None:
    catalog = {"vulnerabilities": [entry('CVE-2026-1"><x', "2026-10-30")]}
    assert source(catalog).fetch(WINDOW) == []


def test_http_failure_is_a_source_error() -> None:
    with pytest.raises(SourceError, match="CISA"):
        source({}, status=503).fetch(WINDOW)


def test_unexpected_payload_is_a_source_error() -> None:
    with pytest.raises(SourceError, match="CISA"):
        source({"vulnerabilities": [{"cveID": "CVE-2026-1"}]}).fetch(WINDOW)
