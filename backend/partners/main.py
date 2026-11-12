import re
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from psycopg import Error
from psycopg.errors import UniqueViolation
from psycopg_pool import ConnectionPool, PoolTimeout

from partners.discovery import DiscoveryUnavailable, discover
from partners.mail import process_one
from partners.models import (
    AssessmentRequest,
    BatchRequest,
    BusinessSeed,
    Contact,
    DiscoveryRequest,
    Evidence,
    InvitationRequest,
    Policy,
    Review,
    Suppression,
)
from partners.repository import (
    CONTACT,
    POLICY,
    QUEUE,
    READ,
    RESEARCH,
    SEND,
    SUPPRESS,
    VERIFY,
    Conflict,
    Denied,
    Missing,
    Repository,
)
from partners.research import ResearchUnavailable, propose
from partners.runtime import evaluate_batch
from partners.settings import get_settings
from specialists.models import Capability
from specialists.security import validate_capability


@asynccontextmanager
async def lifespan(app):
    settings = get_settings()
    pool = (
        ConnectionPool(settings.database_url, min_size=1, max_size=5, open=True)
        if settings.database_url
        else None
    )
    if pool:
        pool.wait(timeout=10)
    app.state.partner_pool = pool
    try:
        yield
    finally:
        if pool:
            pool.close()


app = FastAPI(title="CorePath Partner Bot", version="0.1.0", lifespan=lifespan)
bearer = HTTPBearer(auto_error=False)


@app.exception_handler(Denied)
async def denied(request, exc):
    from fastapi.responses import JSONResponse

    return JSONResponse({"detail": str(exc)}, status_code=403)


@app.exception_handler(Conflict)
async def conflict(request, exc):
    from fastapi.responses import JSONResponse

    return JSONResponse({"detail": str(exc)}, status_code=409)


@app.exception_handler(Missing)
async def missing(request, exc):
    from fastapi.responses import JSONResponse

    return JSONResponse({"detail": str(exc)}, status_code=404)


@app.exception_handler(UniqueViolation)
async def duplicate(request, exc):
    from fastapi.responses import JSONResponse

    return JSONResponse(
        {"detail": "This business, evidence or recipient already exists"}, status_code=409
    )


@app.exception_handler(Error)
@app.exception_handler(PoolTimeout)
async def unavailable(request, exc):
    from fastapi.responses import JSONResponse

    return JSONResponse({"detail": "Partner database operation unavailable"}, status_code=503)


def repository(request: Request):
    pool = getattr(request.app.state, "partner_pool", None)
    if not pool:
        raise HTTPException(503, "Partner database is not configured")
    return Repository(pool)


