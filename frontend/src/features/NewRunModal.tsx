import type { Target, Credential } from "../pages/Applications";
import React, { useState } from "react";
import { Loader2, Play, SlidersHorizontal } from "lucide-react";
import {
  post,
  type Case,
  type Dataset,
  type Experiment,
  type Prompt,
  type Run,
} from "../api";
import { ErrorBox, Button, Modal } from "../components/ui";
import { useData } from "../hooks/useData";

export function NewRunModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (id: string) => void;
}) {
  const datasets = useData<Dataset[]>("datasets", "/datasets"),
    prompts = useData<Prompt[]>("prompts", "/prompts");
  const [name, setName] = useState(""),
    [version, setVersion] = useState(""),
    [prompt, setPrompt] = useState(""),
    [provider, setProvider] = useState("mock"),
    [model, setModel] = useState("mock-balanced"),
    [evaluators, setEvaluators] = useState(["exact_match"]),
    [concurrency, setConcurrency] = useState(5),
    [capture, setCapture] = useState(false),
    [judge, setJudge] = useState(""),
    [embedding, setEmbedding] = useState(""),
    [temperature, setTemperature] = useState(0),
    [attempts, setAttempts] = useState(3),
    [timeout, setTimeoutValue] = useState(30),
    [threshold, setThreshold] = useState(0.8),
    [inputCost, setInputCost] = useState(""),
    [outputCost, setOutputCost] = useState(""),
    [targetId, setTargetId] = useState(""),
    [credentialId, setCredentialId] = useState(""),
    [judgeInput, setJudgeInput] = useState(""),
    [judgeOutput, setJudgeOutput] = useState(""),
    [embeddingCost, setEmbeddingCost] = useState(""),
    [appPrices, setAppPrices] = useState("{}"),
    [error, setError] = useState<unknown>(null),
    [busy, setBusy] = useState(false);
  const targets = useData<Target[]>("targets", "/targets");
  const credentials = useData<Credential[]>("credentials", "/credentials");
  const versionId = version || datasets.data?.[0]?.versions[0]?.id || "",
    promptId = prompt || prompts.data?.[0]?.id || "";
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const experiment = await post<Experiment>("/experiments", {
        name,
        config: {
          dataset_version_id: versionId,
          prompt_version_id: promptId,
          provider,
          model,
          target_id: targetId || null,
          provider_credential_id: credentialId || null,
          application_prices: JSON.parse(appPrices),
          judge_input_cost_per_million: judgeInput === "" ? null : +judgeInput,
          judge_output_cost_per_million:
            judgeOutput === "" ? null : +judgeOutput,
          embedding_cost_per_million:
            embeddingCost === "" ? null : +embeddingCost,
          evaluators,
          concurrency,
          capture_content: capture,
          judge_model: judge,
          embedding_model: embedding,
          temperature,
          max_attempts: attempts,
          timeout_seconds: timeout,
          pass_threshold: threshold,
          input_cost_per_million: inputCost === "" ? null : +inputCost,
          output_cost_per_million: outputCost === "" ? null : +outputCost,
        },
      });
      const run = await post<Run>("/runs", { experiment_id: experiment.id });
      onCreated(run.id);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal
      title="New evaluation"
      subtitle="Freeze your configuration. Measure what changes."
      onClose={onClose}
      wide
    >
      <form onSubmit={submit} className="form-body">
        <ErrorBox error={error || datasets.error || prompts.error} />
        <label>
          Experiment name
          <input
            required
            maxLength={120}
            placeholder="e.g. Support assistant · prompt v2"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <label>
          Evaluation application
          <select
            aria-label="Evaluation application"
            value={targetId}
            onChange={(e) => {
              setTargetId(e.target.value);
              setProvider(e.target.value ? "openai_compatible" : "mock");
              setModel(
                e.target.value ? "application-default" : "mock-balanced",
              );
            }}
          >
            <option value="">Direct model generation</option>
            {targets.data?.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </label>
        <div className="form-row">
          <label>
            Dataset version
            <select
              aria-label="Dataset version"
              required
              value={versionId}
              onChange={(e) => setVersion(e.target.value)}
            >
              <option value="" disabled>
                Select a version
              </option>
              {datasets.data?.flatMap((d) =>
                d.versions.map((v) => (
                  <option key={v.id} value={v.id}>
                    {d.name} · v{v.number} ({v.case_count} cases)
                  </option>
                )),
              )}
            </select>
          </label>
          <label>
            Prompt version
            <select
              aria-label="Prompt version"
              required
              value={promptId}
              onChange={(e) => setPrompt(e.target.value)}
            >
              <option value="" disabled>
                Select a prompt
              </option>
              {prompts.data?.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
        </div>
        {(!datasets.data?.length || !prompts.data?.length) &&
          !datasets.isLoading && (
            <div className="info-box">
              Create a dataset and a prompt in their workspace pages first.
            </div>
          )}
        <div className="form-row">
          <label>
            Provider
            <select
              value={provider}
              onChange={(e) => {
                setProvider(e.target.value);
                setModel(e.target.value === "mock" ? "mock-balanced" : "");
                setEvaluators(["exact_match"]);
              }}
            >
              <option value="mock">Mock · deterministic / no API cost</option>
              <option value="openai_compatible">
                OpenAI-compatible · live
              </option>
            </select>
          </label>
          <label>
            Model
            {provider === "mock" ? (
              <select
                aria-label="Model"
                value={model}
                onChange={(e) => setModel(e.target.value)}
              >
                <option value="mock-balanced">mock-balanced</option>
                <option value="mock-precise">mock-precise</option>
                <option value="mock-regressed">mock-regressed</option>
              </select>
            ) : (
              <input
                required
                placeholder="Your configured model ID"
                value={model}
                onChange={(e) => setModel(e.target.value)}
              />
            )}
          </label>
        </div>
        <fieldset>
          <legend>Evaluation methods</legend>
          <div className="evaluator-options">
            {[
              "exact_match",
              "retrieval",
              "semantic_similarity",
              "llm_judge",
            ].map((v) => (
              <label
                key={v}
                className={`check-option ${evaluators.includes(v) ? "checked" : ""}`}
              >
                <input
                  type="checkbox"
                  checked={evaluators.includes(v)}
                  disabled={
                    provider === "mock" &&
                    ["semantic_similarity", "llm_judge"].includes(v)
                  }
                  onChange={() =>
                    setEvaluators(
                      evaluators.includes(v)
                        ? evaluators.filter((x) => x !== v)
                        : [...evaluators, v],
                    )
                  }
                />
                <span>{v.replaceAll("_", " ")}</span>
              </label>
            ))}
          </div>
          <p className="field-help">
            Embedding similarity and LLM judging require a configured live
            provider. Retrieval requires labeled document IDs.
          </p>
        </fieldset>
        {evaluators.includes("llm_judge") && (
          <label>
            Judge model ID
            <input
              required
              value={judge}
              onChange={(e) => setJudge(e.target.value)}
            />
          </label>
        )}
        {evaluators.includes("semantic_similarity") && (
          <label>
            Embedding model ID
            <input
              required
              value={embedding}
              onChange={(e) => setEmbedding(e.target.value)}
            />
          </label>
        )}
        <div className="form-row">
          <label>
            Concurrency
            <input
              type="number"
              min={1}
              max={32}
              value={concurrency}
              onChange={(e) => setConcurrency(+e.target.value)}
            />
          </label>
          <label>
            Pass threshold (0–1)
            <input
              type="number"
              step="0.05"
              min={0}
              max={1}
              value={threshold}
              onChange={(e) => setThreshold(+e.target.value)}
            />
          </label>
        </div>
        <details className="advanced">
          <summary>
            <SlidersHorizontal size={15} />
            Generation & retry settings
          </summary>
          <div className="form-row">
            <label>
              Temperature
              <input
                type="number"
                step="0.1"
                min={0}
                max={2}
                value={temperature}
                onChange={(e) => setTemperature(+e.target.value)}
              />
            </label>
            <label>
              Maximum attempts
              <input
                type="number"
                min={1}
                max={5}
                value={attempts}
                onChange={(e) => setAttempts(+e.target.value)}
              />
            </label>
            <label>
              Case timeout (s)
              <input
                type="number"
                min={0.01}
                step="0.01"
                max={120}
                value={timeout}
                onChange={(e) => setTimeoutValue(+e.target.value)}
              />
            </label>
          </div>
          <div className="form-row">
            <label>
              Input cost / million tokens ($)
              <input
                type="number"
                min={0}
                step="0.01"
                value={inputCost}
                onChange={(e) => setInputCost(e.target.value)}
              />
            </label>
            <label>
              Output cost / million tokens ($)
              <input
                type="number"
                min={0}
                step="0.01"
                value={outputCost}
                onChange={(e) => setOutputCost(e.target.value)}
              />
            </label>
          </div>
          <p className="field-help">
            Leave unknown rates blank. Zero is an explicitly free rate; the
            ledger includes retries and all evaluation stages.
          </p>
          <div className="form-row">
            <label>
              Judge input / million ($)
              <input
                type="number"
                min={0}
                step="0.01"
                value={judgeInput}
                onChange={(e) => setJudgeInput(e.target.value)}
              />
            </label>
            <label>
              Judge output / million ($)
              <input
                type="number"
                min={0}
                step="0.01"
                value={judgeOutput}
                onChange={(e) => setJudgeOutput(e.target.value)}
              />
            </label>
            <label>
              Embedding / million ($)
              <input
                type="number"
                min={0}
                step="0.01"
                value={embeddingCost}
                onChange={(e) => setEmbeddingCost(e.target.value)}
              />
            </label>
          </div>
          <label>
            Encrypted provider credential
            <select
              value={credentialId}
              onChange={(e) => setCredentialId(e.target.value)}
            >
              <option value="">Server environment credential</option>
              {credentials.data
                ?.filter((c) => c.active)
                .map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name} · v{c.version}
                  </option>
                ))}
            </select>
          </label>
          {targetId && (
            <label>
              Application model prices · JSON
              <textarea
                rows={3}
                className="code-input"
                value={appPrices}
                onChange={(e) => setAppPrices(e.target.value)}
                placeholder={
                  '{"your-model":{"input_cost_per_million":2,"output_cost_per_million":4}}'
                }
              />
            </label>
          )}
          <p className="field-help">
            All stages and retries are recorded. Missing prices or provider
            usage remain explicitly unknown.
          </p>
        </details>
        <label className="capture-option">
          <input
            type="checkbox"
            checked={capture}
            onChange={(e) => setCapture(e.target.checked)}
          />
          <span>
            <strong>Capture response content</strong>
            <small>
              Store model output for inspection and human review. Content is
              omitted from trace attributes.
            </small>
          </span>
        </label>
        <div className="form-footer">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            disabled={busy || !versionId || !promptId || !evaluators.length}
          >
            {busy ? <Loader2 className="spin" size={16} /> : <Play size={16} />}
            Start evaluation
          </Button>
        </div>
      </form>
    </Modal>
  );
}
