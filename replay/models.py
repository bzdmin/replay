"""Model configuration.

Each agent role gets its own model binding so that reasoning-heavy work and
mechanical work can be priced differently. Everything is overridable by
environment variable, because the right answer depends on how much Bedrock
credit is left.
"""

from __future__ import annotations

import os

from strands.models import BedrockModel

# Bedrock model identifiers.
#
# Every current-generation Anthropic model on Bedrock is INFERENCE_PROFILE-only
# - there is no on-demand throughput for the bare "anthropic.<id>" form, and
# invoking it returns AccessDeniedException rather than a validation error.
# So the regional profile prefix is the default, not an escape hatch.
# Use "global." for cross-region routing, or "" only for a legacy ON_DEMAND id.
_PREFIX = os.environ.get("REPLAY_MODEL_PREFIX", "us.")

# Bedrock gates its newest models per account. On a fresh account the 5-series
# (Opus 5, Sonnet 5, Fable 5) and Opus 4.7/4.8 return
#   "anthropic.claude-opus-5 is not available for this account"
# which surfaces as AccessDeniedException. Run scripts/check_aws.py to see what
# the current account can actually invoke; these are the best available there.
OPUS = f"{_PREFIX}anthropic.claude-opus-4-6-v1"
SONNET = f"{_PREFIX}anthropic.claude-sonnet-4-6"
HAIKU = f"{_PREFIX}anthropic.claude-haiku-4-5-20251001-v1:0"

REGION = os.environ.get("AWS_REGION", "us-east-1")

# Per-role model assignment. Defaults to the strongest available model
# everywhere; set REPLAY_ECONOMY=1 to move the two mechanical roles onto
# Sonnet, which cuts credit burn at some cost to recall.
# Any role can be pinned directly with REPLAY_MODEL_IMPACT / _SCENARIO /
# _VERIFIER, which takes precedence over everything else.
_ECONOMY = os.environ.get("REPLAY_ECONOMY") == "1"

ROLE_MODELS = {
    "impact": SONNET if _ECONOMY else OPUS,
    "scenario": SONNET if _ECONOMY else OPUS,
    # The verifier is the one agent that must not be cheapened. Its whole job
    # is finding what the others missed.
    "verifier": OPUS,
}

for _role in tuple(ROLE_MODELS):
    _override = os.environ.get(f"REPLAY_MODEL_{_role.upper()}")
    if _override:
        ROLE_MODELS[_role] = _override


def model_for(role: str, *, max_tokens: int = 8000) -> BedrockModel:
    """Build the Bedrock model binding for one agent role."""
    if role not in ROLE_MODELS:
        raise KeyError(f"unknown agent role: {role!r}")

    return BedrockModel(
        region_name=REGION,
        model_id=ROLE_MODELS[role],
        max_tokens=max_tokens,
    )


def describe() -> str:
    """Human-readable summary of the active model configuration."""
    mode = "economy" if _ECONOMY else "standard"
    lines = [f"region={REGION}  mode={mode}"]
    lines += [f"  {role:<9} {model}" for role, model in ROLE_MODELS.items()]
    return "\n".join(lines)
