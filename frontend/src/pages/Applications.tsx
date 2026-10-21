import React, { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Plug, Plus } from "lucide-react";
import { api, post } from "../api";
import { useData } from "../hooks/useData";
import { Button, Empty, ErrorBox, Modal, PageHeading } from "../components/ui";

export type Target = {
  id: string;
  name: string;
  url: string;
  protocol: string;
  credential_id: string | null;
};
export type Credential = {
  id: string;
  name: string;
  version: number;
  active: boolean;
};

export function ApplicationsPage({
  notify,
}: {
  notify: (text: string) => void;
}) {
  const targets = useData<Target[]>("targets", "/targets");
  const credentials = useData<Credential[]>("credentials", "/credentials");
  const [open, setOpen] = useState(false),
    [name, setName] = useState(""),
    [url, setUrl] = useState(""),
    [credential, setCredential] = useState(""),
    [error, setError] = useState<unknown>(null),
    [busy, setBusy] = useState(false);
  const client = useQueryClient();
  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await post("/targets", { name, url, credential_id: credential || null });
      void client.invalidateQueries();
      setOpen(false);
      notify("Application target registered. Select it in a new evaluation.");
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <PageHeading
        eyebrow="EVALUATE THE WHOLE APPLICATION"
        title="Applications"
        description="Measure actual retrieval, tool use, and answers through a versioned HTTP contract."
      >
        <Button onClick={() => setOpen(true)}>
          <Plus size={16} />
          Register application
        </Button>
      </PageHeading>
      <ErrorBox error={targets.error} />
      <div className="dataset-grid">
        {targets.data?.map((t) => (
          <section className="panel experiment-card" key={t.id}>
            <span className="dataset-icon">
              <Plug size={23} />
            </span>
            <h3>{t.name}</h3>
            <p className="mono">{t.url}</p>
            <div className="tag-list">
              <span className="tag">{t.protocol}</span>
              <span className="tag">
                {t.credential_id ? "Encrypted credential" : "No authentication"}
              </span>
            </div>
            <p className="field-help">
              Each run freezes this target. Reference answers and labeled
              document IDs are withheld from the application.
            </p>
          </section>
        ))}
      </div>
      {!targets.data?.length && (
        <section className="panel">
          <Empty icon={Plug} title="Bring your application into the loop">
            Register your RAG or agent endpoint, then choose it when creating an
            evaluation.
          </Empty>
        </section>
      )}
      <section className="panel">
        <div className="panel-header">
          <h3>Application contract · evalscope-v1</h3>
        </div>
        <div className="form-body">
          <p>
            Receive the question and frozen generation settings. Return the
            actual output, retrieved document IDs, grounding contexts, stage
            spans, and usage. EvalScope scores the result and accounts for every
            attempt.
          </p>
          <pre>
            {JSON.stringify(
              {
                request: {
                  input: "Customer question",
                  configuration: {
                    model: "your-model",
                    temperature: 0,
                    prompt_template: "Answer {input}",
                  },
                },
                response: {
                  output: "Application answer",
                  retrieved_document_ids: ["doc-001"],
                  contexts: ["Retrieved passage"],
                  spans: [],
                  usage: [
                    {
                      scope: "generation",
                      model: "your-model",
                      input_tokens: 100,
                      output_tokens: 30,
                    },
                  ],
                },
              },
              null,
              2,
            )}
          </pre>
          <p className="field-help">
            An administrator must allow the hostname in EVALSCOPE_TARGET_HOSTS.
            Redirects are rejected. Run the included reference RAG application
            with the applications Docker profile.
          </p>
        </div>
      </section>
      {open && (
        <Modal
          title="Register application"
          subtitle="Application targets are immutable. Register a new target to change its endpoint."
          onClose={() => setOpen(false)}
        >
          <form className="form-body" onSubmit={save}>
            <ErrorBox error={error} />
            <label>
              Application name
              <input
                required
                maxLength={120}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <label>
              Evaluation endpoint
              <input
                type="url"
                required
                placeholder="http://reference-app:8080/evaluate"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
              />
            </label>
            <label>
              Bearer credential
              <select
                value={credential}
                onChange={(e) => setCredential(e.target.value)}
              >
                <option value="">No credential</option>
                {credentials.data
                  ?.filter((c) => c.active)
                  .map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name} · v{c.version}
                    </option>
                  ))}
              </select>
            </label>
            <div className="form-footer">
              <Button
                type="button"
                variant="secondary"
                onClick={() => setOpen(false)}
              >
                Cancel
              </Button>
              <Button disabled={busy}>Register target</Button>
            </div>
          </form>
        </Modal>
      )}
    </>
  );
}
