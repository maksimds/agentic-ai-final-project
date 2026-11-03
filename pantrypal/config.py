"""Model configuration: Azure OpenAI through APIM. No native OpenAI key is used.

Values come from a local .env file (never committed). If your class setup
used a different header or variable name, change it here once and every
agent picks it up.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from openai import AsyncAzureOpenAI
from agents import OpenAIChatCompletionsModel, set_tracing_disabled

load_dotenv()

# Tracing uploads to OpenAI's platform by default, which would need a native key.
set_tracing_disabled(True)

REQUIRED = ["AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_DEPLOYMENT"]


def get_model() -> OpenAIChatCompletionsModel:
    missing = [name for name in REQUIRED if not os.getenv(name)]
    if missing:
        raise RuntimeError(
            f"Missing settings: {', '.join(missing)}. Copy .env.example to .env and fill it in."
        )

    key = os.environ["AZURE_OPENAI_API_KEY"]
    client = AsyncAzureOpenAI(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],  # the APIM gateway URL
        api_key=key,
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21"),
        # Most APIM gateways accept the subscription key in this header.
        default_headers={"Ocp-Apim-Subscription-Key": key},
    )
    return OpenAIChatCompletionsModel(
        model=os.environ["AZURE_OPENAI_DEPLOYMENT"],
        openai_client=client,
    )
