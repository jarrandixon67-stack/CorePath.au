import json
from typing import Protocol, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from coordinator.models import CollaborationPlan, Plan, Synthesis
from coordinator.policy import INSTRUCTIONS
from coordinator.settings import Settings
from specialists.models import BudgetExceeded, InvalidEvidence, ProviderUnavailable

T = TypeVar("T", bound=BaseModel)


class Provider(Protocol):
    def plan(self, context: dict) -> Plan: ...
    def collaborate(self, context: dict) -> CollaborationPlan: ...
    def synthesise(self, context: dict) -> Synthesis: ...


class OpenAIProvider:
    def __init__(self, settings: Settings):
        self.settings = settings

    def _request(self, stage: str, context: dict, contract: type[T]) -> T:
        if not self.settings.openai_api_key or not self.settings.model:
            raise ProviderUnavailable
        data = json.dumps({"stage": stage, **context})
        if len(data) > self.settings.max_context_chars:
            raise BudgetExceeded
        try:
            with httpx.Client(
                timeout=self.settings.model_timeout_seconds, follow_redirects=False
            ) as client:
                response = client.post(
                    "https://api.openai.com/v1/responses",
                    headers={"Authorization": "Bearer " + self.settings.openai_api_key},
                    json={
                        "model": self.settings.model,
                        "instructions": INSTRUCTIONS,
                        "input": [{"role": "user", "content": data}],
                        "store": False,
                        "max_output_tokens": self.settings.max_output_tokens,
                        "text": {
                            "format": {
                                "type": "json_schema",
                                "name": "coordinator_" + stage,
                                "strict": True,
                                "schema": contract.model_json_schema(),
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
                raise InvalidEvidence("Incomplete Coordinator output")
            text = "".join(
                part["text"]
                for item in payload.get("output", [])
                if item.get("type") == "message"
                for part in item.get("content", [])
                if part.get("type") == "output_text"
            )
            return contract.model_validate_json(text)
        except (ValidationError, KeyError, TypeError, AttributeError) as exc:
            raise InvalidEvidence("Coordinator output did not match its contract") from exc

    def plan(self, context):
        return self._request("plan", context, Plan)

    def collaborate(self, context):
        return self._request("collaboration", context, CollaborationPlan)

    def synthesise(self, context):
        return self._request("synthesis", context, Synthesis)
