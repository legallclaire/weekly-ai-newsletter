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
