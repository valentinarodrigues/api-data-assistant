#!/usr/bin/env python3
"""
FastAPI backend — spec-driven, unified multi-API assistant.

Endpoints:
  GET  /health  — Ollama connectivity check
  GET  /fields  — all fields across all APIs (each tagged with api_id/api_name)
  POST /ask     — stream answer tokens via SSE (searches across all APIs)
"""

import json
import os
import re
from pathlib import Path
from typing import AsyncIterator

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from spec_parser import parse_spec

load_dotenv(Path(__file__).parent / ".env")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

APIS_CONFIG   = Path("apis.json")
OLLAMA_URL    = "http://localhost:11434"
DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")


def _resolve(value: str) -> str:
    """Replace ${VAR_NAME} with the corresponding env var."""
    return re.sub(r"\$\{(\w+)\}", lambda m: os.getenv(m.group(1), m.group(0)), value)

SYSTEM_PROMPT = """\
You are an API documentation assistant. Users want to know whether specific data \
is available and, if so, which API provides it.

You have been given the full OpenAPI specifications for multiple APIs. \
Each API section is clearly labelled.

When answering:
- Start with **YES** or **NO**.
- State which API contains the field (e.g. "Available in the **Orders API**").
- Cite the exact field path in backticks (e.g. `customer.email`).
- Briefly describe what the field contains, using the spec description.
- Note whether it is required or optional/nullable.
- If data spans multiple APIs, mention all of them.
- If the data is not available in any API, say so clearly.
- Keep answers concise. Use markdown formatting.
"""

# ---------------------------------------------------------------------------
# Load all APIs at startup
# ---------------------------------------------------------------------------

def _load_all() -> tuple[list[dict], str]:
    registry = json.loads(APIS_CONFIG.read_text())["apis"]
    all_fields: list[dict] = []
    sections:   list[str]  = []

    for api in registry:
        source = _resolve(api["spec"])
        print(f"  Loading spec: {source}")
        fields, context = parse_spec(source)

        for f in fields:
            all_fields.append({**f, "api_id": api["id"], "api_name": api["name"]})

        sections.append(
            f"{'=' * 60}\n"
            f"API: {api['name']}\n"
            f"{'=' * 60}\n"
            f"{context}"
        )

    combined_context = "\n\n".join(sections)
    return all_fields, combined_context


print("Loading API specs…")
ALL_FIELDS, COMBINED_CONTEXT = _load_all()
print(f"Ready — {len(ALL_FIELDS)} fields loaded across all APIs.")

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="API Data Assistant")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class AskRequest(BaseModel):
    question: str
    model:    str = DEFAULT_MODEL


@app.get("/health")
async def health():
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get(f"{OLLAMA_URL}/api/tags")
            r.raise_for_status()
            names = [m["name"] for m in r.json().get("models", [])]
        return {"status": "ok", "models": names}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Ollama unavailable: {e}")


@app.get("/fields")
async def get_fields():
    return {"fields": ALL_FIELDS}


@app.post("/ask")
async def ask(body: AskRequest):
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="question is required")

    prompt = f"{COMBINED_CONTEXT}\n\nUser question: {body.question}"

    async def stream_tokens() -> AsyncIterator[str]:
        payload = {
            "model":  body.model,
            "prompt": prompt,
            "system": SYSTEM_PROMPT,
            "stream": True,
        }
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                async with client.stream("POST", f"{OLLAMA_URL}/api/generate", json=payload) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        chunk = json.loads(line)
                        token = chunk.get("response", "")
                        if token:
                            yield f"data: {json.dumps({'token': token})}\n\n"
                        if chunk.get("done"):
                            yield "data: [DONE]\n\n"
                            return
        except httpx.ConnectError:
            yield f"data: {json.dumps({'error': 'Ollama is not running. Start it with: ollama serve'})}\n\n"

    return StreamingResponse(stream_tokens(), media_type="text/event-stream")
