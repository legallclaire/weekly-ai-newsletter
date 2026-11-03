import re
from datetime import date

from tests.factories import make_extension, make_paper, make_repo, make_score, make_vulnerability
from weekly_ai_newsletter.domain.models import (
    CuratedExtension,
    CuratedRepo,
    DevToolChange,
    DevToolGroup,
    NewsItem,
    SecurityAlert,
    SelectedPaper,
)
from weekly_ai_newsletter.domain.newsletter import Newsletter, Section
from weekly_ai_newsletter.rendering.renderer import NewsletterRenderer, format_issue_date

PAPER = SelectedPaper(
    paper=make_paper("2610.00001", title="Agents <that> plan & act"),
    score=make_score(
        "2610.00001", relevance=9, novelty=8, evidence=7, depth=8, practical_utility=6
    ),
    summary="Un résumé.",
    why_selected="Parce que.",
)


SECURITY = [
    SecurityAlert(
        make_vulnerability(
            "GHSA-aaaa-bbbb-cccc",
            exploited=False,
            title="Sandbox <escape>",
            affected="npm @acme/elo <= 1.0.0",
            fixed_in="1.0.1",
        ),
        "Mettre à jour `@acme/elo`.",
    ),
    SecurityAlert(make_vulnerability("CVE-2026-1001", affected="WordPress Core"), "Exploitée."),
    SecurityAlert(make_vulnerability("CVE-2026-1002", affected="Acme VPN", title="Auth bypass")),
]


def newsletter(
    language: str = "fr",
    *,
    papers: Section[SelectedPaper] | None = None,
    repos: Section[CuratedRepo] | None = None,
    security: Section[SecurityAlert] | None = None,
) -> Newsletter:
    change = DevToolChange("v2.1.0", "https://gh.example/r", "Hooks.")
    repo = CuratedRepo(make_repo("acme/agent-kit", stars_this_week=2345), "Utile.")
    return Newsletter(
        issue_date=date(2026, 11, 4),
        language=language,
        news=Section.ok([NewsItem("Model X", "https://n.example/x", "Lab", "Big.")]),
        devtools=Section.ok([DevToolGroup("Claude Code", (change,))]),
        papers=papers if papers is not None else Section.ok([PAPER]),
        repos=repos if repos is not None else Section.ok([repo]),
        extensions=Section.ok(
            [
                CuratedExtension(make_extension("acme/review-skill", stars=1234), "Revue.", False),
                CuratedExtension(
                    make_extension("acme/db-mcp", topics=("mcp-server",)), "Base.", True
                ),
            ]
        ),
        security=security if security is not None else Section.ok(SECURITY),
    )


def test_subject_and_dates_are_localised() -> None:
    assert format_issue_date(date(2026, 11, 4), "fr") == "4 novembre 2026"
    assert format_issue_date(date(2026, 11, 4), "en") == "November 4, 2026"
    assert NewsletterRenderer().render(newsletter()).subject == "Veille IA hebdo — 4 novembre 2026"


def test_html_contains_every_section_with_links_and_score_breakdown() -> None:
    html = NewsletterRenderer().render(newsletter()).html
    for expected in (
        "Actualité IA",
        "https://n.example/x",
        "Claude Code",
        "https://gh.example/r",
        "https://arxiv.org/abs/2610.00001",
        "Un résumé.",
        "Parce que.",
        "Pertinence 9",
        "55/70",
        "https://github.com/acme/agent-kit",
        "2\u202f345",
    ):
        assert expected in html, expected


def test_html_escapes_titles_but_text_keeps_them_readable() -> None:
    rendered = NewsletterRenderer().render(newsletter())
    assert "Agents &lt;that&gt; plan &amp; act" in rendered.html
    assert "Agents <that> plan & act" in rendered.text


def test_unavailable_and_empty_sections_show_notices() -> None:
    rendered = NewsletterRenderer().render(
        newsletter(repos=Section.unavailable("trending down"), papers=Section.ok([]))
    )
    assert "Rubrique indisponible cette semaine." in rendered.html
    # the HTML escapes the apostrophe (&#39;), so check the text version
    assert "Rien d'assez solide cette semaine." in rendered.text
    assert "trending down" not in rendered.html


