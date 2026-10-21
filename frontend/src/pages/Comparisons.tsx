import React, { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  ArrowDownLeft,
  ArrowUpRight,
  BarChart3,
  Check,
  CheckCircle2,
  ChevronRight,
  CircleHelp,
  Clock3,
  Download,
  FlaskConical,
  GitBranch,
  GitCompareArrows,
  Loader2,
  ShieldCheck,
  SlidersHorizontal,
  XCircle,
} from "lucide-react";
import {
  post,
  pct,
  ms,
  date,
  money,
  defaultThresholds,
  type Case,
  type Comparison,
  type Gate,
  type Report,
  type Run,
  type Thresholds,
} from "../api";
import {
  Badge,
  Empty,
  ErrorBox,
  Button,
  download,
  PageHeading,
} from "../components/ui";
import { useData } from "../hooks/useData";

export function ComparisonsPage({
  gates,
  onResult,
  notify,
}: {
  gates: boolean;
  onResult: (id: string) => void;
  notify: (s: string) => void;
}) {
  const runs = useData<{ items: Run[]; total: number }>(
      "comparison-runs",
      "/runs?limit=200",
      true,
    ),
    reports = useData<Report[]>("reports", "/quality-gates");
  const [base, setBase] = useState(""),
    [candidate, setCandidate] = useState(""),
    [comparison, setComparison] = useState<Comparison | null>(null),
    [gate, setGate] = useState<Gate | null>(null),
    [thresholds, setThresholds] = useState<Thresholds>(defaultThresholds),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<unknown>(null),
    [caseFilter, setCaseFilter] = useState("all");
  const client = useQueryClient();
  const items = runs.data?.items || [];
  const baseId = base || items.at(-1)?.id || "",
    candidateId = candidate || items[0]?.id || "";
  const check = async (isGate = false) => {
    setBusy(true);
    setError(null);
    setGate(null);
    setComparison(null);
    try {
      if (isGate) {
        const report = await post<Gate>("/quality-gates/check", {
          baseline_id: baseId,
          candidate_id: candidateId,
          thresholds,
        });
        setGate(report);
        setComparison(report.comparison);
        void client.invalidateQueries({ queryKey: ["reports"] });
        notify(`Quality gate: ${report.decision.toLowerCase()}. Report saved.`);
      } else {
        setComparison(
          await post<Comparison>("/comparisons", {
            baseline_id: baseId,
            candidate_id: candidateId,
          }),
        );
      }
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };
  const choose = (which: string, id: string) => {
    which === "base" ? setBase(id) : setCandidate(id);
    setComparison(null);
    setGate(null);
    setError(null);
  };
  return (
    <>
      <PageHeading
        eyebrow={
          gates ? "BUILD QUALITY INTO YOUR PIPELINE" : "UNDERSTAND WHAT CHANGED"
        }
        title={gates ? "Quality gates" : "Compare evaluations"}
        description={
          gates
            ? "Turn your release criteria into repeatable, automated decisions."
            : "Compare compatible runs. Find improvements, regressions, and the cases behind them."
        }
      >
        {comparison && (
          <Button
            variant="secondary"
            onClick={() =>
              download(gate || comparison, "evalscope-comparison.json")
            }
          >
            <Download size={16} />
            Export report
          </Button>
        )}
      </PageHeading>
      <ErrorBox error={runs.error || reports.error} />
      <section className="panel comparison-config">
        <div className="comparison-selectors">
          <label>
            <span className="selector-label">
              <GitBranch size={15} />
              BASELINE
            </span>
            <select
              aria-label="Baseline run"
              value={baseId}
              onChange={(e) => choose("base", e.target.value)}
            >
              <option value="" disabled>
                Select baseline
              </option>
              {items.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name} · {r.id.slice(0, 8)} · {r.status}
                </option>
              ))}
            </select>
          </label>
          <div className="versus">vs</div>
          <label>
            <span className="selector-label">
              <FlaskConical size={15} />
              CANDIDATE
            </span>
            <select
              aria-label="Candidate run"
              value={candidateId}
              onChange={(e) => choose("candidate", e.target.value)}
            >
              <option value="" disabled>
                Select candidate
              </option>
              {items.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name} · {r.id.slice(0, 8)} · {r.status}
                </option>
              ))}
            </select>
          </label>
        </div>
        <details open={gates} className="threshold-details">
          <summary>
            <SlidersHorizontal size={15} />
            Release thresholds
          </summary>
          <div className="threshold-grid">
            {(Object.entries(thresholds) as [keyof Thresholds, number][]).map(
              ([key, value]) => (
                <label key={key}>
                  {key.replaceAll("_", " ")}
                  <input
                    type="number"
                    aria-label={key}
                    min={
                      key === "minimum_paired_cases"
                        ? 1
                        : key === "maximum_p95_latency_ms"
                          ? 0.01
                          : 0
                    }
                    max={
                      key.includes("rate") || key === "minimum_coverage"
                        ? 1
                        : undefined
                    }
                    step={
                      key === "minimum_paired_cases" ||
                      key === "maximum_p95_latency_ms"
                        ? 1
                        : 0.01
                    }
                    value={value}
                    onChange={(e) => {
                      setThresholds({ ...thresholds, [key]: +e.target.value });
                      setGate(null);
                    }}
                  />
                </label>
              ),
            )}
          </div>
        </details>
        <div className="comparison-actions">
          <p>
            <ShieldCheck size={14} />
            Same dataset version and evaluator configuration required.
          </p>
          <Button
            variant="secondary"
            disabled={busy || !baseId || !candidateId || baseId === candidateId}
            onClick={() => void check(false)}
          >
            <GitCompareArrows size={16} />
            Compare
          </Button>
          <Button
            disabled={busy || !baseId || !candidateId || baseId === candidateId}
            onClick={() => void check(true)}
          >
            {busy ? (
              <Loader2 className="spin" size={16} />
            ) : (
              <ShieldCheck size={16} />
            )}
            Check quality gate
          </Button>
        </div>
      </section>
      <ErrorBox error={error} />
      {gate && (
        <section className={`gate-result ${gate.decision.toLowerCase()}`}>
          <div className="gate-title">
            {gate.decision === "PASS" ? (
              <CheckCircle2 size={26} />
            ) : gate.decision === "FAIL" ? (
              <XCircle size={26} />
            ) : (
              <CircleHelp size={26} />
            )}
            <div>
              <h2>
                {gate.decision === "PASS"
                  ? "Release criteria passed"
                  : gate.decision === "FAIL"
                    ? "Release criteria failed"
                    : "Insufficient evidence"}
              </h2>
              <p>
                {gate.insufficient_reasons.join(" · ") ||
                  "Decision based on your configured thresholds and paired evaluation results."}
              </p>
            </div>
            <Badge status={gate.decision} />
          </div>
          <div className="gate-checks">
            {gate.checks.map((c) => (
              <div key={c.name}>
                {c.passed ? <CheckCircle2 size={16} /> : <XCircle size={16} />}
                <span>{c.name}</span>
                <strong>{c.actual === null ? "—" : c.actual.toFixed(3)}</strong>
                <span className="muted">limit {c.limit}</span>
              </div>
            ))}
          </div>
        </section>
      )}
      {comparison ? (
        <>
          <div className="comparison-stats">
            {(["improved", "regressed", "unchanged", "missing"] as const).map(
              (key, i) => {
                const Icon = [ArrowUpRight, ArrowDownLeft, Check, Clock3][i];
                return (
                  <button
                    key={key}
                    onClick={() =>
                      setCaseFilter(caseFilter === key ? "all" : key)
                    }
                    className={`comparison-stat ${key} ${caseFilter === key ? "selected" : ""}`}
                  >
                    <Icon size={21} />
                    <strong>{comparison.counts[key]}</strong>
                    <span>{key} cases</span>
                  </button>
                );
              },
            )}
          </div>
          <section className="panel">
            <div className="panel-header">
              <div>
                <h3>Quality, performance & cost</h3>
                <p>{comparison.paired_cases} paired successful cases</p>
              </div>
            </div>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>METRIC</th>
                    <th>BASELINE</th>
                    <th>CANDIDATE</th>
                    <th>CHANGE</th>
                  </tr>
                </thead>
                <tbody>
                  {[
                    { name: "Pass rate", key: "pass_rate", format: pct },
                    { name: "Mean score", key: "average_score", format: pct },
                    { name: "p95 latency", key: "p95_latency_ms", format: ms },
                    { name: "Error rate", key: "error_rate", format: pct },
                    {
                      name: "Execution coverage",
                      key: "coverage",
                      format: pct,
                    },
                    {
                      name: "Generation cost",
                      key: "estimated_cost",
                      format: (n: number | null) => money(n || 0),
                    },
                  ].map(({ name, key, format }) => {
                    const a =
                        comparison.baseline.metrics[
                          key as keyof typeof comparison.baseline.metrics
                        ],
                      b =
                        comparison.candidate.metrics[
                          key as keyof typeof comparison.candidate.metrics
                        ];
                    return (
                      <tr key={key}>
                        <td>{name}</td>
                        <td className="mono">{format(a)}</td>
                        <td className="mono">{format(b)}</td>
                        <td className="mono">
                          {a !== null && b !== null
                            ? (b - a > 0 ? "+" : "") + (b - a).toFixed(3)
                            : "—"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <div className="uncertainty-note">
              <BarChart3 size={17} />
              <div>
                <strong>
                  Paired mean score delta:{" "}
                  {comparison.mean_score_delta?.toFixed(3) ?? "—"}
                </strong>
                <p>
                  95% bootstrap interval:{" "}
                  {comparison.score_delta_95_ci
                    ? comparison.score_delta_95_ci
                        .map((n) => n.toFixed(3))
                        .join(" to ")
                    : "Not enough paired cases"}
                  . {comparison.uncertainty_method}.
                </p>
              </div>
            </div>
          </section>
          <section className="panel">
            <div className="panel-header">
              <h3>Case-by-case changes</h3>
              <select
                aria-label="Filter comparison cases"
                value={caseFilter}
                onChange={(e) => setCaseFilter(e.target.value)}
              >
                {["all", "improved", "regressed", "unchanged", "missing"].map(
                  (v) => (
                    <option key={v} value={v}>
                      {v === "all" ? "All changes" : v}
                    </option>
                  ),
                )}
              </select>
            </div>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>TEST CASE</th>
                    <th>BASELINE SCORE</th>
                    <th>CANDIDATE SCORE</th>
                    <th>DELTA</th>
                    <th>CHANGE</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {comparison.cases
                    .filter(
                      (c) => caseFilter === "all" || c.change === caseFilter,
                    )
                    .map((c) => (
                      <tr
                        className="clickable-row"
                        key={c.case_id}
                        onClick={() =>
                          c.candidate_result_id &&
                          onResult(c.candidate_result_id)
                        }
                      >
                        <td>
                          <button
                            className="text-link mono"
                            onClick={(e) => {
                              e.stopPropagation();
                              if (c.candidate_result_id)
                                onResult(c.candidate_result_id);
                            }}
                          >
                            {c.case_id}
                          </button>
                        </td>
                        <td>{pct(c.baseline_score)}</td>
                        <td>{pct(c.candidate_score)}</td>
                        <td
                          className={
                            c.change === "regressed"
                              ? "red-text"
                              : c.change === "improved"
                                ? "green-text"
                                : ""
                          }
                        >
                          {c.delta === null
                            ? "—"
                            : `${c.delta > 0 ? "+" : ""}${(c.delta * 100).toFixed(1)} pp`}
                        </td>
                        <td>
                          <Badge status={c.change} />
                        </td>
                        <td>
                          <ChevronRight size={15} />
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      ) : (
        !error && (
          <section className="panel">
            <Empty
              icon={gates ? ShieldCheck : GitCompareArrows}
              title={
                gates
                  ? "Your criteria. A consistent release decision."
                  : "Every change tells a story."
              }
            >
              Select a baseline and candidate to inspect paired results.
            </Empty>
          </section>
        )
      )}
      {gates && !!reports.data?.length && (
        <section className="panel">
          <div className="panel-header">
            <h3>Saved gate reports</h3>
            <span className="muted-tag">LATEST 50</span>
          </div>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>DECISION</th>
                  <th>CANDIDATE</th>
                  <th>BASELINE</th>
                  <th>CHECKED</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {reports.data.map((r) => (
                  <tr
                    key={r.id}
                    className="clickable-row"
                    onClick={() => {
                      setBase(r.report.comparison.baseline.id);
                      setCandidate(r.report.comparison.candidate.id);
                      setThresholds(r.report.thresholds);
                      setGate(r.report);
                      setComparison(r.report.comparison);
                    }}
                  >
                    <td>
                      <Badge status={r.decision} />
                    </td>
                    <td>{r.report.comparison.candidate.name}</td>
                    <td>{r.report.comparison.baseline.name}</td>
                    <td>{date(r.created_at)}</td>
                    <td>
                      <button
                        className="text-link"
                        onClick={(e) => {
                          e.stopPropagation();
                          download(r.report, `gate-${r.id.slice(0, 8)}.json`);
                        }}
                      >
                        Export <Download size={13} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </>
  );
}
