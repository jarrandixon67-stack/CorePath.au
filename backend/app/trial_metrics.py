"""Aggregate trial metrics. Never record request bodies, identities or exceptions."""

import json
import logging
import os
import secrets
from collections import defaultdict
from contextlib import contextmanager
from threading import Lock
from time import perf_counter

from fastapi import Header, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

lock = Lock()
counters = defaultdict(lambda: defaultdict(int))
logger = logging.getLogger("uvicorn.error")


def record(operation, elapsed, *, error=False, usage=None, rate=None):
    event = {
        "calls": 1,
        "errors": int(error),
        "total_ms": round(elapsed * 1000),
    }
    if isinstance(usage, dict):
        for key in ("input_tokens", "output_tokens"):
            count = usage.get(key)
            if type(count) is int and count >= 0:
                event[key] = count
        if len(event) == 5 and rate:
            event["estimated_usd_micros"] = round(
                event["input_tokens"] * rate[0] + event["output_tokens"] * rate[1]
            )
    with lock:
        for name, value in event.items():
            counters[operation][name] += value
    logger.info(json.dumps({"event": "trial_metric", "operation": operation, **event}))


@contextmanager
def activation(operation):
    started = perf_counter()
    completed = False
    try:
        yield
        completed = True
    finally:
        record(operation, perf_counter() - started, error=not completed)


@contextmanager
def model_call(operation, service):
    started = perf_counter()
    measurement = {}
    try:
        yield measurement
    finally:
        rates = os.getenv("TRIAL_" + service + "_USD_PER_MILLION", "").split(",")
        try:
            rate = tuple(float(part) for part in rates)
            if len(rate) != 2 or not all(0 <= value <= 1000 for value in rate):
                rate = None
        except ValueError:
            rate = None
        record(
            operation,
            perf_counter() - started,
            error=not measurement.get("valid"),
            usage=measurement.get("usage"),
            rate=rate,
        )


def snapshot():
    with lock:
        return {operation: dict(values) for operation, values in sorted(counters.items())}


def install_endpoint(app, service):
    @app.middleware("http")
    async def safe_metrics(request, call_next):
        started = perf_counter()
        try:
            response = await call_next(request)
        except Exception:  # noqa: BLE001 - never log potentially private exceptions
            response = JSONResponse({"detail": "CorePath service unavailable"}, status_code=500)
        if request.method in ("POST", "PUT", "DELETE"):
            record(service + ".write", perf_counter() - started, error=response.status_code >= 400)
        response.headers["Cache-Control"] = "no-store"
        return response

    if RequestValidationError not in app.exception_handlers:

        @app.exception_handler(RequestValidationError)
        async def invalid_request(_request, _exc):
            return JSONResponse({"detail": "Check the submitted fields"}, status_code=422)

    @app.get("/internal/trial-metrics")
    def internal_metrics(authorization: str | None = Header(default=None)):
        expected = os.getenv("TRIAL_METRICS_TOKEN", "")
        supplied = authorization or ""
        if len(expected) < 48 or not secrets.compare_digest(
            supplied.encode(), ("Bearer " + expected).encode()
        ):
            raise HTTPException(404, "Not found")
        return snapshot()
