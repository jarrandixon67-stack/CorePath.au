"""First-party sign-in for a single-instance, invitation-only trial."""

import hashlib
import hmac
import json
import secrets
import time
from functools import lru_cache
from pathlib import Path
from threading import BoundedSemaphore, Lock
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from service_gateway.main import mint

COOKIE = "__Host-corepath-trial"


class TrialSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TRIAL_")
    origin: str | None = None
    accounts: str | None = None
    member_signing_key: str | None = None
    administrator: str | None = None
    specialist_url: str | None = None

    def model_post_init(self, _context):
        for value in (self.origin, self.specialist_url):
            if value:
                url = urlsplit(value)
                if (
                    url.scheme != "https"
                    or not url.hostname
                    or url.username
                    or url.password
                    or url.query
                    or url.fragment
                    or url.path
                ):
                    raise ValueError("Trial requires fixed HTTPS origins")


@lru_cache
def config():
    return TrialSettings()


@lru_cache
def accounts():
    settings = config()
    if (
        not settings.origin
        or not settings.origin.startswith("https://")
        or not settings.member_signing_key
    ):
        raise HTTPException(503, "Trial sign-in is unavailable")

    def unique_object(pairs):
        result = dict(pairs)
        if len(result) != len(pairs):
            raise ValueError
        return result

    try:
        data = json.loads(settings.accounts or "", object_pairs_hook=unique_object)
        if not isinstance(data, dict) or not 1 <= len(data) <= 20:
            raise ValueError
        result = {}
        for subject, verifier in data.items():
            if (
                not isinstance(subject, str)
                or not 1 <= len(subject) <= 100
                or not subject.isascii()
                or not all(char.isalnum() or char in "-_" for char in subject)
            ):
                raise ValueError
            salt, digest = verifier.split(":")
            salt, digest = bytes.fromhex(salt), bytes.fromhex(digest)
            if len(salt) != 16 or len(digest) != 32:
                raise ValueError
            result[subject] = (salt, digest)
        return result
    except (ValueError, TypeError, AttributeError) as exc:
        raise HTTPException(503, "Trial sign-in is unavailable") from exc


def password_digest(password, salt):
    return hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1, dklen=32)


class Login(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=256)


lock = Lock()
attempts = {}
requests = {}
password_slots = BoundedSemaphore(2)
sessions = {}
dummy = (secrets.token_bytes(16), secrets.token_bytes(32))


def require_origin(request: Request):
    if request.headers.get("origin") != config().origin or not config().origin:
        raise HTTPException(403, "Trial requests must come from this site")


def login(request, body):
    require_origin(request)
    allowed = accounts()
    with lock:
        minute = int(time.monotonic() // 60)
        if attempts.get("minute") != minute:
            attempts.clear()
            attempts["minute"] = minute
        username = body.username if body.username in allowed else ""
        identities = ("total", ("member", username))
        if attempts.get("total", 0) >= 60 or attempts.get(identities[1], 0) >= 8:
            raise HTTPException(429, "Try again in a minute")
        for identity in identities:
            attempts[identity] = attempts.get(identity, 0) + 1
    salt, digest = allowed.get(body.username, dummy)
    if not password_slots.acquire(blocking=False):
        raise HTTPException(429, "Try again shortly")
    try:
        valid_password = hmac.compare_digest(password_digest(body.password, salt), digest)
    finally:
        password_slots.release()
    if not valid_password or body.username not in allowed:
        raise HTTPException(401, "Invalid trial credentials")
    return body.username


def new_session(subject):
    token = secrets.token_urlsafe(32)
    with lock:
        for prior, (owner, _) in list(sessions.items()):
            if owner == subject:
                sessions.pop(prior)
        sessions[token] = (subject, time.monotonic() + 3600)
    return token


def end_session(request: Request):
    with lock:
        sessions.pop(request.cookies.get(COOKIE, ""), None)


def session_subject(request: Request):
    allowed = accounts()
    with lock:
        token = request.cookies.get(COOKIE, "")
        current = sessions.get(token)
        if current and current[1] > time.monotonic() and current[0] in allowed:
            return current[0]
        sessions.pop(token, None)
    raise HTTPException(401, "Sign in to the trial")


def browser_capability(request, scope, purpose):
    if request.method not in ("GET", "HEAD"):
        require_origin(request)
    subject = session_subject(request)
    with lock:
        minute = int(time.monotonic() // 60)
        if requests.get("minute") != minute:
            requests.clear()
            requests["minute"] = minute
        identity = ("member", subject)
        if requests.get(identity, 0) >= 45:
            raise HTTPException(429, "Too many trial requests. Try again in a minute.")
        requests[identity] = requests.get(identity, 0) + 1
    return mint(
        config(),
        subject=subject,
        actor="member",
        domain="*",
        scope=scope,
        purpose=purpose,
        audience="corepath-persy",
        request_id=uuid4(),
        expires=int(time.time()) + 240,
        issuer="corepath-member-gateway",
        signing_key=config().member_signing_key,
    )["capability"]


ASSETS = Path(__file__).with_name("trial_ui")
