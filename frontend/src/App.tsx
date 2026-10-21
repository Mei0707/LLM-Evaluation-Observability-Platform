import React, { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  ArrowUpRight,
  BookOpen,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  Database,
  ExternalLink,
  FlaskConical,
  GitCompareArrows,
  Layers3,
  LayoutDashboard,
  Menu,
  Settings2,
  ShieldCheck,
  X,
  type LucideIcon,
} from "lucide-react";
import { type Overview, type Prompt, type Run, type Workspace } from "./api";
import { useData } from "./hooks/useData";
import { Empty, ErrorBox, Button } from "./components/ui";
import { OverviewPage } from "./pages/Overview";
import { ExperimentsPage, RunDetail } from "./pages/Experiments";
import { NewRunModal } from "./features/NewRunModal";
import { DatasetsPage } from "./pages/Datasets";
import { PromptsPage } from "./pages/Prompts";
import { TracesPage, ResultModal } from "./pages/Traces";
import { ComparisonsPage } from "./pages/Comparisons";
import { SettingsPage } from "./pages/Settings";

const navItems: {
  id: string;
  label: string;
  icon: LucideIcon;
  group: string;
}[] = [
  {
    id: "overview",
    label: "Overview",
    icon: LayoutDashboard,
    group: "WORKSPACE",
  },
  {
    id: "experiments",
    label: "Experiments",
    icon: FlaskConical,
    group: "WORKSPACE",
  },
  { id: "datasets", label: "Datasets", icon: Database, group: "WORKSPACE" },
  { id: "prompts", label: "Prompt library", icon: Layers3, group: "WORKSPACE" },
  { id: "traces", label: "Traces", icon: Activity, group: "OBSERVE & IMPROVE" },
  {
    id: "comparisons",
    label: "Comparisons",
    icon: GitCompareArrows,
    group: "OBSERVE & IMPROVE",
  },
  {
    id: "gates",
    label: "Quality gates",
    icon: ShieldCheck,
    group: "OBSERVE & IMPROVE",
  },
];

