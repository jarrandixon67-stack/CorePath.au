"""Optional Responses API adapter. No model calls without explicit consent/config."""

import json
import os
from http.client import HTTPException
import urllib.error
import urllib.request
from typing import Protocol

from pydantic import BaseModel

from .registry import instructions


def output_budget(stage: str) -> int:
    # Bounded output allowances. A cap is not proof of cost or output quality;
    # truncated/invalid structured results continue to fail closed, without retry.
    return {
        "select_necessary_specialists": 700,
        "initial_assessment": 1600,
        "peer_review": 1600,
        "present_reviewed_team_draft": 900,
    }.get(stage, 3500)


class ProviderError(RuntimeError):
    pass


class Provider(Protocol):
    def generate(self, role_id: str, stage: str, context: dict, contract: type[BaseModel]) -> dict:
        ...


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class OpenAIProvider:
    """Fixed endpoint; no arbitrary model tools, redirects, retries or source fetching."""

    def __init__(self, *, allow_model_processing: bool, timeout: float = 40):
        if not allow_model_processing:
            raise PermissionError("Explicit permission for external model processing is required")
        self.api_key = os.environ.get("OPENAI_API_KEY", "")
        self.model = os.environ.get("COREPATH_MODEL", "")
        if not self.api_key or not self.model:
            raise ProviderError("Set OPENAI_API_KEY and COREPATH_MODEL before model execution")
        if not 1 <= timeout <= 60:
            raise ValueError("Model timeout must be between 1 and 60 seconds")
        self.timeout = timeout

    def generate(self, role_id, stage, context, contract):
        data = json.dumps(context, ensure_ascii=False)
        if len(data) > 70000:
            raise ProviderError("Context exceeds the bounded input budget")
        schema = contract.model_json_schema()
        # OpenAI strict schemas require every object property to be required.
        # All output-contract fields above have no defaults.
        body = json.dumps({
            "model": self.model, "store": False,
            "instructions": instructions(role_id, stage),
            "input": [{"role": "user", "content": data}],
            "max_output_tokens": output_budget(stage),
            "text": {"format": {"type": "json_schema", "name": "corepath_output",
                                "strict": True, "schema": schema}},
        }).encode()
        request = urllib.request.Request(
            "https://api.openai.com/v1/responses", data=body, method="POST",
            headers={"Authorization": "Bearer " + self.api_key,
                     "Content-Type": "application/json"},
        )
        try:
            with urllib.request.build_opener(NoRedirect).open(request, timeout=self.timeout) as response:
                payload = response.read(300001)
            if len(payload) > 300000:
                raise ProviderError("Model response exceeded the response budget")
            result = json.loads(payload)
            if not isinstance(result, dict):
                raise ValueError("Expected a response object")
            if result.get("status") != "completed":
                raise ProviderError("Model returned an incomplete response")
            items = result.get("output")
            if not isinstance(items, list):
                raise ValueError("Expected an output list")
            texts = []
            for item in items:
                if not isinstance(item, dict):
                    raise ValueError("Invalid output item")
                if item.get("type") != "message":
                    continue
                if not isinstance(item.get("content"), list):
                    raise ValueError("Invalid message content")
                for part in item["content"]:
                    if not isinstance(part, dict):
                        raise ValueError("Invalid content item")
                    if part.get("type") == "output_text":
                        if not isinstance(part.get("text"), str):
                            raise ValueError("Invalid output text")
                        texts.append(part["text"])
            text = "".join(texts)
            return contract.model_validate_json(text).model_dump(mode="json")
        except (OSError, HTTPException, ValueError, KeyError, TypeError) as exc:
            # Do not log responses/requests or secrets in this exception.
            raise ProviderError("Model request failed or output did not match its contract") from exc
