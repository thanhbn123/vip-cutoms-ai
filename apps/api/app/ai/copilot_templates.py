"""Placeholder; implemented in G09."""

from app.ai.base import CopilotAnswer


def answer(question, context, provider):  # pragma: no cover - replaced in G09
    return CopilotAnswer(answer="Copilot not implemented yet", intent="unknown", sources=[], reasoning=[], provider=provider)
