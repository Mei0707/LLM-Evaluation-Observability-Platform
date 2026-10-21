import { Governance } from "../features/Governance";
import React, { useState } from "react";
import { Check, ExternalLink } from "lucide-react";
import { type Workspace } from "../api";
import { Badge, Button, PageHeading } from "../components/ui";

export function SettingsPage({
  workspace,
  onSaved,
}: {
  workspace?: Workspace;
  onSaved: () => void;
}) {
  const [token, setToken] = useState(
      sessionStorage.getItem("evalscope-token") || "",
    ),
    [saved, setSaved] = useState(false);
  return (
    <>
      <PageHeading
        eyebrow="YOUR LOCAL ENVIRONMENT"
        title="Workspace settings"
        description="Connection details and provider configuration for this development workspace."
      />
      <section className="panel settings-panel">
        <div className="panel-header">
          <h3>API connection</h3>
          <Badge status={workspace ? "COMPLETED" : "PENDING"} />
        </div>
        <div className="form-body">
          <label>
            Access token
            <input
              type="password"
              autoComplete="off"
              value={token}
              onChange={(e) => {
                setToken(e.target.value);
                setSaved(false);
              }}
              placeholder="Only required when EVALSCOPE_API_TOKEN is set"
            />
          </label>
          <p className="field-help">
            Stored in this browser tab's session storage. In users mode this is
            your personal identity token; project permissions are checked for
            every request.
          </p>
          <div>
            <Button
              onClick={() => {
                token
                  ? sessionStorage.setItem("evalscope-token", token)
                  : sessionStorage.removeItem("evalscope-token");
                location.reload();
              }}
            >
              <Check size={16} />
              Save connection
            </Button>
            {saved && (
              <span className="saved-message">
                Saved. Connection refreshed.
              </span>
            )}
          </div>
        </div>
      </section>
      <Governance workspace={workspace} onSaved={onSaved} />
      <section className="panel settings-panel">
        <div className="panel-header">
          <h3>Model provider</h3>
          <span className="muted-tag">SERVER CONFIGURATION</span>
        </div>
        <div className="form-body">
          <div className="provider-status">
            <span
              className={
                workspace?.provider_configured ? "live-dot" : "sub-dot"
              }
            />
            {workspace?.provider_configured
              ? "Live provider credentials configured"
              : "Deterministic mock provider is ready"}
          </div>
          <p>
            Live generation, embeddings, and judging use the server's
            OpenAI-compatible provider. Set these environment variables before
            starting the backend:
          </p>
          <pre>
            PROVIDER_API_KEY=your-provider-key{`\n`}
            PROVIDER_BASE_URL=https://your-provider.example/v1
          </pre>
          <p className="field-help">
            Keys stay on the server. Configure model IDs and token prices per
            experiment. Provider behavior may change even when the model ID
            stays the same.
          </p>
        </div>
      </section>
      <section className="panel settings-panel">
        <div className="panel-header">
          <h3>Workspace details</h3>
        </div>
        <div className="settings-facts">
          <div>
            <span>Project</span>
            <strong>{workspace?.project.name || "Disconnected"}</strong>
          </div>
          <div>
            <span>Mode</span>
            <strong>Local development prototype</strong>
          </div>
          <div>
            <span>Content capture</span>
            <strong>Off by default · enabled per experiment</strong>
          </div>
          <div>
            <span>Demo dataset</span>
            <strong>100 synthetic cases · no independent human labels</strong>
          </div>
          <div>
            <span>Documentation</span>
            <a
              href="/docs"
              target="_blank"
              rel="noreferrer"
              className="text-link"
            >
              Explore REST API <ExternalLink size={14} />
            </a>
          </div>
        </div>
      </section>
    </>
  );
}
