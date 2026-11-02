"""Composition root: the only place that knows about concrete adapters."""

from __future__ import annotations

import httpx

from weekly_ai_newsletter.adapters.arxiv import ArxivPaperSource
from weekly_ai_newsletter.adapters.claude import ClaudeClient
from weekly_ai_newsletter.adapters.github_releases import GithubReleasesSource, RoutingFeedSource
from weekly_ai_newsletter.adapters.github_trending import GithubTrendingSource
from weekly_ai_newsletter.adapters.json_history import JsonHistoryStore
from weekly_ai_newsletter.adapters.resend import ResendEmailSender
from weekly_ai_newsletter.adapters.rss import RssFeedSource
from weekly_ai_newsletter.config import AppConfig, Secrets
from weekly_ai_newsletter.pipeline import Delivery, Dependencies, NewsletterPipeline


def build_pipeline(config: AppConfig, secrets: Secrets, http: httpx.Client) -> NewsletterPipeline:
    settings = config.settings
    github_token = secrets.github_token.get_secret_value() if secrets.github_token else None
    deps = Dependencies(
        papers=ArxivPaperSource(http),
        feeds=RoutingFeedSource(
            rss=RssFeedSource(http), releases=GithubReleasesSource(http, token=github_token)
        ),
        trending=GithubTrendingSource(http, languages=settings.repos.trending_languages),
        llm=ClaudeClient.from_api_key(
            secrets.anthropic_api_key.get_secret_value(),
            model=settings.llm.model,
            max_tokens=settings.llm.max_tokens,
        ),
        history=JsonHistoryStore(settings.history_path),
    )
    delivery = None
    if secrets.email is not None:
        delivery = Delivery(
            sender=ResendEmailSender(http, api_key=secrets.email.resend_api_key.get_secret_value()),
            from_address=secrets.email.sender_email,
            to_address=secrets.email.recipient_email,
        )
    return NewsletterPipeline(config, deps, delivery=delivery)
