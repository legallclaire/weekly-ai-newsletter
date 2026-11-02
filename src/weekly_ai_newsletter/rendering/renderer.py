from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape

from weekly_ai_newsletter.domain.models import MAX_TOTAL
from weekly_ai_newsletter.domain.newsletter import Newsletter

LABELS: dict[str, dict[str, str]] = {
    "fr": {
        "title": "Veille IA hebdo",
        "news": "Actualité IA",
        "devtools": "Outils de dev IA",
        "papers": "Papiers de recherche",
        "repos": "Tendances GitHub",
        "unavailable": "Rubrique indisponible cette semaine.",
        "empty": "Rien de notable cette semaine.",
        "empty_papers": "Rien d'assez solide cette semaine.",
        "why_selected": "Pourquoi ce papier",
        "stars_this_week": "étoiles cette semaine",
        "relevance": "Pertinence",
        "novelty": "Nouveauté",
        "evidence": "Preuves",
        "depth": "Profondeur",
        "practical_utility": "Utilité",
        "footer": "Généré automatiquement par weekly-ai-newsletter.",
    },
    "en": {
        "title": "Weekly AI digest",
        "news": "AI news",
        "devtools": "AI dev tools",
        "papers": "Research papers",
        "repos": "GitHub trending",
        "unavailable": "Section unavailable this week.",
        "empty": "Nothing notable this week.",
        "empty_papers": "Nothing solid enough this week.",
        "why_selected": "Why this paper",
        "stars_this_week": "stars this week",
        "relevance": "Relevance",
        "novelty": "Novelty",
        "evidence": "Evidence",
        "depth": "Depth",
        "practical_utility": "Utility",
        "footer": "Generated automatically by weekly-ai-newsletter.",
    },
}

_FRENCH_MONTHS = (
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
)


def format_issue_date(day: date, language: str) -> str:
    if language == "fr":
        return f"{day.day} {_FRENCH_MONTHS[day.month - 1]} {day.year}"
    return f"{day:%B} {day.day}, {day.year}"


@dataclass(frozen=True)
class RenderedNewsletter:
    subject: str
    html: str
    text: str


class NewsletterRenderer:
    def __init__(self) -> None:
        self._env = Environment(
            loader=PackageLoader("weekly_ai_newsletter", "rendering/templates"),
            autoescape=select_autoescape(enabled_extensions=("html.j2",), default=False),
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def render(self, newsletter: Newsletter) -> RenderedNewsletter:
        labels = LABELS[newsletter.language]
        date_label = format_issue_date(newsletter.issue_date, newsletter.language)
        subject = f"{labels['title']} — {date_label}"
        context = {
            "newsletter": newsletter,
            "labels": labels,
            "subject": subject,
            "date_label": date_label,
            "max_total": MAX_TOTAL,
        }
        return RenderedNewsletter(
            subject=subject,
            html=self._env.get_template("newsletter.html.j2").render(context),
            text=self._env.get_template("newsletter.txt.j2").render(context),
        )
