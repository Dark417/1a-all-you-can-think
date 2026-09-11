"""Guestbook API -- a deliberately small, cloud-native service used to
demonstrate Kubernetes across three environments (raw / EKS / GKE).

It is intentionally "12-factor":
  * configuration comes from environment variables (injected by ConfigMaps &
    Secrets in Kubernetes),
  * it exposes separate **liveness** (`/healthz`) and **readiness** (`/readyz`)
    probes so Kubernetes can manage its lifecycle correctly,
  * it logs to stdout,
  * it stores state in MongoDB (never on local disk), so the Pods stay
    stateless and horizontally scalable.

Swagger UI is served at `/docs`.
"""
from __future__ import annotations

import os
import socket
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from pymongo import MongoClient
from pymongo.errors import PyMongoError

# --------------------------------------------------------------------------- #
# Configuration (everything overridable via environment).
# --------------------------------------------------------------------------- #
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DB = os.getenv("MONGODB_DB", "guestbook")
APP_VERSION = os.getenv("APP_VERSION", "1.0.0")
# A label so you can SEE which Pod served a request when you scale to N replicas.
POD_NAME = os.getenv("POD_NAME", socket.gethostname())

_state: dict[str, object] = {"client": None, "ready": False}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Connect lazily and tolerantly: the Pod must start even if Mongo is not up
    # yet, so the *readiness* probe (not liveness) gates traffic.
    _state["client"] = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=1500)
    yield
    client = _state.get("client")
    if client:
        client.close()


app = FastAPI(
    title="Kubernetes + MongoDB Guestbook",
    version=APP_VERSION,
    description=(
        "A tiny stateless service backed by MongoDB, used to demonstrate "
        "Kubernetes primitives (Deployments, Services, probes, HPA, config) "
        "identically across a local `kind` cluster, AWS EKS, and GCP GKE."
    ),
    lifespan=lifespan,
)


def _col():
    return _state["client"][MONGODB_DB]["messages"]


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #
class MessageIn(BaseModel):
    author: str = Field(..., examples=["ada"])
    text: str = Field(..., examples=["hello from kubernetes"])


class Message(MessageIn):
    id: str
    created_at: str
    served_by: str


# --------------------------------------------------------------------------- #
# Health probes -- the distinction matters in Kubernetes.
# --------------------------------------------------------------------------- #
@app.get("/healthz", tags=["health"], summary="Liveness: is the process alive?")
def healthz():
    """Liveness probe. Must NOT depend on external systems -- if it fails,
    Kubernetes *restarts* the container. We only report that the process runs."""
    return {"status": "alive", "pod": POD_NAME, "version": APP_VERSION}


@app.get("/readyz", tags=["health"], summary="Readiness: can we serve traffic?")
def readyz():
    """Readiness probe. SHOULD check dependencies -- if it fails, Kubernetes
    removes the Pod from Service endpoints (no restart) until Mongo is back."""
    try:
        _state["client"].admin.command("ping")
        return {"status": "ready", "pod": POD_NAME, "mongo": "up"}
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail=f"mongo unavailable: {exc}")


# --------------------------------------------------------------------------- #
# Business endpoints
# --------------------------------------------------------------------------- #
@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/docs")


@app.get("/api/messages", response_model=list[Message], tags=["messages"])
def list_messages(limit: int = 50):
    docs = _col().find().sort("_id", -1).limit(limit)
    return [_to_message(d) for d in docs]


@app.post("/api/messages", response_model=Message, status_code=201, tags=["messages"])
def add_message(body: MessageIn):
    doc = {"author": body.author, "text": body.text, "created_at": datetime.now(timezone.utc)}
    try:
        res = _col().insert_one(doc)
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail=f"write failed: {exc}")
    doc["_id"] = res.inserted_id
    return _to_message(doc)


@app.get("/api/info", tags=["messages"], summary="Which Pod am I talking to?")
def info():
    """Handy when scaled to many replicas -- refresh and watch `served_by` change
    as the Service load-balances across Pods."""
    return {
        "pod": POD_NAME,
        "version": APP_VERSION,
        "mongodb_db": MONGODB_DB,
        "now": datetime.now(timezone.utc).isoformat(),
    }


def _to_message(d) -> Message:
    return Message(
        id=str(d["_id"]),
        author=d["author"],
        text=d["text"],
        created_at=d["created_at"].isoformat()
        if isinstance(d["created_at"], datetime)
        else str(d["created_at"]),
        served_by=POD_NAME,
    )
