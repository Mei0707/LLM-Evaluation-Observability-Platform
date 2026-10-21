"""Controlled HTTP provider for resilience tests; no external inference."""

import asyncio
import re
from fastapi import FastAPI

app = FastAPI()


@app.post("/v1/chat/completions")
async def completion(body: dict):
    await asyncio.sleep(0.5)
    match = re.search(r"Question (\d+)", body["messages"][0]["content"])
    answer = "Answer " + match.group(1) if match else "Answer"
    return {
        "choices": [{"message": {"content": answer}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }
