import React, { useEffect, useRef } from "react";
import {
  ChevronLeft,
  ChevronRight,
  FlaskConical,
  Loader2,
  X,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import { pct, ms, date, type Run } from "../api";

export function Badge({ status }: { status: string }) {
  return (
    <span className={`badge ${status.toLowerCase()}`}>
      <span className="status-dot" />
      {status.replaceAll("_", " ").toLowerCase()}
    </span>
  );
}

export function Empty({
  icon: Icon = FlaskConical,
  title,
  children,
}: {
  icon?: LucideIcon;
  title: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty-icon">
        <Icon size={26} />
      </div>
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}

export function ErrorBox({ error }: { error: unknown }) {
  return error ? (
    <div role="alert" className="error-box">
      <XCircle size={17} />
      {error instanceof Error ? error.message : String(error)}
    </div>
  ) : null;
}

export function Loading() {
  return (
    <div className="loading">
      <Loader2 className="spin" size={22} /> Loading workspace…
    </div>
  );
}

export function Button({
  children,
  variant = "primary",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: string }) {
  return (
    <button {...props} className={`button ${variant} ${props.className || ""}`}>
      {children}
    </button>
  );
}

export function download(data: unknown, name: string) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }),
  );
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function Modal({
  title,
  subtitle,
  onClose,
  children,
  wide = false,
}: {
  title: string;
  subtitle?: string;
  onClose: () => void;
  children: React.ReactNode;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    const previous = document.activeElement as HTMLElement;
    const node = ref.current;
    node?.focus();
    const handle = (e: KeyboardEvent) => {
      if (e.key === "Escape") close.current();
      if (e.key === "Tab") {
        const elements = node?.querySelectorAll<HTMLElement>(
          'button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),[tabindex="0"]',
        );
        if (!elements?.length) return;
        const first = elements[0],
          last = elements[elements.length - 1];
        if (
          e.shiftKey &&
          (document.activeElement === first || document.activeElement === node)
        ) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", handle);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", handle);
      document.body.style.overflow = "";
      previous?.focus();
    };
  }, []);
  return (
    <div
      className="modal-overlay"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={ref}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={`modal ${wide ? "wide" : ""}`}
      >
        <div className="modal-head">
          <div>
            <h2>{title}</h2>
            {subtitle && <p>{subtitle}</p>}
          </div>
          <button
            className="icon-button"
            aria-label="Close dialog"
            onClick={onClose}
          >
            <X size={20} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function PageHeading({
  eyebrow,
  title,
  description,
  children,
}: {
  eyebrow?: string;
  title: string;
  description: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      <div className="heading-actions">{children}</div>
    </div>
  );
}

export function Stat({
  label,
  value,
  icon: Icon,
  sub,
  accent = false,
}: {
  label: string;
  value: string;
  icon: LucideIcon;
  sub: string;
  accent?: boolean;
}) {
  return (
    <div className={`stat-card ${accent ? "accent-stat" : ""}`}>
      <div className="stat-label">
        {label}
        <Icon size={17} />
      </div>
      <div className="stat-value">{value}</div>
      <div className="stat-sub">
        {accent ? <span className="live-dot" /> : <span className="sub-dot" />}
        {sub}
      </div>
    </div>
  );
}

export function RunTable({
  runs,
  onRun,
}: {
  runs: Run[];
  onRun: (id: string) => void;
}) {
  return runs.length ? (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>EXPERIMENT</th>
            <th>STATUS</th>
            <th>PASS RATE</th>
            <th>p95 LATENCY</th>
            <th>CASES</th>
            <th>CREATED</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr
              key={run.id}
              className="clickable-row"
              onClick={() => onRun(run.id)}
            >
              <td>
                <button
                  className="run-name"
                  onClick={(e) => {
                    e.stopPropagation();
                    onRun(run.id);
                  }}
                >
                  <span
                    className={`table-icon ${run.config.model.includes("regressed") ? "orange" : ""}`}
                  >
                    <FlaskConical size={17} />
                  </span>
                  <span>
                    <strong>{run.name}</strong>
                    <small>
                      {run.config.model} <span>·</span> {run.id.slice(0, 8)}
                    </small>
                  </span>
                </button>
              </td>
              <td>
                <Badge status={run.status} />
              </td>
              <td>
                <div className="pass-rate">
                  <strong>
                    {run.metrics.completed ? pct(run.metrics.pass_rate) : "—"}
                  </strong>
                  <div className="mini-progress">
                    <span
                      style={{ width: `${run.metrics.pass_rate * 100}%` }}
                    />
                  </div>
                </div>
              </td>
              <td className="mono">{ms(run.metrics.p95_latency_ms)}</td>
              <td className="mono">
                <span>{run.metrics.completed}</span>
                <span className="muted"> / {run.total}</span>
              </td>
              <td className="muted nowrap">{date(run.created_at)}</td>
              <td>
                <ChevronRight size={15} className="muted" />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  ) : (
    <Empty title="No evaluations yet">
      Create an experiment to begin measuring your application.
    </Empty>
  );
}

export function Pagination({
  offset,
  limit,
  total,
  onChange,
}: {
  offset: number;
  limit: number;
  total: number;
  onChange: (n: number) => void;
}) {
  return (
    <div className="pagination">
      <span>
        {total
          ? `${offset + 1}–${Math.min(offset + limit, total)} of ${total}`
          : "0 results"}
      </span>
      <div>
        <button
          className="icon-button"
          aria-label="Previous page"
          disabled={!offset}
          onClick={() => onChange(Math.max(0, offset - limit))}
        >
          <ChevronLeft size={17} />
        </button>
        <button
          className="icon-button"
          aria-label="Next page"
          disabled={offset + limit >= total}
          onClick={() => onChange(offset + limit)}
        >
          <ChevronRight size={17} />
        </button>
      </div>
    </div>
  );
}
