import { UsagePanel } from "../features/UsagePanel";
import React, { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  CheckCircle2,
  ChevronLeft,
  Clock3,
  Code2,
  Coins,
  Download,
  FlaskConical,
  GitBranch,
  Loader2,
  Play,
  Plus,
  Search,
  Sparkles,
  X,
} from "lucide-react";
import {
  api,
  post,
  pct,
  ms,
  date,
  money,
  terminal,
  type Case,
  type Experiment,
  type Result,
  type Run,
} from "../api";
import {
  Badge,
  ErrorBox,
  Loading,
  Button,
  download,
  PageHeading,
  Stat,
  RunTable,
  Pagination,
} from "../components/ui";
import { useData } from "../hooks/useData";

export function ExperimentsPage({
  onNew,
  onRun,
  notify,
}: {
  onNew: () => void;
  onRun: (id: string) => void;
  notify: (s: string) => void;
}) {
  const [tab, setTab] = useState("runs"),
    [search, setSearch] = useState(""),
    [status, setStatus] = useState("all"),
    [offset, setOffset] = useState(0),
    [busy, setBusy] = useState("");
  const runs = useQuery({
    queryKey: ["runs", offset],
    queryFn: () =>
      api<{ items: Run[]; total: number }>(`/runs?offset=${offset}&limit=50`),
    refetchInterval: 2000,
  });
  const experiments = useData<Experiment[]>("experiments", "/experiments");
  const [error, setError] = useState<unknown>(null);
  const client = useQueryClient();
  const rerun = async (experiment: Experiment) => {
    setBusy(experiment.id);
    setError(null);
    try {
      const run = await post<Run>("/runs", { experiment_id: experiment.id });
      void client.invalidateQueries();
      notify("Evaluation queued.");
      onRun(run.id);
    } catch (e) {
      setError(e);
    } finally {
      setBusy("");
    }
  };
  return (
    <>
      <PageHeading
        eyebrow="EXPERIMENT & ITERATE"
        title="Experiments"
        description="Reproducible runs. Measurable improvements. A record of every decision."
      >
        <Button onClick={onNew}>
          <Plus size={17} />
          New evaluation
        </Button>
      </PageHeading>
      <div className="tabs">
        <button
          className={tab === "runs" ? "selected" : ""}
          onClick={() => setTab("runs")}
        >
          Evaluation runs <span>{runs.data?.total || 0}</span>
        </button>
        <button
          className={tab === "configs" ? "selected" : ""}
          onClick={() => setTab("configs")}
        >
          Saved configurations <span>{experiments.data?.length || 0}</span>
        </button>
      </div>
      <ErrorBox error={error || runs.error || experiments.error} />
      <div className="panel">
        <div className="toolbar">
          <label className="search-field">
            <Search size={17} />
            <input
              placeholder="Search experiments or models…"
              aria-label="Search experiments"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>
          {tab === "runs" && (
            <select
              aria-label="Filter by status"
              value={status}
              onChange={(e) => setStatus(e.target.value)}
            >
              <option value="all">All statuses</option>
              {[
                "PENDING",
                "RUNNING",
                "COMPLETED",
                "PARTIAL",
                "FAILED",
                "CANCELED",
              ].map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          )}
          <span className="toolbar-note">
            {tab === "runs"
              ? "Live updates every 2s"
              : "Immutable experiment settings"}
          </span>
        </div>
        {runs.isLoading ? (
          <Loading />
        ) : tab === "runs" ? (
          <>
            <RunTable
              runs={(runs.data?.items || []).filter(
                (r) =>
                  (status === "all" || r.status === status) &&
                  `${r.name} ${r.config.model}`
                    .toLowerCase()
                    .includes(search.toLowerCase()),
              )}
              onRun={onRun}
            />
            <Pagination
              offset={offset}
              limit={50}
              total={runs.data?.total || 0}
              onChange={setOffset}
            />
          </>
        ) : (
          <div className="experiment-grid">
            {experiments.data
              ?.filter((e) =>
                e.name.toLowerCase().includes(search.toLowerCase()),
              )
              .map((e) => (
                <div className="experiment-card" key={e.id}>
                  <div className="card-top">
                    <span className="table-icon">
                      <FlaskConical size={20} />
                    </span>
                    <span className="muted-tag">{e.config.provider}</span>
                  </div>
                  <h3>{e.name}</h3>
                  <p className="mono">{e.config.model}</p>
                  <div className="tag-list">
                    {e.config.evaluators.map((v) => (
                      <span className="tag" key={v}>
                        {v.replaceAll("_", " ")}
                      </span>
                    ))}
                  </div>
                  <div className="card-foot">
                    <span>
                      {e.config.concurrency} concurrent · {date(e.created_at)}
                    </span>
                    <Button
                      variant="secondary"
                      disabled={busy === e.id}
                      onClick={() => void rerun(e)}
                    >
                      {busy === e.id ? (
                        <Loader2 className="spin" size={14} />
                      ) : (
                        <Play size={14} />
                      )}
                      Run again
                    </Button>
                  </div>
                </div>
              ))}
          </div>
        )}
      </div>
    </>
  );
}

export function RunDetail({
  id,
  onBack,
  onResult,
  notify,
}: {
  id: string;
  onBack: () => void;
  onResult: (id: string) => void;
  notify: (s: string) => void;
}) {
  const run = useQuery({
    queryKey: ["run", id],
    queryFn: () => api<Run>("/runs/" + id),
    refetchInterval: 2000,
  });
  const [offset, setOffset] = useState(0),
    [filter, setFilter] = useState("all"),
    [error, setError] = useState<unknown>(null),
    [busy, setBusy] = useState(false);
  const results = useQuery({
    queryKey: ["results", id, offset, filter],
    queryFn: () =>
      api<{ items: Result[]; total: number }>(
        `/runs/${id}/results?offset=${offset}&limit=50${filter === "all" ? "" : `&status=${filter}`}`,
      ),
    refetchInterval: 2000,
  });
  const calibration = useQuery({
    queryKey: ["calibration", id],
    queryFn: () =>
      api<{ reviewed_judge_pairs: number; mean_absolute_error: number | null }>(
        `/runs/${id}/calibration`,
      ),
  });
  const client = useQueryClient();
  const action = async (kind: string) => {
    setBusy(true);
    setError(null);
    try {
      if (kind === "cancel") {
        await post("/runs/" + id + "/cancel", {});
        notify("Remaining cases canceled.");
      } else {
        await post("/baselines", { name: "main", run_id: id });
        notify("Run saved as the main baseline.");
      }
      void client.invalidateQueries();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };
  if (run.isLoading) return <Loading />;
  if (!run.data) return <ErrorBox error={run.error} />;
  const r = run.data,
    m = r.metrics,
    progress = (m.completed + m.failed + m.canceled) / r.total;
  return (
    <>
      <button className="back-link" onClick={onBack}>
        <ChevronLeft size={16} />
        All experiments
      </button>
      <PageHeading
        eyebrow={`RUN / ${id.slice(0, 8)}`}
        title={r.name}
        description={`${r.config.model} · ${r.config.prompt_name || "Versioned prompt"} · Started ${date(r.created_at)}`}
      >
        <Badge status={r.status} />
        {!terminal(r.status) ? (
          <Button
            variant="secondary"
            onClick={() => void action("cancel")}
            disabled={busy}
          >
            <X size={16} />
            Cancel run
          </Button>
        ) : r.status === "COMPLETED" ? (
          <Button
            variant="secondary"
            disabled={busy}
            onClick={() => void action("baseline")}
          >
            <GitBranch size={16} />
            Set as baseline
          </Button>
        ) : null}
        <Button
          variant="secondary"
          onClick={() => download(r, `evalscope-${id.slice(0, 8)}.json`)}
        >
          <Download size={16} />
          Run report
        </Button>
      </PageHeading>
      <ErrorBox error={error} />
      <div className="progress-panel">
        <div>
          <strong>{Math.round(progress * 100)}% complete</strong>
          <span>
            {m.completed} completed · {m.failed} failed · {m.running} running ·{" "}
            {m.pending} queued
          </span>
        </div>
        <div className="progress-track">
          <div style={{ width: `${progress * 100}%` }} />
        </div>
      </div>
      <div className="stats-grid">
        <Stat
          label="Pass rate"
          value={pct(m.pass_rate)}
          icon={CheckCircle2}
          sub={`${m.coverage * 100}% execution coverage`}
          accent
        />
        <Stat
          label="Mean quality score"
          value={pct(m.average_score)}
          icon={Sparkles}
          sub={`${r.config.evaluators.length} versioned evaluators`}
        />
        <Stat
          label="p95 latency"
          value={ms(m.p95_latency_ms)}
          icon={Clock3}
          sub={`${m.retries} retries recorded`}
        />
        <Stat
          label="Known usage estimate"
          value={money(m.estimated_cost)}
          icon={Coins}
          sub={`${(m.input_tokens + m.output_tokens).toLocaleString()} reported tokens · all attempts`}
        />
      </div>
      <UsagePanel runId={id} />
      <details className="panel config-details">
        <summary>
          <Code2 size={16} />
          Frozen run configuration{" "}
          <span className="muted">Immutable snapshot</span>
        </summary>
        <pre>{JSON.stringify(r.config, null, 2)}</pre>
      </details>
      {r.config.evaluators.includes("llm_judge") && (
        <div className="info-box">
          Judge calibration: {calibration.data?.reviewed_judge_pairs || 0}{" "}
          explicit human-review pairs · Mean absolute error:{" "}
          {calibration.data?.mean_absolute_error?.toFixed(3) ??
            "not yet measured"}
          . Review individual outputs to build calibration evidence.
        </div>
      )}
      <section className="panel">
        <div className="panel-header">
          <div>
            <h3>
              Case results <span className="count-chip">{r.total}</span>
            </h3>
            <p>Inspect scores, review outputs, and follow execution traces.</p>
          </div>
          <select
            aria-label="Filter case results"
            value={filter}
            onChange={(e) => {
              setFilter(e.target.value);
              setOffset(0);
            }}
          >
            <option value="all">All cases</option>
            {["COMPLETED", "FAILED", "RUNNING", "PENDING", "CANCELED"].map(
              (s) => (
                <option key={s}>{s}</option>
              ),
            )}
          </select>
        </div>
        <ErrorBox error={results.error} />
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>TEST CASE</th>
                <th>STATUS</th>
                <th>SCORE</th>
                <th>RESULT</th>
                <th>LATENCY</th>
                <th>ATTEMPTS</th>
                <th>TRACE</th>
              </tr>
            </thead>
            <tbody>
              {results.data?.items.map((result) => (
                <tr
                  key={result.id}
                  onClick={() => onResult(result.id)}
                  className="clickable-row"
                >
                  <td>
                    <button
                      className="text-link mono"
                      onClick={(e) => {
                        e.stopPropagation();
                        onResult(result.id);
                      }}
                    >
                      {result.case_id}
                    </button>
                    {result.error && (
                      <small className="cell-error">{result.error}</small>
                    )}
                  </td>
                  <td>
                    <Badge status={result.status} />
                  </td>
                  <td className="mono">{pct(result.score)}</td>
                  <td>
                    {result.passed === null ? (
                      "—"
                    ) : (
                      <span
                        className={result.passed ? "green-text" : "red-text"}
                      >
                        {result.passed ? "Pass" : "Below threshold"}
                      </span>
                    )}
                  </td>
                  <td className="mono">{ms(result.latency_ms)}</td>
                  <td className="mono">{result.attempts}</td>
                  <td>
                    {result.trace_id ? (
                      <span className="trace-link">
                        <Activity size={14} />
                        {result.trace_id.slice(0, 8)}
                      </span>
                    ) : (
                      "—"
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Pagination
          offset={offset}
          limit={50}
          total={results.data?.total || 0}
          onChange={setOffset}
        />
      </section>
    </>
  );
}
