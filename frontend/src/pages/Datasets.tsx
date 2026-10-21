import React, { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowUpRight,
  ChevronLeft,
  Database,
  FileJson,
  GitBranch,
  Loader2,
  Plus,
  ShieldCheck,
  Upload,
} from "lucide-react";
import { api, post, date, type Case, type Dataset } from "../api";
import {
  Empty,
  ErrorBox,
  Loading,
  Button,
  Modal,
  PageHeading,
  Pagination,
} from "../components/ui";
import { useData } from "../hooks/useData";

export function DatasetsPage({ notify }: { notify: (s: string) => void }) {
  const datasets = useData<Dataset[]>("datasets", "/datasets");
  const [importing, setImporting] = useState(false),
    [selected, setSelected] = useState<Dataset | null>(null),
    [versionId, setVersionId] = useState(""),
    [newVersion, setNewVersion] = useState(false),
    [json, setJson] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<unknown>(null),
    [offset, setOffset] = useState(0);
  const version = versionId || selected?.versions[0]?.id || "";
  const cases = useQuery({
    queryKey: ["cases", version, offset],
    queryFn: () =>
      api<{ items: Case[]; total: number }>(
        `/dataset-versions/${version}/cases?offset=${offset}&limit=50`,
      ),
    enabled: !!version,
  });
  const client = useQueryClient();
  const beginVersion = async () => {
    setBusy(true);
    setError(null);
    try {
      const all: Case[] = [];
      let total = 1;
      while (all.length < total) {
        const batch = await api<{ items: Case[]; total: number }>(
          `/dataset-versions/${version}/cases?offset=${all.length}&limit=500`,
        );
        all.push(...batch.items);
        total = batch.total;
        if (!batch.items.length) break;
      }
      setJson(JSON.stringify(all, null, 2));
      setNewVersion(true);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };
  const createVersion = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const data = JSON.parse(json);
      await post(`/datasets/${selected!.id}/versions`, { cases: data });
      await client.invalidateQueries({ queryKey: ["datasets"] });
      const fresh = await api<Dataset>(`/datasets/${selected!.id}`);
      setSelected(fresh);
      setVersionId("");
      setOffset(0);
      setNewVersion(false);
      notify("New immutable dataset version created.");
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };
  if (selected)
    return (
      <>
        <button
          className="back-link"
          onClick={() => {
            setSelected(null);
            setVersionId("");
            setOffset(0);
          }}
        >
          <ChevronLeft size={16} />
          All datasets
        </button>
        <PageHeading
          eyebrow="VERSIONED GROUND TRUTH"
          title={selected.name}
          description={
            selected.description ||
            "Immutable snapshots for repeatable evaluations."
          }
        >
          <select
            aria-label="Dataset version"
            value={version}
            onChange={(e) => {
              setVersionId(e.target.value);
              setOffset(0);
            }}
          >
            {selected.versions.map((v) => (
              <option key={v.id} value={v.id}>
                Version {v.number} · {v.case_count} cases
              </option>
            ))}
          </select>
          <Button disabled={busy} onClick={() => void beginVersion()}>
            <Plus size={16} />
            Create version
          </Button>
        </PageHeading>
        <div className="info-box">
          <ShieldCheck size={17} />
          Existing versions stay immutable. The editor loads the complete
          snapshot. Save a new version to apply changes without altering
          previous runs.
        </div>
        <ErrorBox error={cases.error || error} />
        <section className="panel">
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>CASE ID</th>
                  <th>INPUT</th>
                  <th>REFERENCE ANSWER</th>
                  <th>TAGS</th>
                </tr>
              </thead>
              <tbody>
                {cases.data?.items.map((c) => (
                  <tr key={c.case_id}>
                    <td className="mono nowrap">{c.case_id}</td>
                    <td className="wrap-cell">{c.input}</td>
                    <td className="wrap-cell">{c.reference_answer}</td>
                    <td>
                      <div className="tag-list">
                        {c.tags.map((t) => (
                          <span className="tag" key={t}>
                            {t}
                          </span>
                        ))}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination
            offset={offset}
            limit={50}
            total={cases.data?.total || 0}
            onChange={setOffset}
          />
        </section>
        {newVersion && (
          <Modal
            title="Create dataset version"
            subtitle="Provide the complete case array for this new snapshot."
            onClose={() => setNewVersion(false)}
            wide
          >
            <form className="form-body" onSubmit={createVersion}>
              <ErrorBox error={error} />
              <label>
                Test cases · JSON array
                <textarea
                  className="code-input"
                  required
                  rows={16}
                  value={json}
                  onChange={(e) => setJson(e.target.value)}
                />
              </label>
              <div className="form-footer">
                <Button
                  variant="secondary"
                  type="button"
                  onClick={() => setNewVersion(false)}
                >
                  Cancel
                </Button>
                <Button disabled={busy}>
                  {busy ? (
                    <Loader2 className="spin" size={15} />
                  ) : (
                    <Plus size={15} />
                  )}
                  Save version
                </Button>
              </div>
            </form>
          </Modal>
        )}
      </>
    );
  return (
    <>
      <PageHeading
        eyebrow="THE FOUNDATION OF RELIABLE EVALUATION"
        title="Datasets"
        description="Curate your ground truth. Keep every version reproducible."
      >
        <Button onClick={() => setImporting(true)}>
          <Upload size={16} />
          Import dataset
        </Button>
      </PageHeading>
      <ErrorBox error={datasets.error} />
      {datasets.isLoading ? (
        <Loading />
      ) : datasets.data?.length ? (
        <div className="dataset-grid">
          {datasets.data.map((d) => (
            <button
              className="dataset-card"
              key={d.id}
              onClick={() => setSelected(d)}
            >
              <div className="card-top">
                <span className="dataset-icon">
                  <Database size={24} />
                </span>
                <span className="version-tag">v{d.versions[0]?.number}</span>
              </div>
              <h3>{d.name}</h3>
              <p>
                {d.description ||
                  "A versioned evaluation dataset, ready for your next experiment."}
              </p>
              <div className="dataset-meta">
                <span>
                  <FileJson size={14} />
                  {d.versions[0]?.case_count} cases
                </span>
                <span>
                  <GitBranch size={14} />
                  {d.versions.length} version
                  {d.versions.length === 1 ? "" : "s"}
                </span>
              </div>
              <div className="dataset-card-foot">
                <span>Created {date(d.created_at)}</span>
                <ArrowUpRight size={17} />
              </div>
            </button>
          ))}
        </div>
      ) : (
        <section className="panel">
          <Empty icon={Database} title="Start with your ground truth">
            Import a JSONL or CSV dataset to create your first immutable
            version.
          </Empty>
        </section>
      )}
      <div className="info-box">
        <ShieldCheck size={18} />
        <span>
          Every run is pinned to an immutable dataset version. Updating a
          dataset never changes an existing evaluation.
        </span>
      </div>
      {importing && (
        <ImportModal
          datasets={datasets.data || []}
          onClose={() => setImporting(false)}
          onDone={() => {
            setImporting(false);
            void client.invalidateQueries();
            notify("Dataset imported and versioned.");
          }}
        />
      )}
    </>
  );
}

export function ImportModal({
  datasets,
  onClose,
  onDone,
}: {
  datasets: Dataset[];
  onClose: () => void;
  onDone: () => void;
}) {
  const [name, setName] = useState(""),
    [format, setFormat] = useState("jsonl"),
    [content, setContent] = useState(""),
    [datasetId, setDatasetId] = useState(""),
    [error, setError] = useState<unknown>(null),
    [busy, setBusy] = useState(false);
  const file = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    if (f.size > 5_000_000) {
      setError(new Error("File must be under 5 MB."));
      return;
    }
    setFormat(f.name.endsWith(".csv") ? "csv" : "jsonl");
    setContent(await f.text());
    if (!name) setName(f.name.replace(/\.[^.]+$/, ""));
  };
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await post("/datasets/import", {
        name: name || "New version",
        format,
        content,
        dataset_id: datasetId || null,
      });
      onDone();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal
      title="Import evaluation dataset"
      subtitle="JSONL or CSV · up to 5,000 cases / 5 MB"
      onClose={onClose}
      wide
    >
      <form className="form-body" onSubmit={submit}>
        <ErrorBox error={error} />
        <div className="form-row">
          <label>
            Destination
            <select
              value={datasetId}
              onChange={(e) => setDatasetId(e.target.value)}
            >
              <option value="">Create new dataset</option>
              {datasets.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name} · new version
                </option>
              ))}
            </select>
          </label>
          {!datasetId && (
            <label>
              Dataset name
              <input
                required
                maxLength={120}
                value={name}
                placeholder="e.g. Customer support golden set"
                onChange={(e) => setName(e.target.value)}
              />
            </label>
          )}
        </div>
        <label className="upload-zone">
          <Upload size={24} />
          <strong>Choose a dataset file</strong>
          <span>or paste its content below</span>
          <input
            type="file"
            accept=".jsonl,.csv"
            onChange={(e) => void file(e)}
          />
        </label>
        <label>
          Format
          <select value={format} onChange={(e) => setFormat(e.target.value)}>
            <option value="jsonl">JSONL · one object per line</option>
            <option value="csv">CSV · header row required</option>
          </select>
        </label>
        <label>
          Dataset content
          <textarea
            required
            rows={8}
            className="code-input"
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder={
              '{"case_id":"case-001","input":"What is the refund policy?","reference_answer":"Refunds are available within 30 days.","tags":["policy"]}'
            }
          />
        </label>
        <p className="field-help">
          Required: case_id, input, reference_answer. Optional: tags,
          reference_contexts, relevant_document_ids, retrieved_document_ids. CSV
          list cells use JSON arrays.
        </p>
        <div className="form-footer">
          <Button variant="secondary" type="button" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={busy}>
            {busy ? (
              <Loader2 className="spin" size={16} />
            ) : (
              <Upload size={16} />
            )}
            Import & version
          </Button>
        </div>
      </form>
    </Modal>
  );
}
