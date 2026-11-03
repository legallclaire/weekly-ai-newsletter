import json

from tests.factories import make_vulnerability
from tests.fakes import FakeLLM
from weekly_ai_newsletter.services.security_curator import (
    SecurityCurator,
    SecurityPick,
    SecuritySelection,
    merge_vulnerabilities,
)

EXPLOITED_A = make_vulnerability("CVE-2026-1", exploited=True)
EXPLOITED_B = make_vulnerability("CVE-2026-2", exploited=True)
CRITICAL = make_vulnerability("GHSA-aaaa-bbbb-cccc", exploited=False, fixed_in="1.0.1")
OTHER_CRITICAL = make_vulnerability("CVE-2026-4", exploited=False)


def test_highlights_come_first_then_every_other_exploited_flaw() -> None:
    picks = [SecurityPick(index=2, summary="Patch now."), SecurityPick(index=1, summary="Big.")]
    llm = FakeLLM({SecuritySelection: SecuritySelection(picks=picks)})
    candidates = [EXPLOITED_A, EXPLOITED_B, CRITICAL, OTHER_CRITICAL]

    alerts = SecurityCurator(llm, language="fr", max_items=5).curate(candidates)

    assert [(a.vulnerability.id, a.summary) for a in alerts] == [
        ("GHSA-aaaa-bbbb-cccc", "Patch now."),
        ("CVE-2026-2", "Big."),
        ("CVE-2026-1", ""),  # exploited: listed even without a write-up
    ]
    system, prompt, _ = llm.calls[0]
    assert "French" in system and "at most 5" in system
    sent = json.loads(prompt)
    assert sent[0]["exploited"] is True and sent[2]["fixed_in"] == "1.0.1"


def test_highlights_are_capped_and_bad_indices_ignored() -> None:
    picks = [SecurityPick(index=i, summary="s") for i in (9, 3, 3, -1, 2)]
    llm = FakeLLM({SecuritySelection: SecuritySelection(picks=picks)})
    alerts = SecurityCurator(llm, language="en", max_items=1).curate(
        [EXPLOITED_A, EXPLOITED_B, CRITICAL, OTHER_CRITICAL]
    )
    assert [(a.vulnerability.id, a.summary) for a in alerts] == [
        ("CVE-2026-4", "s"),
        ("CVE-2026-1", ""),
        ("CVE-2026-2", ""),
    ]


def test_brief_lists_only_exploited_flaws() -> None:
    alerts = SecurityCurator.brief([CRITICAL, EXPLOITED_A])
    assert [(a.vulnerability.id, a.summary) for a in alerts] == [("CVE-2026-1", "")]


def test_empty_input_skips_llm() -> None:
    llm = FakeLLM({})
    assert SecurityCurator(llm, language="en", max_items=5).curate([]) == []
    assert llm.calls == []


def test_merge_keeps_one_entry_per_id_and_puts_exploited_first() -> None:
    advisory = make_vulnerability(
        "CVE-2026-1", exploited=False, affected="pip acme", fixed_in="2.0"
    )
    merged = merge_vulnerabilities([[OTHER_CRITICAL, advisory], [EXPLOITED_B, EXPLOITED_A]])

    assert [v.id for v in merged] == ["CVE-2026-1", "CVE-2026-2", "CVE-2026-4"]
    # The advisory keeps its package details and gains the exploitation flag.
    assert merged[0].exploited and merged[0].affected == "pip acme" and merged[0].fixed_in == "2.0"
