# Application evaluation contract

Register an application under **Applications**, then select it in **New evaluation**. Administrators must allow its exact hostname in `EVALSCOPE_TARGET_HOSTS`. Targets are immutable, scoped to a project, and frozen into each run. Bearer credentials reference encrypted project credentials; no secret is copied into the run configuration.

```sh
docker compose --profile applications up -d
```

The included target URL is `http://reference-app:8080/evaluate`. Its source is [examples/rag_app.py](../examples/rag_app.py). Use the local development deployment for this HTTP example; HTTPS deployments require HTTPS application endpoints.

The platform POSTs:

```json
{
  "input": "The evaluation question",
  "configuration": {
    "model": "your-model-id",
    "temperature": 0,
    "prompt_template": "Answer {input} from retrieved evidence."
  }
}
```

It also sends `traceparent`, `X-EvalScope-Run-ID`, and `X-EvalScope-Case-ID`. Expected answers, labeled relevant IDs, reference contexts, mock outputs, and evaluation metadata are withheld. Applications must run their own retrieval/tools; the platform evaluates the IDs and contexts they actually return.

Return a JSON object:

```json
{
  "output": "The application response",
  "retrieved_document_ids": ["doc-001"],
  "contexts": ["Actually retrieved source passage"],
  "spans": [],
  "usage": [
    {"scope": "generation", "model": "your-model-id", "input_tokens": 100, "output_tokens": 30}
  ]
}
```

Spans use the metadata-only online span schema: operation `request`, `retrieval`, `prompt`, `generation`, `tool`, or `evaluation`; a 16-character lowercase hex span ID; optional parent ID; UTC Unix start/end timestamps; OK/ERROR status; and allowlisted attributes. Parents must form an acyclic forest within the supplied list. The platform imports stages into the same OTel trace and records their actual supplied timestamps. Remote clock skew can affect the timeline; synchronize application and worker clocks.

`usage` may report generation, embedding, judge, and tool stages. Each entry is stored with source `application`, distinct from direct provider evidence. Freeze `application_prices` by model ID to estimate cost. Omitting usage or pricing leaves the estimate incomplete. Application-reported usage is trusted application telemetry, not independently verified billing. A parent request envelope is non-billable when component usage is returned, preventing double counting.

Redirects are rejected; authentication is never forwarded to a redirected endpoint. 429 and 5xx responses can retry. Invalid contracts fail explicitly. Calls have durable usage intents before dispatch; timeouts, interruptions, and uncertain server errors stay visible. The response is capped at 2 MB for validation, and returned content follows the run's capture policy.
