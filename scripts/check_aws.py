"""Check that AWS credentials and Bedrock model access are actually working.

    python scripts/check_aws.py

Reports exactly which of the three prerequisites is missing, and what to do
about it, instead of failing with a raw botocore traceback halfway through a
rehearsal.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

OK = "  [ok]  "
BAD = "  [--]  "


def main() -> int:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError

    from replay import models

    print("\n  Replay - AWS preflight\n")

    # 1. Credentials -------------------------------------------------------
    session = boto3.Session()
    region = session.region_name or os.environ.get("AWS_REGION") or models.REGION
    creds = session.get_credentials()

    if creds is None:
        print(BAD + "No AWS credentials found.")
        print("         Set AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_DEFAULT_REGION,")
        print("         then open a NEW terminal (setx does not affect the current one).")
        return 1

    print(OK + f"Credentials found (access key ...{creds.access_key[-4:]})")
    print(OK + f"Region: {region}")

    # 2. Who am I ----------------------------------------------------------
    try:
        identity = session.client("sts", region_name=region).get_caller_identity()
        print(OK + f"Authenticated as {identity['Arn'].split('/')[-1]}")
    except (ClientError, NoCredentialsError) as exc:
        print(BAD + f"Credentials were rejected by AWS: {exc}")
        print("         The key may be inactive, deleted, or mistyped.")
        return 1

    # 3. Which Claude models exist in this region --------------------------
    try:
        listing = session.client("bedrock", region_name=region).list_foundation_models(
            byProvider="anthropic"
        )
        available = sorted({m["modelId"] for m in listing.get("modelSummaries", [])})
        print(OK + f"Bedrock reachable - {len(available)} Anthropic model(s) listed in {region}")
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        print(BAD + f"Could not list Bedrock models ({code}).")
        if code == "AccessDeniedException":
            print("         The IAM user needs the AmazonBedrockFullAccess policy.")
        return 1

    # 4. Can we actually invoke the configured model? ----------------------
    print()
    failed = False
    for role, model_id in models.ROLE_MODELS.items():
        status = _probe(session, region, model_id)
        failed = failed or status.startswith("[--]")
        print(f"  {status}  {role:<9} {model_id}")

    if not failed:
        print("\n  All good. Run:  python scripts/rehearse.py \"<your change>\"\n")
        return 0

    print(
        "\n  USE-CASE FORM NOT SUBMITTED means exactly that: open the Bedrock"
        "\n  console -> Model catalog -> any Anthropic model, and fill in the"
        "\n  Anthropic use case details form. It is a one-time, account-wide"
        "\n  step and takes about 15 minutes to take effect.\n"
    )
    return 1


def _probe(session, region: str, model_id: str) -> str:
    """Attempt the smallest possible real call against one model."""
    from botocore.exceptions import ClientError

    client = session.client("bedrock-runtime", region_name=region)
    try:
        client.converse(
            modelId=model_id,
            messages=[{"role": "user", "content": [{"text": "hi"}]}],
            inferenceConfig={"maxTokens": 1},
        )
        return "[ok]  "
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        message = exc.response["Error"].get("Message", "")
        low = message.lower()

        # Bedrock puts the actionable part in the message, not the code, and the
        # codes are actively misleading -- the use-case gate arrives as
        # ResourceNotFoundException and account gating as AccessDenied. Always
        # surface the message.
        if "use case details" in low:
            return "[--]  USE-CASE FORM NOT SUBMITTED -"
        if "not available for this account" in low:
            return "[--]  not enabled for this account -"
        if "legacy" in low:
            return "[--]  legacy model, retired -"
        if code == "ValidationException" and "inference profile" in low:
            return "[--]  needs an inference profile (REPLAY_MODEL_PREFIX=us.) -"
        return f"[--]  {code}: {message[:60]} -"
    except Exception as exc:  # noqa: BLE001
        return f"[--]  {type(exc).__name__} -"


if __name__ == "__main__":
    raise SystemExit(main())
