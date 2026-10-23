"""Pick the Claude backend: Amazon Bedrock when AWS_BEARER_TOKEN_BEDROCK is set, else the Anthropic API.

Model names in .env stay short (claude-haiku-4-5); on Bedrock they are mapped to inference-profile IDs.
"""
from __future__ import annotations

import os

from anthropic import AsyncAnthropic, AsyncAnthropicBedrock

BEDROCK_IDS: dict[str, str] = {
    "claude-haiku-4-5": "global.anthropic.claude-haiku-4-5-20251001-v1:0",
    "claude-sonnet-4-5": "global.anthropic.claude-sonnet-4-5-20250929-v1:0",
}


def using_bedrock() -> bool:
    return bool(os.environ.get("AWS_BEARER_TOKEN_BEDROCK"))


def provider_name() -> str:
    return f"bedrock:{os.environ.get('AWS_REGION', '?')}" if using_bedrock() else "anthropic"


def resolve_model(name: str) -> str:
    """Short name -> Bedrock ID when on Bedrock. Full IDs (containing 'anthropic.') pass through."""
    if using_bedrock() and "anthropic." not in name:
        return BEDROCK_IDS.get(name, name)
    return name


def request_kwargs() -> dict[str, object]:
    """Extra per-request args. Bedrock rejects the SDK's default API version for models older than 4.7,
    so send the classic Bedrock body version there."""
    if using_bedrock():
        return {"extra_body": {"anthropic_version": "bedrock-2023-05-31"}}
    return {}


def make_async_client(api_key: str | None = None) -> AsyncAnthropic | AsyncAnthropicBedrock:
    if using_bedrock():
        return AsyncAnthropicBedrock(aws_region=os.environ.get("AWS_REGION"))
    return AsyncAnthropic(api_key=api_key) if api_key else AsyncAnthropic()
