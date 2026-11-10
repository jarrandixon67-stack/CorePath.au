import json
from typing import Protocol

import httpx
from pydantic import ValidationError

from specialists.models import InvalidEvidence, Proposal, ProviderUnavailable
from specialists.registry import Specialist
from specialists.settings import Settings


class Provider(Protocol):
    def propose(self, specialist: Specialist, context: dict) -> Proposal: ...


class OpenAIProvider:
    def __init__(self, settings: Settings):
        self.settings = settings

    def propose(self, specialist: Specialist, context: dict) -> Proposal:
        model = self.settings.model_for(specialist.domain)
        if not model or not self.settings.openai_api_key:
            raise ProviderUnavailable
        try:
            with httpx.Client(timeout=self.settings.model_timeout_seconds) as client:
                response = client.post(
                    "https://api.openai.com/v1/responses",
                    headers={"Authorization": "Bearer " + self.settings.openai_api_key},
                    json={
                        "model": model,
                        "instructions": specialist.instructions,
                        "input": [{"role": "user", "content": json.dumps(context)}],
                        "store": False,
                        "max_output_tokens": self.settings.max_output_tokens,
                        "text": {
                            "format": {
                                "type": "json_schema",
                                "name": "specialist_findings",
                                "strict": True,
                                "schema": Proposal.model_json_schema(),
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
                raise InvalidEvidence("The model response was incomplete.")
            text = "".join(
                part["text"]
                for item in payload.get("output", [])
                if item.get("type") == "message"
                for part in item.get("content", [])
                if part.get("type") == "output_text"
            )
            return Proposal.model_validate_json(text)
        except (ValidationError, KeyError, TypeError, AttributeError) as exc:
            raise InvalidEvidence("The response did not match the specialist contract.") from exc
