"""Optional Responses API adapter. No model calls without explicit consent/config."""

import json
import os
import urllib.error
import urllib.request
from typing import Protocol

from pydantic import BaseModel

from .registry import instructions


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
            "instructions": instructions(role_id) + "\nSTAGE: " + stage,
            "input": [{"role": "user", "content": data}],
            "max_output_tokens": 3500,
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
            if result.get("status") != "completed":
                raise ProviderError("Model returned an incomplete response")
            text = "".join(part["text"] for item in result.get("output", [])
                           if item.get("type") == "message"
                           for part in item.get("content", [])
                           if part.get("type") == "output_text")
            return contract.model_validate_json(text).model_dump(mode="json")
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError, TypeError) as exc:
            # Do not log responses/requests or secrets in this exception.
            raise ProviderError("Model request failed or output did not match its contract") from exc
