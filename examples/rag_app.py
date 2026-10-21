"""A real HTTP retrieval/tool pipeline with an explicit extractive demo generator.

Its knowledge base is independent of evaluation request payloads. Replace the
extractive generation stage with your application model without changing the
evaluation contract.
"""

import asyncio
import json
from pathlib import Path
import re
import time
import uuid
from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI(title="EvalScope reference RAG application")


@app.get("/health")
def health():
    return {"status": "ok", "generator": "extractive-reference-v1"}


documents = json.loads(
    (Path(__file__).resolve().parents[1] / "datasets/review/knowledge.json").read_text()
)


class Input(BaseModel):
    input: str = Field(min_length=1, max_length=20000)
    configuration: dict = Field(default_factory=dict)


@app.post("/evaluate")
async def evaluate(body: Input):
    spans = []

    def span(name, started, **attributes):
        spans.append(
            {
                "name": name,
                "span_id": uuid.uuid4().hex[:16],
                "started_at": started,
                "ended_at": time.time(),
                "status": "OK",
                "attributes": attributes,
            }
        )

    started = time.time()
    tokens = set(re.findall(r"[a-z0-9]+", body.input.casefold()))

    def similarity(document):
        words = set(
            re.findall(
                r"[a-z0-9]+", (document["title"] + " " + document["text"]).casefold()
            )
        )
        return len(tokens & words) / max(1, len(tokens | words))

    retrieved = sorted(documents, key=similarity, reverse=True)[:3]
    span("retrieval", started, document_count=len(retrieved))
    started = time.time()
    await asyncio.to_thread(
        (Path(__file__).resolve().parents[1] / "datasets/review/knowledge.json").stat
    )
    span("tool", started)
    started = time.time()
    # This extractive baseline is deliberately limited, not an LLM-quality claim.
    output = (
        retrieved[0]["text"]
        if retrieved and similarity(retrieved[0]) > 0.1
        else "Insufficient evidence."
    )
    span(
        "generation",
        started,
        model="extractive-reference-v1",
        input_tokens=0,
        output_tokens=0,
    )
    return {
        "output": output,
        "retrieved_document_ids": [d["id"] for d in retrieved],
        "contexts": [d["text"] for d in retrieved],
        "spans": spans,
        "usage": [
            {
                "scope": "generation",
                "model": "extractive-reference-v1",
                "input_tokens": 0,
                "output_tokens": 0,
            }
        ],
    }