def test_english_labels() -> None:
    rendered = NewsletterRenderer().render(newsletter(language="en"))
    assert rendered.subject == "Weekly AI digest — November 4, 2026"
    assert "Research papers" in rendered.html and "Relevance 9" in rendered.text


def test_enterprise_use_is_shown_only_when_present() -> None:
    with_use = SelectedPaper(
        paper=PAPER.paper,
        score=PAPER.score,
        summary=PAPER.summary,
        why_selected=PAPER.why_selected,
        enterprise_use="Réduit le coût d'un assistant interne.",
    )
    shown = NewsletterRenderer().render(newsletter(papers=Section.ok([with_use])))
    assert "En entreprise :" in shown.text
    assert "Réduit le coût d" in shown.html
    hidden = NewsletterRenderer().render(newsletter())
    assert "En entreprise" not in hidden.html + hidden.text


def test_numbers_follow_the_language_convention() -> None:
    assert "+2,345 stars this week" in NewsletterRenderer().render(newsletter("en")).text
    assert "+2\u202f345 étoiles cette semaine" in NewsletterRenderer().render(newsletter()).text


def test_inline_code_in_summaries_renders_as_code_in_html() -> None:
    change = DevToolChange("v1", "https://gh.example/r", "Adds `/security-review` <now>.")
    base = newsletter()
    rendered = NewsletterRenderer().render(
        Newsletter(
            issue_date=base.issue_date,
            language="fr",
            news=base.news,
            devtools=Section.ok([DevToolGroup("Copilot", (change,))]),
            papers=base.papers,
            repos=base.repos,
            extensions=base.extensions,
            security=base.security,
        )
    )
    assert "<code" in rendered.html and "/security-review</code>" in rendered.html
    assert "`" not in rendered.html
    assert "&lt;now&gt;" in rendered.html


def test_extensions_section_shows_stars_and_marks_mcp_servers() -> None:
    rendered = NewsletterRenderer().render(newsletter())
    assert "Skills &amp; plugins" in rendered.html
    assert "https://github.com/acme/review-skill" in rendered.html
    assert "1\u202f234 étoiles" in rendered.text
    assert "acme/db-mcp (MCP" in rendered.text


def test_english_output_has_no_space_before_punctuation() -> None:
    rendered = NewsletterRenderer().render(newsletter(language="en"))
    for text in (rendered.text, rendered.html):
        assert not re.search("[ \u00a0\u202f][:;!?]", text)


def test_security_section_comes_last_with_highlights_then_a_brief_list() -> None:
    rendered = NewsletterRenderer().render(newsletter())
    html, text = rendered.html, rendered.text
    assert html.index("⚠️ Sécurité") > html.index("Skills &amp; plugins")
    assert "## ⚠️ Sécurité" in text
    assert "Sandbox &lt;escape&gt;" in html and "/@acme/elo</code>" not in html
    assert "<code" in html and "@acme/elo</code>" in html
    assert "https://github.com/advisories/GHSA-aaaa-bbbb-cccc" not in html  # factory uses NVD
    assert "https://nvd.nist.gov/vuln/detail/GHSA-aaaa-bbbb-cccc" in html
    assert "Corrigé en 1.0.1" in text
    assert "Exploitée activement" in text
    brief = text.split("Aussi exploitées cette semaine :")[1]
    assert "CVE-2026-1002" in brief and "Acme VPN" in brief and "Auth bypass" in brief
    assert "CVE-2026-1001" not in brief


def test_security_brief_list_is_omitted_when_every_flaw_is_highlighted() -> None:
    rendered = NewsletterRenderer().render(newsletter(security=Section.ok(SECURITY[:2])))
    assert "Aussi exploitées" not in rendered.html + rendered.text


def test_security_section_in_english() -> None:
    text = NewsletterRenderer().render(newsletter(language="en")).text
    assert "## ⚠️ Security" in text and "Fixed in 1.0.1" in text
    assert "Also exploited this week:" in text and "Actively exploited" in text