def capability(action):
    def dependency(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
        settings = get_settings()
        return validate_capability(
            credentials.credentials if credentials else None,
            public_key=settings.gateway_public_key,
            issuer=settings.gateway_issuer,
            audience=settings.gateway_audience,
            actor="partner_gateway",
            scope=action,
            purpose="business_partnerships",
            domain="*",
        )

    return dependency


RepoDependency = Annotated[Repository, Depends(repository)]
ReadCap = Annotated[Capability, Depends(capability(READ))]
ResearchCap = Annotated[Capability, Depends(capability(RESEARCH))]
VerifyCap = Annotated[Capability, Depends(capability(VERIFY))]
PolicyCap = Annotated[Capability, Depends(capability(POLICY))]
ContactCap = Annotated[Capability, Depends(capability(CONTACT))]
QueueCap = Annotated[Capability, Depends(capability(QUEUE))]
SendCap = Annotated[Capability, Depends(capability(SEND))]
SuppressCap = Annotated[Capability, Depends(capability(SUPPRESS))]


@app.get("/health/live")
def live():
    return {"status": "alive"}


@app.get("/health/ready")
def ready(repo: RepoDependency):
    if not get_settings().gateway_public_key:
        raise HTTPException(503, "Partner authentication is not configured")
    with repo.pool.connection() as c:
        c.execute("SELECT 1 FROM partner_actors LIMIT 1")
    return {"status": "ready", "email_delivery_enabled": get_settings().email_delivery_enabled}


@app.post("/v1/businesses", status_code=201)
def ingest(seed: BusinessSeed, cap: ResearchCap, repo: RepoDependency):
    return repo.ingest(cap.subject, seed)


@app.get("/v1/businesses")
def businesses(
    cap: ReadCap,
    repo: RepoDependency,
    after: UUID | None = None,
    limit: int = Query(50, ge=1, le=100),
):
    return repo.list_businesses(cap.subject, after=after, limit=limit)


@app.get("/v1/businesses/{business_id}")
def business(business_id: UUID, cap: ReadCap, repo: RepoDependency):
    return repo.read_business(cap.subject, business_id)


@app.post("/v1/discovery")
def discovery(body: DiscoveryRequest, cap: ResearchCap, repo: RepoDependency):
    repo.authorize(cap.subject, RESEARCH)
    try:
        seeds = discover(body)
    except DiscoveryUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    return {
        "businesses": [repo.ingest(cap.subject, seed) for seed in seeds],
        "coverage": "One bounded OpenStreetMap search; not every business or verified registry data.",
    }


@app.post("/v1/policies", status_code=201)
def policy(body: Policy, cap: PolicyCap, repo: RepoDependency):
    return repo.create_policy(cap.subject, body)


@app.post("/v1/policies/{policy_id}/review")
def policy_review(policy_id: UUID, body: Review, cap: PolicyCap, repo: RepoDependency):
    return repo.approve_policy(cap.subject, policy_id, body)


@app.post("/v1/businesses/{business_id}/evidence", status_code=201)
def evidence(business_id: UUID, body: Evidence, cap: ResearchCap, repo: RepoDependency):
    return repo.add_evidence(cap.subject, business_id, body)


@app.post("/v1/evidence/{evidence_id}/review")
def evidence_review(evidence_id: UUID, body: Review, cap: VerifyCap, repo: RepoDependency):
    return repo.review_evidence(cap.subject, evidence_id, body)


@app.post("/v1/businesses/{business_id}/assess")
def assessment(
    business_id: UUID,
    body: AssessmentRequest,
    cap: ResearchCap,
    repo: RepoDependency,
):
    return repo.assess(cap.subject, business_id, body.policy_id)


@app.post("/v1/businesses/{business_id}/research")
def research(business_id: UUID, cap: ResearchCap, repo: RepoDependency):
    repo.authorize(cap.subject, RESEARCH)
    try:
        draft = propose(repo.read_business(cap.subject, business_id), get_settings())
    except ResearchUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    return {
        "review_required": True,
        "draft": draft.model_dump(mode="json"),
        "note": "Draft interpretations do not verify evidence, alter an assessment or enable outreach.",
    }


@app.post("/v1/businesses/{business_id}/contact")
def contact(business_id: UUID, body: Contact, cap: ContactCap, repo: RepoDependency):
    return repo.save_contact(cap.subject, business_id, body)


@app.post("/v1/businesses/{business_id}/invitations", status_code=201)
def queue(business_id: UUID, body: InvitationRequest, cap: QueueCap, repo: RepoDependency):
    return repo.enqueue(cap.subject, business_id, body.assessment_id, get_settings())


@app.post("/v1/assessment-batches")
def assessment_batch(
    body: BatchRequest, cap: ResearchCap, queue_cap: QueueCap, repo: RepoDependency
):
    return evaluate_batch(repo, cap.subject, body.business_ids, body.policy_id, get_settings())


@app.get("/v1/invitations")
def invitations(cap: ReadCap, repo: RepoDependency):
    return repo.list_invitations(cap.subject)


@app.post("/v1/suppressions", status_code=204)
def suppress(body: Suppression, cap: SuppressCap, repo: RepoDependency):
    repo.suppress(cap.subject, body.email, body.reason)


@app.post("/v1/process-one")
def process(cap: SendCap, repo: RepoDependency):
    repo.consume_dispatch_capability(cap)
    return process_one(repo, cap.subject, get_settings())


UNSUB_HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'none'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'",
}


@app.get("/unsubscribe/{token}", response_class=HTMLResponse)
def unsubscribe_page(token: str):
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
        raise HTTPException(404, "Not found")
    return HTMLResponse(
        '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Stop CorePath partner invitations</title><main><h1>Stop partner invitations</h1><p>Confirm below to stop business partnership invitations to this address.</p><form method="post"><button type="submit">Stop invitations</button></form></main></html>',
        headers=UNSUB_HEADERS,
    )


@app.post("/unsubscribe/{token}", response_class=HTMLResponse)
def unsubscribe(token: str, repo: RepoDependency):
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
        raise HTTPException(404, "Not found")
    repo.unsubscribe(token)
    return HTMLResponse(
        '<!doctype html><html lang="en"><meta charset="utf-8"><title>Request received</title><main><h1>Your request has been received.</h1><p>Any matching address is excluded from future partner invitations. No sign-in is needed.</p></main></html>',
        headers=UNSUB_HEADERS,
    )
