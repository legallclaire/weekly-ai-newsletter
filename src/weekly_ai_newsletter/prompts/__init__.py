"""System prompts, kept as templates so they can be reviewed and versioned like code."""

from jinja2 import Environment, PackageLoader, StrictUndefined

LANGUAGE_NAMES = {"fr": "French", "en": "English"}

_env = Environment(
    loader=PackageLoader("weekly_ai_newsletter", "prompts"),
    undefined=StrictUndefined,
    autoescape=False,
    keep_trailing_newline=True,
)


def render_prompt(name: str, **context: object) -> str:
    return _env.get_template(name).render(**context)