export function App() {
  const [page, setPage] = useState(location.hash.slice(1) || "overview");
  const [newRun, setNewRun] = useState(false),
    [runId, setRunId] = useState<string | null>(null),
    [resultId, setResultId] = useState<string | null>(null),
    [menu, setMenu] = useState(false),
    [toast, setToast] = useState("");
  const workspace = useData<Workspace>("workspace", "/workspace");
  const overview = useData<Overview>("overview", "/overview", true);
  const client = useQueryClient();
  const navigate = (next: string) => {
    setPage(next);
    location.hash = next;
    setRunId(null);
    setMenu(false);
  };
  useEffect(() => {
    const handle = () => {
      setPage(location.hash.slice(1) || "overview");
      setRunId(null);
    };
    addEventListener("hashchange", handle);
    return () => removeEventListener("hashchange", handle);
  }, []);
  useEffect(() => {
    if (toast) {
      const timeout = setTimeout(() => setToast(""), 4500);
      return () => clearTimeout(timeout);
    }
  }, [toast]);
  const refresh = () => {
    void client.invalidateQueries();
  };
  const title =
    navItems.find((n) => n.id === page)?.label ||
    (page === "settings" ? "Workspace settings" : "Overview");
  const openRun = (id: string) => {
    setRunId(id);
    setPage("experiments");
  };
  return (
    <div className="app-shell">
      <aside className={`sidebar ${menu ? "mobile-open" : ""}`}>
        <a
          className="brand"
          href="#overview"
          onClick={() => navigate("overview")}
        >
          <div className="brand-mark">
            <Activity size={23} strokeWidth={2.6} />
          </div>
          <span>
            evalscope<span className="brand-period">.</span>
          </span>
        </a>
        <button
          className="workspace-switch"
          onClick={() => navigate("settings")}
        >
          <span className="workspace-avatar">A</span>
          <span>
            <strong>Acme AI</strong>
            <small>Development workspace</small>
          </span>
          <ChevronDown size={15} />
        </button>
        <nav aria-label="Main navigation">
          {["WORKSPACE", "OBSERVE & IMPROVE"].map((group) => (
            <div className="nav-group" key={group}>
              <div className="nav-label">{group}</div>
              {navItems
                .filter((n) => n.group === group)
                .map(({ id, label, icon: Icon }) => (
                  <button
                    key={id}
                    onClick={() => navigate(id)}
                    className={`nav-item ${page === id ? "active" : ""}`}
                  >
                    <Icon size={18} />
                    <span>{label}</span>
                    {id === "experiments" && overview.data?.active_runs ? (
                      <span className="nav-count">
                        {overview.data.active_runs}
                      </span>
                    ) : null}
                    {id === "gates" && <span className="new-dot" />}
                  </button>
                ))}
            </div>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="local-card">
            <div>
              <span className="live-dot" /> LOCAL ENVIRONMENT
            </div>
            <p>Your data. Your evaluations.</p>
            <button onClick={() => navigate("settings")}>
              Manage workspace <ArrowUpRight size={14} />
            </button>
          </div>
          <button
            className={`nav-item ${page === "settings" ? "active" : ""}`}
            onClick={() => navigate("settings")}
          >
            <Settings2 size={18} />
            Settings
          </button>
          <a className="nav-item" href="/docs" target="_blank" rel="noreferrer">
            <BookOpen size={18} />
            API documentation <ExternalLink size={13} />
          </a>
          <div className="sidebar-user">
            <span className="user-avatar">D</span>
            <div>
              <strong>Developer</strong>
              <small>Local workspace</small>
            </div>
            <span className="version">v0.1</span>
          </div>
        </div>
      </aside>
      {menu && <div className="mobile-scrim" onClick={() => setMenu(false)} />}
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumbs">
            <button
              className="icon-button mobile-toggle"
              aria-label="Open navigation"
              onClick={() => setMenu(!menu)}
            >
              <Menu size={20} />
            </button>
            <span>Workspace</span>
            <ChevronRight size={14} />
            <strong>{runId ? "Run details" : title}</strong>
          </div>
          <div className="topbar-right">
            <span className="environment">
              <span className={overview.isError ? "offline-dot" : "live-dot"} />
              {overview.isError ? "Disconnected" : "Development"}
            </span>
            <a
              className="icon-button help-link"
              href="/docs"
              title="API documentation"
              target="_blank"
              rel="noreferrer"
            >
              <CircleHelp size={19} />
            </a>
            <span className="user-avatar small">D</span>
          </div>
        </header>
        <main>
          {overview.error && page !== "settings" && (
            <div className="connection">
              <ErrorBox error={overview.error} />
              <p>
                Start the API with <code>make dev</code>, or{" "}
                <button
                  className="text-link"
                  onClick={() => navigate("settings")}
                >
                  configure your access token
                </button>
                .
              </p>
            </div>
          )}
          {runId ? (
            <RunDetail
              id={runId}
              onBack={() => setRunId(null)}
              onResult={setResultId}
              notify={setToast}
            />
          ) : page === "overview" ? (
            <OverviewPage
              data={overview.data}
              loading={overview.isLoading}
              onNew={() => setNewRun(true)}
              onRun={openRun}
              navigate={navigate}
            />
          ) : page === "experiments" ? (
            <ExperimentsPage
              onNew={() => setNewRun(true)}
              onRun={openRun}
              notify={setToast}
            />
          ) : page === "datasets" ? (
            <DatasetsPage notify={setToast} />
          ) : page === "prompts" ? (
            <PromptsPage notify={setToast} />
          ) : page === "traces" ? (
            <TracesPage onResult={setResultId} />
          ) : page === "comparisons" || page === "gates" ? (
            <ComparisonsPage
              gates={page === "gates"}
              onResult={setResultId}
              notify={setToast}
            />
          ) : page === "settings" ? (
            <SettingsPage workspace={workspace.data} onSaved={refresh} />
          ) : (
            <Empty title="Page not found">
              <button
                className="text-link"
                onClick={() => navigate("overview")}
              >
                Return to overview
              </button>
            </Empty>
          )}
          <footer className="page-footer">
            <span>
              <Activity size={13} /> EvalScope{" "}
              <span className="footer-divider">/</span> Evaluate with evidence.
            </span>
            <span>Local prototype · Synthetic demo data</span>
          </footer>
        </main>
      </div>
      {newRun && (
        <NewRunModal
          onClose={() => setNewRun(false)}
          onCreated={(id) => {
            setNewRun(false);
            refresh();
            openRun(id);
            setToast(
              "Evaluation queued. Workers will pick it up automatically.",
            );
          }}
        />
      )}
      {resultId && (
        <ResultModal
          id={resultId}
          onClose={() => setResultId(null)}
          notify={setToast}
        />
      )}
      {toast && (
        <div className="toast" role="status">
          <CheckCircle2 size={18} />
          {toast}
          <button
            className="icon-button"
            aria-label="Dismiss notification"
            onClick={() => setToast("")}
          >
            <X size={16} />
          </button>
        </div>
      )}
    </div>
  );
}
