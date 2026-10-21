import time
from pydantic import ValidationError
import httpx
from . import usage
from .providers import ProviderError
from .schemas import ApplicationResponse
from .security import decrypt_credential, validate_target


async def invoke(job, client, recorder):
    cfg, case = job["config"], job["case"]
    target = cfg["target_snapshot"]
    validate_target(target["url"])
    headers = {
        "X-EvalScope-Run-ID": job["run_id"],
        "X-EvalScope-Case-ID": case["case_id"],
        "traceparent": recorder.traceparent(),
    }
    if target.get("credential_id"):
        try:
            headers["Authorization"] = "Bearer " + decrypt_credential(
                target["credential_id"], job["project_id"]
            )
        except ValueError:
            raise ProviderError("credential_unavailable") from None
    identity = usage.begin("application", target["name"], cfg, source="application")
    try:
        # References and expected answers are never sent to the application.
        response = await client.post(
            target["url"],
            headers=headers,
            json={
                "input": case["input"],
                "configuration": {
                    "model": cfg["model"],
                    "temperature": cfg["temperature"],
                    "prompt_template": cfg["prompt_template"],
                },
            },
            follow_redirects=False,
        )
        if response.status_code >= 300:
            rejected = response.status_code in {400, 401, 403, 404, 422, 429}
            category = (
                "rate_limit"
                if response.status_code == 429
                else (
                    "application_server"
                    if response.status_code >= 500
                    else "application_rejected"
                )
            )
            usage.finish(
                identity,
                "REJECTED" if rejected else "UNCERTAIN",
                error=category,
                billable=not rejected,
            )
            raise ProviderError(
                category, response.status_code == 429 or response.status_code >= 500
            )
        try:
            if len(response.content) > 2_000_000:
                raise ValueError("Oversized response")
            data = ApplicationResponse.model_validate(response.json())
        except (ValidationError, ValueError):
            usage.finish(identity, "UNCERTAIN", error="malformed_application_response")
            raise ProviderError("malformed_application_response") from None
        for event in data.usage:
            rates = usage.prices("application", event.model, cfg)
            child = usage.begin(
                event.scope,
                event.model,
                cfg,
                source="application",
                parent_id=identity,
                rates=rates,
            )
            usage.finish(child, "REPORTED", event.input_tokens, event.output_tokens)
        usage.finish(
            identity,
            "REPORTED" if data.usage else "UNREPORTED",
            billable=not bool(data.usage),
        )
        recorder.import_application_spans(data.spans)
        return data
    except (httpx.TimeoutException, httpx.NetworkError):
        usage.finish(identity, "UNCERTAIN", error="application_timeout")
        raise ProviderError("application_timeout", True) from None
    except BaseException:
        usage.finish(identity, "UNCERTAIN", error="application_interrupted")
        raise
