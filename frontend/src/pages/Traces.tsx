import React, { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, Check, ChevronRight, Search } from "lucide-react";
import { api, pct, ms, type Case, type Result, type Trace } from "../api";
import {
  Badge,
  Empty,
  ErrorBox,
  Loading,
  Button,
  Modal,
  PageHeading,
} from "../components/ui";
import { useData } from "../hooks/useData";

export function TracesPage({ onResult }: { onResult: (id: string) => void }) {
  const traces = useData<Trace[]>("traces", "/traces?limit=500", true);
  const [search, setSearch] = useState(""),
    [filter, setFilter] = useState("all"),
    [online, setOnline] = useState<string | null>(null);
  const items =
    traces.data?.filter(
      (t) =>
        (filter === "all" ||
          (filter === "errors" && !!t.error) ||
          (filter === "slow" && (t.latency_ms || 0) > 1000)) &&
        `${t.case_id} ${t.trace_id} ${t.error || ""}`.includes(search),
    ) || [];
  return (
    <>
      <PageHeading
        eyebrow="FOLLOW THE EVIDENCE"
        title="Execution traces"
        description="From retrieval to evaluation. See where time goes and failures begin."
      >
        <span className="live-label">
          <span className="live-dot" />
          Live · latest 500 traces
        </span>
      </PageHeading>
      <ErrorBox error={traces.error} />
      <section className="panel">
        <div className="toolbar">
          <label className="search-field">
            <Search size={17} />
            <input
              placeholder="Search trace ID, case, or error…"
              aria-label="Search traces"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>
          <select
            aria-label="Filter traces"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          >
            <option value="all">All traces</option>
            <option value="errors">With errors</option>
            <option value="slow">Slower than 1s</option>
          </select>
        </div>
        {traces.isLoading ? (
          <Loading />
        ) : items.length ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>TRACE ID</th>
                  <th>TEST CASE</th>
                  <th>STATUS</th>
                  <th>LATENCY</th>
                  <th>SPANS</th>
                  <th>ERROR CATEGORY</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {items.map((t) => (
                  <tr
                    className="clickable-row"
                    key={t.trace_id}
                    onClick={() => setOnline(t.trace_id)}
                  >
                    <td>
                      <button
                        className="trace-link"
                        onClick={(e) => {
                          e.stopPropagation();
                          setOnline(t.trace_id);
                        }}
                      >
                        <Activity size={15} />
                        {t.trace_id.slice(0, 16)}
                      </button>
                    </td>
                    <td className="mono">
                      {t.case_id}
                      <small className="trace-source">
                        {t.source}
                        {t.attempt ? ` · attempt ${t.attempt}` : ""}
                      </small>
                    </td>
                    <td>
                      <Badge status={t.status} />
                    </td>
                    <td className="mono">{ms(t.latency_ms)}</td>
                    <td>{t.span_count}</td>
                    <td className={t.error ? "red-text" : "muted"}>
                      {t.error || "None"}
                    </td>
                    <td>
                      <ChevronRight size={15} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty icon={Activity} title="No matching traces">
            Evaluation workers record traces as test cases execute. Use the
            Python SDK to observe application requests.
          </Empty>
        )}
      </section>
      {online && (
        <OnlineTraceModal
          id={online}
          onClose={() => setOnline(null)}
          onResult={onResult}
        />
      )}
    </>
  );
}

export function ResultModal({
  id,
  onClose,
  notify,
}: {
  id: string;
  onClose: () => void;
  notify: (s: string) => void;
}) {
  const result = useQuery({
    queryKey: ["result", id],
    queryFn: () => api<Result>("/results/" + id),
    refetchInterval: 2000,
  });
  const [review, setReview] = useState(""),
    [note, setNote] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<unknown>(null);
  const client = useQueryClient();
  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api(`/results/${id}/review`, {
        method: "PUT",
        body: JSON.stringify({ score: +review, note }),
      });
      void client.invalidateQueries();
      notify("Human review saved.");
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };
  const r = result.data,
    spans = r?.spans || [],
    start = Math.min(...spans.map((s) => s.started_at)),
    end = Math.max(...spans.map((s) => s.ended_at)),
    duration = end - start || 1;
  return (
    <Modal
      title={r?.case_id || "Case inspection"}
      subtitle={
        r?.trace_id
          ? `Trace ${r.trace_id}`
          : "Scores, output, and execution evidence"
      }
      onClose={onClose}
      wide
    >
      {result.isLoading ? (
        <Loading />
      ) : (
        <div className="result-body">
          <ErrorBox error={result.error || error} />
          {r && (
            <>
              <div className="result-summary">
                <Badge status={r.status} />
                <span>
                  Score <strong>{pct(r.score)}</strong>
                </span>
                <span>
                  Latency <strong>{ms(r.latency_ms)}</strong>
                </span>
                <span>
                  Attempts <strong>{r.attempts}</strong>
                </span>
              </div>
              {r.error && (
                <div className="error-box">Failure category: {r.error}</div>
              )}
              <div className="answer-block">
                <h4>INPUT</h4>
                <p>{r.case?.input}</p>
              </div>
              <div className="answer-columns">
                <div className="answer-block">
                  <h4>REFERENCE ANSWER</h4>
                  <p>{r.case?.reference_answer}</p>
                </div>
                <div className="answer-block generated">
                  <h4>MODEL RESPONSE</h4>
                  <p>
                    {r.output ??
                      "Response content was not captured for this case."}
                  </p>
                </div>
              </div>
              <h3 className="subheading">Evaluator scores</h3>
              {r.scores.map((s) => (
                <div className="score-row" key={s.evaluator}>
                  <div>
                    <strong>{s.evaluator.replaceAll("_", " ")}</strong>
                    <span className="muted-tag">{s.version}</span>
                    <p>{s.reason}</p>
                    {Object.keys(s.details).length > 0 && (
                      <code>{JSON.stringify(s.details)}</code>
                    )}
                  </div>
                  <span className="score-value">{pct(s.value)}</span>
                </div>
              ))}
              {!r.scores.length && (
                <p className="muted">
                  Scores become available after successful evaluation.
                </p>
              )}
              <h3 className="subheading">
                Trace timeline{" "}
                <span className="count-chip">{spans.length} spans</span>
              </h3>
              <div className="trace-timeline">
                {spans.map((s) => (
                  <div className="span-row" key={s.span_id}>
                    <span className="span-name">
                      <i className={s.status === "ERROR" ? "error-span" : ""} />
                      {s.name}
                    </span>
                    <div className="span-track">
                      <div
                        className={
                          s.status === "ERROR"
                            ? "span-bar failed-bar"
                            : "span-bar"
                        }
                        style={{
                          left: `${((s.started_at - start) / duration) * 100}%`,
                          width: `${Math.max(0.6, (s.duration_ms / 1000 / duration) * 100)}%`,
                        }}
                      />
                    </div>
                    <span className="mono">{ms(s.duration_ms)}</span>
                  </div>
                ))}
              </div>
              {r.attempt_history && r.attempt_history.length > 1 && (
                <>
                  <h3 className="subheading">Attempt history</h3>
                  <div className="attempt-list">
                    {r.attempt_history.map((a) => (
                      <div key={a.number}>
                        <span>Attempt {a.number}</span>
                        <Badge status={a.status} />
                        <code>{a.error || "No error"}</code>
                        {a.trace_id && (
                          <a
                            className="text-link"
                            href={`#traces`}
                            onClick={() => onClose()}
                          >
                            Trace {a.trace_id.slice(0, 8)}
                          </a>
                        )}
                      </div>
                    ))}
                  </div>
                </>
              )}
              {r.output !== null && r.status === "COMPLETED" && (
                <form onSubmit={save} className="review-form">
                  <h3>
                    Human review{" "}
                    <span className="muted-tag">EXPLICIT LABEL</span>
                  </h3>
                  {r.human_score !== null && (
                    <p className="green-text">
                      Saved score: {pct(r.human_score)} ·{" "}
                      {r.human_note || "No note"}
                    </p>
                  )}
                  <div className="form-row">
                    <label>
                      Quality score (0–1)
                      <input
                        required
                        type="number"
                        min={0}
                        max={1}
                        step="0.05"
                        value={review}
                        onChange={(e) => setReview(e.target.value)}
                      />
                    </label>
                    <label>
                      Review note
                      <input
                        maxLength={2000}
                        value={note}
                        onChange={(e) => setNote(e.target.value)}
                        placeholder="Why did you assign this score?"
                      />
                    </label>
                  </div>
                  <Button disabled={busy} variant="secondary">
                    <Check size={15} />
                    Save human review
                  </Button>
                </form>
              )}
            </>
          )}
        </div>
      )}
    </Modal>
  );
}

export function OnlineTraceModal({
  id,
  onClose,
  onResult,
}: {
  id: string;
  onClose: () => void;
  onResult?: (id: string) => void;
}) {
  const trace = useQuery({
    queryKey: ["online-trace", id],
    queryFn: () =>
      api<{
        service?: string;
        attempt?: number;
        expired?: boolean;
        result_id?: string;
        spans: import("../api").Span[];
      }>("/traces/" + id),
  });
  return (
    <Modal
      title={
        trace.data?.service ||
        `Evaluation attempt ${trace.data?.attempt || "—"}`
      }
      subtitle={`Trace · ${id}`}
      onClose={onClose}
      wide
    >
      <div className="result-body">
        <ErrorBox error={trace.error} />
        {trace.isLoading ? (
          <Loading />
        ) : (
          <>
            <div className="info-box">
              This exact trace belongs to the selected request or attempt. New
              evaluation traces measure the persistence transaction; historical
              traces can predate that instrumentation. Expired spans are
              unavailable.
            </div>
            {trace.data?.expired && (
              <div className="info-box">
                Trace spans expired under the project retention policy.
              </div>
            )}
            {trace.data?.result_id && onResult && (
              <Button
                variant="secondary"
                onClick={() => {
                  onResult(trace.data!.result_id!);
                  onClose();
                }}
              >
                Inspect case results
              </Button>
            )}
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>OPERATION</th>
                    <th>STATUS</th>
                    <th>DURATION</th>
                    <th>METADATA</th>
                  </tr>
                </thead>
                <tbody>
                  {trace.data?.spans.map((s) => (
                    <tr key={s.span_id}>
                      <td>{s.name}</td>
                      <td>
                        <Badge
                          status={s.status === "OK" ? "COMPLETED" : "FAILED"}
                        />
                      </td>
                      <td>{ms(s.duration_ms)}</td>
                      <td>
                        <code>{JSON.stringify(s.attributes)}</code>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </Modal>
  );
}
