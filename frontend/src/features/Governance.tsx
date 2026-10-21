import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, post, type Workspace } from "../api";
import { Button, ErrorBox } from "../components/ui";
import type { Credential } from "../pages/Applications";

type Person = { id: string; name: string; active: boolean };
type Policy = { enabled: boolean; content_days: number; trace_days: number };

export function Governance({
  workspace,
  onSaved,
}: {
  workspace?: Workspace;
  onSaved: () => void;
}) {
  const admin = workspace?.role === "admin";
  const projects = useQuery({
    queryKey: ["projects"],
    queryFn: () => api<{ id: string; name: string }[]>("/projects"),
  });
  const members = useQuery({
    queryKey: ["members"],
    queryFn: () => api<{ user: Person; role: string }[]>("/members"),
    enabled: admin,
  });
  const credentials = useQuery({
    queryKey: ["credentials"],
    queryFn: () => api<Credential[]>("/credentials"),
    enabled: admin,
  });
  const policy = useQuery({
    queryKey: ["retention"],
    queryFn: () => api<Policy>("/retention"),
    enabled: admin,
  });
  const [error, setError] = useState<unknown>(null),
    [message, setMessage] = useState(""),
    [userName, setUserName] = useState(""),
    [userId, setUserId] = useState(""),
    [role, setRole] = useState("reviewer"),
    [issued, setIssued] = useState(""),
    [secretName, setSecretName] = useState(""),
    [secret, setSecret] = useState(""),
    [credentialId, setCredentialId] = useState(""),
    [retention, setRetention] = useState<Policy | null>(null),
    [busy, setBusy] = useState(false);
  async function perform(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    setMessage("");
    try {
      await action();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  const refresh = () => {
    void members.refetch();
    void credentials.refetch();
    void policy.refetch();
    onSaved();
  };
  const selectedPolicy = retention ||
    policy.data || { enabled: false, content_days: 30, trace_days: 90 };
  return (
    <>
      <section className="panel settings-panel">
        <div className="panel-header">
          <h3>Identity & project</h3>
          <span className="muted-tag">
            {workspace?.auth_mode || "local"} ·{" "}
            {workspace?.role || "disconnected"}
          </span>
        </div>
        <div className="form-body">
          <p>
            Signed in as {workspace?.user?.name || "local developer"}. Project
            roles are checked by the API. Personal tokens can be rotated or
            revoked.
          </p>
          <label>
            Active project
            <select
              value={
                sessionStorage.getItem("evalscope-project") ||
                workspace?.project.id ||
                ""
              }
              onChange={(e) => {
                sessionStorage.setItem("evalscope-project", e.target.value);
                location.reload();
              }}
            >
              {projects.data?.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
        </div>
      </section>
      {admin && (
        <>
          <ErrorBox
            error={error || members.error || credentials.error || policy.error}
          />
          {message && (
            <div className="info-box" role="status">
              {message}
            </div>
          )}
          <section className="panel settings-panel">
            <div className="panel-header">
              <h3>Project membership</h3>
            </div>
            <div className="form-body">
              <div className="settings-facts">
                {members.data?.map((m) => (
                  <div key={m.user.id}>
                    <span>
                      {m.user.name} · {m.user.id.slice(0, 8)}
                    </span>
                    <strong>
                      {m.role} · {m.user.active ? "active" : "disabled"}
                    </strong>
                    {workspace?.user?.is_admin && (
                      <Button
                        variant="secondary"
                        disabled={busy}
                        onClick={() =>
                          void perform(async () => {
                            await api(`/users/${m.user.id}`, {
                              method: "PATCH",
                              body: JSON.stringify({ active: !m.user.active }),
                            });
                            refresh();
                          })
                        }
                      >
                        {m.user.active ? "Disable identity" : "Enable identity"}
                      </Button>
                    )}
                    <Button
                      variant="secondary"
                      disabled={busy}
                      onClick={() =>
                        void perform(async () => {
                          await api(`/members/${m.user.id}`, {
                            method: "DELETE",
                          });
                          refresh();
                        })
                      }
                    >
                      Remove membership
                    </Button>
                  </div>
                ))}
              </div>
              {workspace?.user?.is_admin && (
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    void perform(async () => {
                      const user = await post<Person & { token: string }>(
                        "/users",
                        { name: userName },
                      );
                      await api("/members", {
                        method: "PUT",
                        body: JSON.stringify({ user_id: user.id, role }),
                      });
                      setIssued(user.token);
                      setUserId(user.id);
                      setUserName("");
                      refresh();
                      setMessage(
                        "Identity created. Copy its token now; it will not be returned again.",
                      );
                    });
                  }}
                >
                  <div className="form-row">
                    <label>
                      New user name
                      <input
                        required
                        value={userName}
                        onChange={(e) => setUserName(e.target.value)}
                      />
                    </label>
                    <label>
                      Initial project role
                      <select
                        value={role}
                        onChange={(e) => setRole(e.target.value)}
                      >
                        {["reader", "reviewer", "editor", "admin"].map((r) => (
                          <option key={r}>{r}</option>
                        ))}
                      </select>
                    </label>
                  </div>
                  <Button disabled={busy}>Create identity & membership</Button>
                </form>
              )}
              {issued && (
                <label>
                  New personal token · shown once
                  <input readOnly type="password" value={issued} />
                  <Button
                    variant="secondary"
                    onClick={() => void navigator.clipboard.writeText(issued)}
                  >
                    Copy token
                  </Button>
                  <Button variant="secondary" onClick={() => setIssued("")}>
                    Dismiss token
                  </Button>
                </label>
              )}
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  void perform(async () => {
                    await api("/members", {
                      method: "PUT",
                      body: JSON.stringify({ user_id: userId, role }),
                    });
                    refresh();
                    setMessage("Project role saved.");
                  });
                }}
              >
                <div className="form-row">
                  <label>
                    Existing user ID
                    <input
                      required
                      value={userId}
                      onChange={(e) => setUserId(e.target.value)}
                    />
                  </label>
                  <label>
                    Project role
                    <select
                      value={role}
                      onChange={(e) => setRole(e.target.value)}
                    >
                      {["reader", "reviewer", "editor", "admin"].map((r) => (
                        <option key={r}>{r}</option>
                      ))}
                    </select>
                  </label>
                </div>
                <Button variant="secondary" disabled={busy}>
                  Assign project role
                </Button>
              </form>
            </div>
          </section>
          <section className="panel settings-panel">
            <div className="panel-header">
              <h3>Encrypted credentials</h3>
              <span className="muted-tag">
                {workspace?.credential_encryption
                  ? "ENCRYPTION READY"
                  : "MASTER KEY REQUIRED"}
              </span>
            </div>
            <div className="form-body">
              <p>
                Secrets are encrypted before database storage. The master key is
                supplied separately through environment or a mounted secret
                file. Secret values are never returned by the API.
              </p>
              {credentials.data?.map((c) => (
                <div className="credential-row" key={c.id}>
                  <span>
                    {c.name} · v{c.version} · {c.active ? "active" : "disabled"}
                  </span>
                  <Button
                    variant="secondary"
                    onClick={() => {
                      setCredentialId(c.id);
                      setSecretName(c.name);
                      setSecret("");
                    }}
                  >
                    Rotate
                  </Button>
                  <Button
                    variant="secondary"
                    disabled={busy || !c.active}
                    onClick={() =>
                      void perform(async () => {
                        await api("/credentials/" + c.id, { method: "DELETE" });
                        refresh();
                      })
                    }
                  >
                    Disable
                  </Button>
                </div>
              ))}
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  void perform(async () => {
                    await api(
                      "/credentials" + (credentialId ? "/" + credentialId : ""),
                      {
                        method: credentialId ? "PUT" : "POST",
                        body: JSON.stringify({
                          name: secretName,
                          value: secret,
                        }),
                      },
                    );
                    setSecret("");
                    setSecretName("");
                    setCredentialId("");
                    refresh();
                    setMessage("Encrypted credential saved.");
                  });
                }}
              >
                <div className="form-row">
                  <label>
                    Credential name
                    <input
                      required
                      value={secretName}
                      onChange={(e) => setSecretName(e.target.value)}
                    />
                  </label>
                  <label>
                    Secret value
                    <input
                      required
                      type="password"
                      autoComplete="new-password"
                      value={secret}
                      onChange={(e) => setSecret(e.target.value)}
                    />
                  </label>
                </div>
                <Button disabled={busy || !workspace?.credential_encryption}>
                  {credentialId
                    ? "Rotate credential"
                    : "Store encrypted credential"}
                </Button>
              </form>
            </div>
          </section>
          <section className="panel settings-panel">
            <div className="panel-header">
              <h3>Content & trace retention</h3>
            </div>
            <div className="form-body">
              <p>
                Enabled policies are enforced every five minutes. Captured
                responses and explanation text expire; numeric scores, labels,
                usage, and audit evidence remain. Dataset snapshots have a
                separate explicit lifecycle.
              </p>
              <label className="capture-option">
                <input
                  type="checkbox"
                  checked={selectedPolicy.enabled}
                  onChange={(e) =>
                    setRetention({
                      ...selectedPolicy,
                      enabled: e.target.checked,
                    })
                  }
                />
                Enable automatic retention
              </label>
              <div className="form-row">
                <label>
                  Captured content lifetime (days)
                  <input
                    type="number"
                    min={1}
                    max={3650}
                    value={selectedPolicy.content_days}
                    onChange={(e) =>
                      setRetention({
                        ...selectedPolicy,
                        content_days: +e.target.value,
                      })
                    }
                  />
                </label>
                <label>
                  Trace lifetime (days)
                  <input
                    type="number"
                    min={1}
                    max={3650}
                    value={selectedPolicy.trace_days}
                    onChange={(e) =>
                      setRetention({
                        ...selectedPolicy,
                        trace_days: +e.target.value,
                      })
                    }
                  />
                </label>
              </div>
              <div className="heading-actions">
                <Button
                  disabled={busy}
                  onClick={() =>
                    void perform(async () => {
                      await api("/retention", {
                        method: "PUT",
                        body: JSON.stringify(selectedPolicy),
                      });
                      refresh();
                      setMessage("Retention policy saved.");
                    })
                  }
                >
                  Save retention policy
                </Button>
                <Button
                  variant="secondary"
                  disabled={busy}
                  onClick={() =>
                    void perform(async () => {
                      const preview = await post("/retention/sweep", {
                        dry_run: true,
                      });
                      setMessage(JSON.stringify(preview));
                    })
                  }
                >
                  Preview cleanup
                </Button>
                <Button
                  variant="secondary"
                  disabled={busy || !policy.data?.enabled}
                  onClick={() =>
                    void perform(async () => {
                      const result = await post("/retention/sweep", {
                        dry_run: false,
                      });
                      setMessage(JSON.stringify(result));
                    })
                  }
                >
                  Purge expired content
                </Button>
              </div>
            </div>
          </section>
        </>
      )}
    </>
  );
}
