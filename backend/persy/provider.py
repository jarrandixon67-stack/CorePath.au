import json

import httpx
from pydantic import ValidationError

from persy.models import Reply
from persy.policy import INSTRUCTIONS
from persy.settings import Settings
from specialists.models import BudgetExceeded, InvalidEvidence, ProviderUnavailable


class OpenAIProvider:
    def __init__(self, settings: Settings):
        self.settings = settings

    def reply(self, context):
        settings = self.settings
        if not settings.openai_api_key or not settings.model:
            raise ProviderUnavailable
        data = json.dumps(context)
        if len(data) > settings.max_context_chars:
            raise BudgetExceeded
        try:
            with httpx.Client(
                timeout=settings.model_timeout_seconds, follow_redirects=False
            ) as client:
                response = client.post(
                    "https://api.openai.com/v1/responses",
                    headers={"Authorization": "Bearer " + settings.openai_api_key},
                    json={
                        "model": settings.model,
                        "instructions": INSTRUCTIONS,
                        "input": [{"role": "user", "content": data}],
                        "store": False,
                        "max_output_tokens": settings.max_output_tokens,
                        "text": {
                            "format": {
                                "type": "json_schema",
                                "name": "persy_reply",
                                "strict": True,
                                "schema": Reply.model_json_schema(),
                            }
                        },
                    },
                )
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderUnavailable from exc
        try:
            if payload.get("status") != "completed":
                raise InvalidEvidence("Incomplete Persy output")
            text = "".join(
                part["text"]
                for item in payload.get("output", [])
                if item.get("type") == "message"
                for part in item.get("content", [])
                if part.get("type") == "output_text"
            )
            return Reply.model_validate_json(text)
        except (ValidationError, KeyError, TypeError, AttributeError) as exc:
            raise InvalidEvidence("Persy output failed its contract") from exc
