"""Send a text prompt to Amazon Nova or Anthropic Claude through Bedrock."""

from __future__ import annotations

import argparse
import os
import sys

import boto3
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError


DEFAULT_REGION = "ap-southeast-2"
MODEL_IDS = {
    "nova-2-lite": "global.amazon.nova-2-lite-v1:0",
    "opus-4.6": "au.anthropic.claude-opus-4-6-v1",
    "opus-4.5": "global.anthropic.claude-opus-4-5-20251101-v1:0",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Call Amazon Nova or Claude through the Bedrock Converse API."
    )
    parser.add_argument(
        "prompt",
        nargs="?",
        default="Reply with OK",
        help="Text to send to Claude.",
    )
    parser.add_argument(
        "--model",
        default=(
            os.getenv("CLAUDE_BEDROCK_MODEL_ID", "").strip()
            if os.getenv("CLAUDE_CODE_USE_BEDROCK", "false").strip().lower() in {"1", "true", "yes", "on"}
            else os.getenv("BEDROCK_MODEL_ID", "nova-2-lite")
        ),
        help=(
            "Model alias (nova-2-lite, opus-4.6, or opus-4.5), profile ID, "
            "or inference profile ARN."
        ),
    )
    parser.add_argument(
        "--region",
        default=os.getenv("AWS_REGION", DEFAULT_REGION),
        help=f"AWS region (default: {DEFAULT_REGION}).",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=1024,
        help="Maximum response tokens (default: 1024).",
    )
    return parser.parse_args()


def invoke_model(
    prompt: str,
    model: str,
    region: str,
    max_tokens: int,
) -> str:
    if not prompt.strip():
        raise ValueError("The prompt must not be empty.")

    if os.getenv("BEDROCK_AUTH_MODE", "iam").strip().lower() == "iam":
        os.environ.pop("AWS_BEARER_TOKEN_BEDROCK", None)

    model_id = MODEL_IDS.get(model, model)
    client = boto3.client("bedrock-runtime", region_name=region)
    request = {
        "modelId": model_id,
        "messages": [
            {
                "role": "user",
                "content": [{"text": prompt}],
            }
        ],
        "inferenceConfig": {
            "maxTokens": max_tokens,
        },
    }
    if model_id.startswith(("au.anthropic.", "global.anthropic.")):
        request["additionalModelRequestFields"] = {"top_k": 250}
    response = client.converse(**request)

    content = response["output"]["message"]["content"]
    return "\n".join(block["text"] for block in content if "text" in block)


def main() -> int:
    args = parse_args()

    try:
        result = invoke_model(
            prompt=args.prompt,
            model=args.model,
            region=args.region,
            max_tokens=args.max_tokens,
        )
    except NoCredentialsError:
        print(
            "AWS credentials were not found. Run `aws configure` or set "
            "`AWS_BEARER_TOKEN_BEDROCK`.",
            file=sys.stderr,
        )
        return 1
    except ClientError as exc:
        error = exc.response.get("Error", {})
        code = error.get("Code", "ClientError")
        message = error.get("Message", str(exc))
        print(f"Bedrock request failed [{code}]: {message}", file=sys.stderr)
        return 1
    except (BotoCoreError, ValueError) as exc:
        print(f"Bedrock request failed: {exc}", file=sys.stderr)
        return 1

    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
