import json
from typing import Protocol
from uuid import UUID

import httpx
from fastapi import HTTPException
from pydantic import ValidationError

from coordinator.models import Assignment, SpecialistResult
from coordinator.settings import Settings
from specialists.models import InvalidEvidence, ProviderUnavailable
from specialists.security import validate_capability


class SpecialistClient(Protocol):
    def dispatch(self, assignment: Assignment, task_id: UUID) -> SpecialistResult: ...


def response_json(client, url, headers, body, max_bytes):
    with client.stream("POST", url, headers=headers, json=body) as response:
        response.raise_for_status()
        chunks, length = [], 0
        for chunk in response.iter_bytes():
            length += len(chunk)
            if length > max_bytes:
                raise InvalidEvidence("Service response exceeded the bounded contract")
            chunks.append(chunk)
        return json.loads(b"".join(chunks))


class HTTPSpecialistClient:
    """Uses a restricted external token exchange; never holds a signing key."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def dispatch(self, assignment: Assignment, task_id: UUID) -> SpecialistResult:
        settings = self.settings
        if not all(
            (
                settings.specialist_url,
                settings.exchange_url,
                settings.exchange_token,
                settings.specialist_public_key,
            )
        ):
            raise ProviderUnavailable
        try:
            with httpx.Client(
                timeout=min(settings.specialist_timeout_seconds, 10), follow_redirects=False
            ) as client:
                exchange = response_json(
                    client,
                    settings.exchange_url,
                    {"Authorization": "Bearer " + settings.exchange_token},
                    {
                        "domain": assignment.domain.value,
                        "purpose": "dispatch",
                        "scope": ["specialist:dispatch"],
                        "request_id": str(task_id),
                    },
                    16384,
                )
            if (
                not isinstance(exchange, dict)
                or set(exchange) != {"capability"}
                or not isinstance(exchange["capability"], str)
                or len(exchange["capability"]) > 8192
            ):
                raise InvalidEvidence("Invalid gateway exchange envelope")
            token = exchange["capability"]
            capability = validate_capability(
                token,
                public_key=settings.specialist_public_key,
                issuer=settings.specialist_issuer,
                audience=settings.specialist_audience,
                actor="coordinator_ai",
                scope="specialist:dispatch",
                purpose="dispatch",
                domain=assignment.domain.value,
            )
            if capability.subject != settings.service_subject or capability.request_id != str(
                task_id
            ):
                raise InvalidEvidence("The exchanged capability names another service or request")
            with httpx.Client(
                timeout=settings.specialist_timeout_seconds, follow_redirects=False
            ) as client:
                payload = response_json(
                    client,
                    settings.specialist_url.rstrip("/")
                    + f"/v1/specialists/{assignment.domain.value}/tasks",
                    {"Authorization": "Bearer " + token},
                    assignment.task.model_dump(mode="json"),
                    262144,
                )
            result = SpecialistResult.model_validate(payload)
            if result.specialist != assignment.domain:
                raise InvalidEvidence("The specialist returned another discipline's result")
            return result
        except HTTPException as exc:
            raise ProviderUnavailable from exc
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            if isinstance(exc, ValidationError):
                raise InvalidEvidence("The specialist returned an invalid result") from exc
            raise ProviderUnavailable from exc
