class NewsletterError(Exception):
    """Base class for expected, reportable failures."""


class ConfigError(NewsletterError):
    """Invalid or missing configuration or secrets."""


class SourceError(NewsletterError):
    """A content source could not be fetched or parsed."""


class LLMOutputError(NewsletterError):
    """The LLM did not return valid structured output."""


class EmailDeliveryError(NewsletterError):
    """The email provider rejected or failed to receive the message."""


class PipelineError(NewsletterError):
    """The pipeline cannot produce or publish a newsletter."""


class StateError(NewsletterError):
    """Persisted state (the send history) cannot be read."""


def describe_error(exc: Exception) -> str:
    """A short error description for the public job summary.

    Our own errors carry messages written for it; third-party messages can hold URLs with
    query strings or API response bodies, so only their status and host are kept (the full
    error stays in the run log).
    """
    if isinstance(exc, NewsletterError):
        return f"{type(exc).__name__}: {exc}"
    # HTTP client errors (httpx, the Anthropic SDK) expose `.response` and `.request`.
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if status is None:
        return type(exc).__name__
    host = getattr(getattr(getattr(exc, "request", None), "url", None), "host", None)
    return f"HTTP {status} from {host}" if host else f"HTTP {status}"
