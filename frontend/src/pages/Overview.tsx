import React, { useState } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  BarChart3,
  CheckCheck,
  CheckCircle2,
  Clock3,
  Coins,
  Database,
  FlaskConical,
  GitBranch,
  GitCompareArrows,
  Plus,
  ShieldCheck,
  Terminal,
} from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { pct, ms, money, type Dataset, type Overview, type Run } from "../api";
import {
  Empty,
  Loading,
  Button,
  PageHeading,
  Stat,
  RunTable,
} from "../components/ui";

export function OverviewPage({
  data,
  loading,
  onNew,
  onRun,
  navigate,
}: {
  data?: Overview;
  loading: boolean;
  onNew: () => void;
  onRun: (id: string) => void;
  navigate: (p: string) => void;
}) {
  const [range, setRange] = useState("all");
  if (loading) return <Loading />;
  const m = data?.metrics;
  const chronological = (data?.runs || [])
    .filter((r) => r.status === "COMPLETED")
    .slice()
    .reverse();
  const cutoff =
    range === "24h"
      ? Date.now() / 1000 - 86400
      : range === "7d"
        ? Date.now() / 1000 - 604800
        : 0;
  const chartData = chronological
    .filter((r) => r.created_at >= cutoff)
    .map((r, i) => ({
      name: `Run ${i + 1}`,
      quality: +(r.metrics.pass_rate * 100).toFixed(1),
      score:
        r.metrics.average_score === null
          ? null
          : +(r.metrics.average_score * 100).toFixed(1),
      run: r.name,
    }));
  const candidate = chronological.at(-1),
    baseline = chronological.length > 1 ? chronological[0] : undefined;
  const regression =
    baseline &&
    candidate &&
    candidate.metrics.pass_rate < baseline.metrics.pass_rate - 0.03;
  return (
    <>
      <PageHeading
        eyebrow="YOUR EVALUATION WORKSPACE"
        title="Evaluation overview"
        description="A clear view of quality, performance, and every change in between."
      >
        <Button variant="secondary" onClick={() => navigate("comparisons")}>
          <GitCompareArrows size={16} />
          Compare runs
        </Button>
        <Button onClick={onNew}>
          <Plus size={17} />
          New evaluation
        </Button>
      </PageHeading>
      <div className="welcome-banner">
        <div className="banner-copy">
          <span className="banner-label">
            <span className="live-dot" /> BUILT FOR BETTER AI
          </span>
          <h2>
            Measure first.
            <br />
            Ship with confidence.
          </h2>
          <p>Turn every prompt change into a decision backed by evidence.</p>
          <button onClick={onNew}>
            Start an experiment <ArrowRight size={17} />
          </button>
        </div>
        <div className="banner-visual" aria-hidden="true">
          <div className="orbit orbit-one" />
          <div className="orbit orbit-two" />
          <div className="orbit orbit-three" />
          <div className="visual-line" />
          <div className="visual-node node-a">
            <Database size={22} />
            <span>Dataset</span>
          </div>
          <div className="visual-node node-b">
            <FlaskConical size={26} />
            <span>Evaluate</span>
          </div>
          <div className="visual-node node-c">
            <CheckCheck size={23} />
            <span>Improve</span>
          </div>
          <span className="visual-spark spark-one">+</span>
          <span className="visual-spark spark-two">+</span>
          <span className="visual-coordinate">01 — EVALUATION PIPELINE</span>
        </div>
      </div>
      <div className="stats-grid">
        <Stat
          label="Overall pass rate"
          value={pct(m?.pass_rate)}
          icon={CheckCircle2}
          sub={`${m?.completed || 0} completed cases`}
          accent
        />
        <Stat
          label="Evaluation runs"
          value={String(data?.run_count || 0).padStart(2, "0")}
          icon={FlaskConical}
          sub={`${data?.active_runs || 0} currently in progress`}
        />
        <Stat
          label="p95 latency"
          value={ms(m?.p95_latency_ms)}
          icon={Clock3}
          sub="Across completed evaluations"
        />
        <Stat
          label="Known usage estimate"
          value={money(m?.estimated_cost || 0)}
          icon={Coins}
          sub={`${((m?.input_tokens || 0) + (m?.output_tokens || 0)).toLocaleString()} reported tokens`}
        />
      </div>
      {data?.usage && !data.usage.complete && (
        <div className="usage-note">
          Cost is a known lower bound: some calls have missing usage/prices or
          predate the ledger. Open a run's usage ledger for the unresolved
          entries.
        </div>
      )}
      <div className="overview-middle">
        <section className="panel trend-panel">
          <div className="panel-header">
            <div>
              <h3>
                Quality over time <span className="muted-tag">BY RUN</span>
              </h3>
              <p>Pass rate and mean score across completed evaluations</p>
            </div>
            <select
              aria-label="Chart time range"
              className="compact-select"
              value={range}
              onChange={(e) => setRange(e.target.value)}
            >
              <option value="all">All runs</option>
              <option value="24h">Last 24 hours</option>
              <option value="7d">Last 7 days</option>
            </select>
          </div>
          {chartData.length ? (
            <>
              <div className="chart-legend">
                <span>
                  <i className="legend-square green" />
                  Pass rate
                </span>
                <span>
                  <i className="legend-square pale" />
                  Mean score
                </span>
              </div>
              <div className="quality-chart">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart
                    data={chartData}
                    margin={{ top: 10, right: 15, bottom: 5, left: -24 }}
                  >
                    <defs>
                      <linearGradient
                        id="qualityGradient"
                        x1="0"
                        y1="0"
                        x2="0"
                        y2="1"
                      >
                        <stop
                          offset="0%"
                          stopColor="#21846b"
                          stopOpacity={0.15}
                        />
                        <stop
                          offset="100%"
                          stopColor="#21846b"
                          stopOpacity={0}
                        />
                      </linearGradient>
                    </defs>
                    <CartesianGrid
                      strokeDasharray="3 5"
                      vertical={false}
                      stroke="#e8ebe6"
                    />
                    <XAxis
                      dataKey="name"
                      tickLine={false}
                      axisLine={false}
                      tick={{ fill: "#89918b", fontSize: 11 }}
                      dy={10}
                    />
                    <YAxis
                      domain={[0, 100]}
                      tickFormatter={(v) => `${v}%`}
                      tickLine={false}
                      axisLine={false}
                      tick={{ fill: "#89918b", fontSize: 11 }}
                    />
                    <Tooltip
                      formatter={(v: number) => `${v}%`}
                      labelFormatter={(_, payload) =>
                        payload?.[0]?.payload?.run || ""
                      }
                      contentStyle={{
                        borderRadius: 10,
                        border: "1px solid #e1e6df",
                        fontSize: 12,
                      }}
                    />
                    <Area
                      type="linear"
                      dataKey="score"
                      name="Mean score"
                      stroke="#a6c8b3"
                      strokeDasharray="5 4"
                      fill="none"
                      strokeWidth={2}
                    />
                    <Area
                      type="linear"
                      dataKey="quality"
                      name="Pass rate"
                      stroke="#258269"
                      fill="url(#qualityGradient)"
                      strokeWidth={2.5}
                      dot={{
                        fill: "#258269",
                        stroke: "#fff",
                        strokeWidth: 2,
                        r: 4,
                      }}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </>
          ) : (
            <Empty icon={BarChart3} title="Your first data point is ahead">
              Complete an evaluation to track quality here.
            </Empty>
          )}
          <div className="panel-bottom">
            <span>
              <span className="sub-dot" />
              Measured results only. No interpolated history.
            </span>
            <button
              className="text-link"
              onClick={() => navigate("experiments")}
            >
              View experiments <ArrowRight size={14} />
            </button>
          </div>
        </section>
        <section className="panel release-panel">
          <div className="panel-header">
            <div className="section-icon">
              <ShieldCheck size={19} />
            </div>
            <h3>Release confidence</h3>
          </div>
          <div
            className={`release-symbol ${regression ? "warning-symbol" : ""}`}
          >
            {regression ? <GitBranch size={29} /> : <ShieldCheck size={29} />}
          </div>
          <h2>
            {regression
              ? "A change worth a closer look."
              : candidate
                ? "Evidence, ready for review."
                : "Make your next release measurable."}
          </h2>
          <p>
            {regression
              ? "The latest completed run has a lower pass rate than the first run. Compare compatible runs to investigate."
              : "Compare a candidate with a baseline and apply your release thresholds."}
          </p>
          <div className="release-facts">
            <span>
              Completed runs<strong>{chronological.length}</strong>
            </span>
            <span>
              Datasets<strong>{data?.dataset_count || 0} datasets</strong>
            </span>
            <span>
              Review status
              <strong className={regression ? "amber-text" : "green-text"}>
                {regression ? "Review recommended" : "Ready to evaluate"}
              </strong>
            </span>
          </div>
          <Button variant="secondary" onClick={() => navigate("comparisons")}>
            Review comparison <ArrowRight size={15} />
          </Button>
        </section>
      </div>
      <section className="panel">
        <div className="panel-header">
          <div>
            <h3>
              Recent evaluations{" "}
              <span className="count-chip">{data?.run_count || 0}</span>
            </h3>
            <p>Your latest experiments, at a glance</p>
          </div>
          <button className="text-link" onClick={() => navigate("experiments")}>
            View all runs <ArrowRight size={15} />
          </button>
        </div>
        <RunTable runs={data?.runs.slice(0, 5) || []} onRun={onRun} />
      </section>
      <div className="workflow-strip">
        <div>
          <div className="workflow-icon">
            <Database size={19} />
          </div>
          <span>
            <strong>Your ground truth, versioned.</strong>
            <small>Build a reliable foundation with immutable datasets.</small>
          </span>
          <button
            className="icon-button"
            onClick={() => navigate("datasets")}
            aria-label="Manage datasets"
          >
            <ArrowUpRight size={19} />
          </button>
        </div>
        <div>
          <div className="workflow-icon">
            <Terminal size={19} />
          </div>
          <span>
            <strong>Quality belongs in your pipeline.</strong>
            <small>Catch regressions before they reach production.</small>
          </span>
          <button
            className="icon-button"
            onClick={() => navigate("gates")}
            aria-label="Manage quality gates"
          >
            <ArrowUpRight size={19} />
          </button>
        </div>
      </div>
    </>
  );
}
