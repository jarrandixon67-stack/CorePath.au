from email.utils import formataddr

import httpx


class DeliveryUnknown(Exception):
    pass


def invitation(business, row, settings):
    unsubscribe = settings.public_base_url + "/unsubscribe/" + row["unsubscribe_token"]
    name = " ".join(business["name"].split())
    text = (
        f"Hello {name} team,\n\n"
        "We’re developing CorePath, a platform helping people turn knowledge into practical improvements in their lives. "
        "Your business has met the requirements in our current evidence-based partner assessment, and we’d like to invite you to discuss becoming a CorePath partner.\n\n"
        "Our proposed commercial model is a 10% commission on agreed CorePath-generated transactions, subject to a written partner agreement. "
        "Partnership does not buy a better rating or guarantee referrals. This invitation does not create an agreement.\n\n"
        "If you’re interested, reply to this email and we’ll explain the requirements and next steps. "
        "You can also reply to request the basis of the assessment or correct our information.\n\n"
        f"{settings.sender_legal_name}\n{settings.sender_contact}\n"
        f"Contact: {settings.reply_to}\n\n"
        f"To stop partner invitations, use this free opt-out: {unsubscribe}\n"
    )
    return {
        "from": formataddr((settings.sender_legal_name, settings.sender_email)),
        "to": [row["recipient"]],
        "reply_to": settings.reply_to,
        "subject": "An invitation to discuss a CorePath business partnership",
        "text": text,
        "headers": {
            "List-Unsubscribe": "<" + unsubscribe + ">",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        },
    }


class ResendTransport:
    def __init__(self, api_key, *, client=None):
        self.api_key = api_key
        self.client = client

    def send(self, payload, idempotency_key):
        def request(client):
            response = client.post(
                "https://api.resend.com/emails",
                json=payload,
                headers={
                    "Authorization": "Bearer " + self.api_key,
                    "Idempotency-Key": "corepath-partner/" + idempotency_key,
                },
            )
            response.raise_for_status()
            result = response.json()
            provider_id = result.get("id")
            if not isinstance(provider_id, str) or not 1 <= len(provider_id) <= 200:
                raise ValueError("Email provider did not acknowledge delivery acceptance")
            return provider_id

        try:
            if self.client:
                return request(self.client)
            with httpx.Client(timeout=25, follow_redirects=False) as client:
                return request(client)
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise DeliveryUnknown(
                "Provider acknowledgement is uncertain; do not resend automatically"
            ) from exc


def process_one(repo, subject, settings, *, transport=None):
    reserved = repo.reserve(subject, settings, invitation)
    if not reserved or "blocked" in reserved:
        return reserved or {"state": "idle"}
    return repo.deliver_reserved(
        subject, reserved, settings, transport or ResendTransport(settings.email_api_key)
    )
