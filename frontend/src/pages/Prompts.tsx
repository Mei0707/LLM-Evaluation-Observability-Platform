import React, { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Check, GitBranch, Layers3, Plus } from "lucide-react";
import { post, date, type Prompt } from "../api";
import { Empty, ErrorBox, Button, Modal, PageHeading } from "../components/ui";
import { useData } from "../hooks/useData";

export function PromptsPage({ notify }: { notify: (s: string) => void }) {
  const prompts = useData<Prompt[]>("prompts", "/prompts");
  const [editing, setEditing] = useState(false),
    [name, setName] = useState(""),
    [template, setTemplate] = useState(
      "Answer the question using the context.\nContext: {contexts}\nQuestion: {input}",
    ),
    [error, setError] = useState<unknown>(null),
    [busy, setBusy] = useState(false);
  const client = useQueryClient();
  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await post("/prompts", { name, template });
      void client.invalidateQueries();
      setEditing(false);
      notify("Immutable prompt version saved.");
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <PageHeading
        eyebrow="SMALL CHANGES. MEASURABLE IMPACT."
        title="Prompt library"
        description="Version your instructions and trace every result back to its source."
      >
        <Button
          onClick={() => {
            setName("");
            setEditing(true);
          }}
        >
          <Plus size={16} />
          New prompt version
        </Button>
      </PageHeading>
      <ErrorBox error={prompts.error} />
      <div className="prompt-grid">
        {prompts.data?.map((p) => (
          <section className="panel prompt-card" key={p.id}>
            <div className="panel-header">
              <div>
                <span className="eyebrow">
                  IMMUTABLE VERSION · {p.id.slice(0, 8)}
                </span>
                <h3>{p.name}</h3>
              </div>
              <span className="table-icon">
                <Layers3 size={20} />
              </span>
            </div>
            <pre>{p.template}</pre>
            <div className="panel-bottom">
              <span>{date(p.created_at)}</span>
              <button
                className="text-link"
                onClick={() => {
                  setName(`${p.name} · next`);
                  setTemplate(p.template);
                  setEditing(true);
                }}
              >
                Create variant <GitBranch size={15} />
              </button>
            </div>
          </section>
        ))}
      </div>
      {prompts.data?.length === 0 && (
        <Empty icon={Layers3} title="Your next great prompt starts here">
          Create a version using {"{input}"} and optional {"{contexts}"}{" "}
          placeholders.
        </Empty>
      )}
      {editing && (
        <Modal
          title="New prompt version"
          subtitle="Saved versions remain immutable for reproducibility."
          onClose={() => setEditing(false)}
          wide
        >
          <form className="form-body" onSubmit={save}>
            <ErrorBox error={error} />
            <label>
              Version name
              <input
                required
                maxLength={120}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <label>
              Prompt template
              <textarea
                required
                rows={12}
                className="code-input"
                value={template}
                onChange={(e) => setTemplate(e.target.value)}
              />
            </label>
            <div className="info-box">
              Use {"{input}"} for the test question and {"{contexts}"} for
              reference context. These are the only supported placeholders.
            </div>
            <div className="form-footer">
              <Button
                variant="secondary"
                type="button"
                onClick={() => setEditing(false)}
              >
                Cancel
              </Button>
              <Button disabled={busy}>
                <Check size={16} />
                Save prompt version
              </Button>
            </div>
          </form>
        </Modal>
      )}
    </>
  );
}
