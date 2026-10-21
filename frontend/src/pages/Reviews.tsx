import React, { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Plus, Users } from "lucide-react";
import { api, post, pct, type Run, type Workspace } from "../api";
import { useData } from "../hooks/useData";
import {
  Button,
  Empty,
  ErrorBox,
  Modal,
  PageHeading,
  Loading,
} from "../components/ui";

type Campaign = {
  id: string;
  name: string;
  rubric: string;
  minimum_reviews: number;
  total_items: number;
  consensus_items: number;
  my_reviews: number;
  independent_reviewers: number;
};
type Item = {
  id: string;
  input: string;
  reference_answer: string;
  reference_contexts: string[];
  retrieved_contexts: string[];
  retrieved_document_ids: string[];
  output: string;
};
type Calibration = {
  consensus_case_count: number;
  consensus_item_count: number;
  campaign_complete: boolean;
  independent_reviewer_count: number;
  human_corpus_target_met: boolean;
  judge_consensus_pairs: number;
  judge_mean_absolute_error: number | null;
  reviewer_mean_absolute_difference: number | null;
  category_agreement: number | null;
  category_agreement_by_reviewer_pair: {
    reviewer_ids: string[];
    paired_items: number;
    agreement: number;
    cohens_kappa: number | null;
  }[];
  judge_disagreement_examples: {
    item_id: string;
    input: string;
    reference_answer: string;
    output: string;
    judge_score: number;
    human_median: number;
    judge_reason: string;
    reviews: { reviewer_id: string; category: string; rationale: string }[];
  }[];
  example_method: string;
  disagreements: {
    item_id: string;
    human_median: number;
    judge_score: number | null;
    reviewer_spread: number;
    category: string;
  }[];
  method: string;
};

export function ReviewsPage({
  workspace,
  notify,
}: {
  workspace?: Workspace;
  notify: (s: string) => void;
}) {
  const campaigns = useData<Campaign[]>("campaigns", "/review-campaigns");
  const reviewer = workspace?.role === "reviewer";
  const runs = useQuery({
    queryKey: ["review-runs"],
    queryFn: () => api<{ items: Run[] }>("/runs?limit=200"),
    enabled: !reviewer,
  });
  const [selected, setSelected] = useState<Campaign | null>(null),
    [creating, setCreating] = useState(false),
    [name, setName] = useState(""),
    [chosen, setChosen] = useState<string[]>([]),
    [score, setScore] = useState(""),
    [category, setCategory] = useState("correct"),
    [rationale, setRationale] = useState(""),
    [error, setError] = useState<unknown>(null),
    [busy, setBusy] = useState(false),
    [showReport, setShowReport] = useState(false);
  const client = useQueryClient();
  const queue = useQuery({
    queryKey: ["review-queue", selected?.id],
    queryFn: () =>
      api<{ remaining: number; items: Item[] }>(
        `/review-campaigns/${selected!.id}/queue?limit=1`,
      ),
    enabled: !!selected && !showReport,
  });
  const report = useQuery({
    queryKey: ["review-report", selected?.id],
    queryFn: () =>
      api<Calibration>(`/review-campaigns/${selected!.id}/calibration`),
    enabled: !!selected && showReport && !reviewer,
  });
  async function create(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await post("/review-campaigns", {
        name,
        run_ids: chosen,
        minimum_reviews: 2,
      });
      setCreating(false);
      void client.invalidateQueries({ queryKey: ["campaigns"] });
      notify(
        "Blind review campaign created. Invite independent reviewers through project membership.",
      );
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const item = queue.data?.items[0];
    if (!item || !selected) return;
    setError(null);
    setBusy(true);
    try {
      await post(`/review-campaigns/${selected.id}/items/${item.id}/labels`, {
        score: +score,
        category,
        rationale,
      });
      setScore("");
      setRationale("");
      await client.invalidateQueries({
        queryKey: ["review-queue", selected.id],
      });
      void client.invalidateQueries({ queryKey: ["campaigns"] });
      notify("Independent review submitted. Machine scores remain hidden.");
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  const item = queue.data?.items[0];
  return (
    <>
      <PageHeading
        eyebrow="HUMAN EVIDENCE, EXPLICITLY ATTRIBUTED"
        title="Human review"
        description="Blinded answers. Independent reviewers. Calibration with visible disagreements."
      >
        {!reviewer && (
          <Button onClick={() => setCreating(true)}>
            <Plus size={16} />
            New review campaign
          </Button>
        )}
      </PageHeading>
      <ErrorBox error={campaigns.error || error} />
      {workspace?.auth_mode === "local" && (
        <div className="info-box">
          Local development has one reviewer identity. Enable personal-token
          identities to collect independent labels; duplicate labels from one
          person never count as agreement.
        </div>
      )}
      <div className="dataset-grid">
        {campaigns.data?.map((c) => (
          <button
            className="dataset-card"
            key={c.id}
            onClick={() => {
              setSelected(c);
              setShowReport(false);
            }}
          >
            <div className="card-top">
              <span className="dataset-icon">
                <Users size={24} />
              </span>
              <span className="version-tag">
                {c.my_reviews} reviewed by you
              </span>
            </div>
            <h3>{c.name}</h3>
            <p>
              {c.consensus_items}/{c.total_items} answers have at least{" "}
              {c.minimum_reviews} distinct reviews.
            </p>
            <div className="dataset-meta">
              {c.independent_reviewers} attributed reviewers
            </div>
          </button>
        ))}
      </div>
      {!campaigns.data?.length && (
        <section className="panel">
          <Empty icon={Users} title="Start collecting independent evidence">
            Create a campaign from completed runs with captured responses.
          </Empty>
        </section>
      )}
      {selected && (
        <section className="panel">
          <div className="panel-header">
            <div>
              <h3>{selected.name}</h3>
              <p>{queue.data?.remaining ?? "—"} answers remaining for you</p>
            </div>
            <div className="heading-actions">
              {!reviewer && (
                <Button
                  variant="secondary"
                  onClick={() => setShowReport(!showReport)}
                >
                  {showReport ? "Return to blind review" : "Calibration report"}
                </Button>
              )}
              <Button variant="secondary" onClick={() => setSelected(null)}>
                Close campaign
              </Button>
            </div>
          </div>
          {showReport ? (
            <div className="form-body">
              <ErrorBox error={report.error} />
              {report.data && (
                <>
                  <div className="info-box">
                    {report.data.consensus_case_count}/100 distinct cases with
                    consensus · {report.data.independent_reviewer_count}{" "}
                    reviewers ·{" "}
                    {report.data.human_corpus_target_met
                      ? "Corpus review target met"
                      : "Human review target still pending"}
                  </div>
                  <div className="settings-facts">
                    <div>
                      <span>Reviewer mean absolute difference</span>
                      <strong>
                        {report.data.reviewer_mean_absolute_difference?.toFixed(
                          3,
                        ) ?? "Not enough labels"}
                      </strong>
                    </div>
                    <div>
                      <span>Category agreement</span>
                      <strong>{pct(report.data.category_agreement)}</strong>
                    </div>
                    <div>
                      <span>Judge vs. human median MAE</span>
                      <strong>
                        {report.data.judge_mean_absolute_error?.toFixed(3) ??
                          "No paired judge scores"}
                      </strong>
                    </div>
                    <div>
                      <span>Judge / consensus pairs</span>
                      <strong>{report.data.judge_consensus_pairs}</strong>
                    </div>
                  </div>
                  <p>
                    {report.data.consensus_item_count}/{selected.total_items}{" "}
                    answers reviewed ·{" "}
                    {report.data.campaign_complete
                      ? "Campaign complete"
                      : "Campaign incomplete"}
                  </p>
                  <Button
                    variant="secondary"
                    onClick={() => {
                      const url = URL.createObjectURL(
                        new Blob([JSON.stringify(report.data, null, 2)], {
                          type: "application/json",
                        }),
                      );
                      const link = document.createElement("a");
                      link.href = url;
                      link.download = `calibration-${selected.id}.json`;
                      link.click();
                      URL.revokeObjectURL(url);
                    }}
                  >
                    Download calibration report
                  </Button>
                  <h3>Disagreements to investigate</h3>
                  {report.data.disagreements.map((d) => (
                    <div className="score-row" key={d.item_id}>
                      <code>{d.item_id.slice(0, 8)}</code>
                      <span>
                        Human {pct(d.human_median)} · judge {pct(d.judge_score)}{" "}
                        · spread {pct(d.reviewer_spread)} · {d.category}
                      </span>
                    </div>
                  ))}
                  <h3>Agreement by reviewer pair</h3>
                  {report.data.category_agreement_by_reviewer_pair.map(
                    (pair) => (
                      <p key={pair.reviewer_ids.join("-")}>
                        {pair.reviewer_ids
                          .map((id) => id.slice(0, 8))
                          .join(" / ")}
                        : {pair.paired_items} answers · agreement{" "}
                        {pct(pair.agreement)} · Cohen’s κ{" "}
                        {pair.cohens_kappa?.toFixed(3) ??
                          "Undefined (no category variation)"}
                      </p>
                    ),
                  )}
                  <h3>Judge disagreement examples</h3>
                  <p className="field-help">{report.data.example_method}</p>
                  {report.data.judge_disagreement_examples.map((example) => (
                    <details key={example.item_id}>
                      <summary>
                        {example.input} · human {pct(example.human_median)} /
                        judge {pct(example.judge_score)}
                      </summary>
                      <p>
                        <strong>Reference:</strong> {example.reference_answer}
                      </p>
                      <p>
                        <strong>Response:</strong> {example.output}
                      </p>
                      <p>
                        <strong>Judge reasoning:</strong> {example.judge_reason}
                      </p>
                      {example.reviews.map((review) => (
                        <p key={review.reviewer_id}>
                          <strong>{review.category}:</strong> {review.rationale}
                        </p>
                      ))}
                    </details>
                  ))}
                  <p className="field-help">{report.data.method}</p>
                </>
              )}
            </div>
          ) : queue.isLoading ? (
            <Loading />
          ) : item ? (
            <form className="form-body" onSubmit={submit}>
              <ErrorBox error={queue.error} />
              <div className="info-box">{selected.rubric}</div>
              <div className="answer-block">
                <h4>QUESTION</h4>
                <p>{item.input}</p>
              </div>
              <div className="answer-columns">
                <div className="answer-block">
                  <h4>REFERENCE ANSWER</h4>
                  <p>{item.reference_answer}</p>
                </div>
                <div className="answer-block generated">
                  <h4>ANONYMOUS RESPONSE</h4>
                  <p>{item.output}</p>
                </div>
              </div>
              <details>
                <summary>Reference evidence</summary>
                <p>{item.reference_contexts.join("\n")}</p>
              </details>
              <details>
                <summary>Actually retrieved evidence</summary>
                <p>
                  {item.retrieved_contexts.join("\n") ||
                    "No captured retrieval context."}
                </p>
                <p className="field-help">
                  Document IDs:{" "}
                  {item.retrieved_document_ids.join(", ") || "None"}
                </p>
              </details>
              <div className="form-row">
                <label>
                  Independent quality score
                  <input
                    required
                    type="number"
                    min={0}
                    max={1}
                    step="0.05"
                    value={score}
                    onChange={(e) => setScore(e.target.value)}
                  />
                </label>
                <label>
                  Response category
                  <select
                    value={category}
                    onChange={(e) => setCategory(e.target.value)}
                  >
                    {[
                      "correct",
                      "incomplete",
                      "hallucinated",
                      "irrelevant",
                    ].map((c) => (
                      <option key={c}>{c}</option>
                    ))}
                  </select>
                </label>
              </div>
              <label>
                Your reasoning
                <textarea
                  required
                  maxLength={2000}
                  rows={3}
                  value={rationale}
                  onChange={(e) => setRationale(e.target.value)}
                />
              </label>
              <div className="form-footer">
                <Button disabled={busy}>
                  <Check size={16} />
                  Submit independent review
                </Button>
              </div>
            </form>
          ) : (
            <Empty
              icon={Check}
              title="You have reviewed every available answer"
            >
              A second reviewer must submit their own labels before consensus is
              reported. Expired responses are excluded.
            </Empty>
          )}
        </section>
      )}
      {creating && (
        <Modal
          title="Create blind review campaign"
          subtitle="Select compatible completed runs. Model names and scores are withheld from reviewers."
          onClose={() => setCreating(false)}
          wide
        >
          <form className="form-body" onSubmit={create}>
            <ErrorBox error={error} />
            <label>
              Campaign name
              <input
                required
                maxLength={120}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <fieldset>
              <legend>Completed runs with content capture</legend>
              {runs.data?.items
                .filter(
                  (r) =>
                    ["COMPLETED", "PARTIAL"].includes(r.status) &&
                    r.config.capture_content,
                )
                .map((r) => (
                  <label className="check-option" key={r.id}>
                    <input
                      type="checkbox"
                      checked={chosen.includes(r.id)}
                      onChange={() =>
                        setChosen(
                          chosen.includes(r.id)
                            ? chosen.filter((id) => id !== r.id)
                            : [...chosen, r.id],
                        )
                      }
                    />
                    {r.name} · {r.id.slice(0, 8)}
                  </label>
                ))}
            </fieldset>
            <p className="field-help">
              A minimum of two distinct authenticated reviewers is required per
              response. Labels are immutable and never generated automatically.
            </p>
            <div className="form-footer">
              <Button disabled={busy || !chosen.length}>Create campaign</Button>
            </div>
          </form>
        </Modal>
      )}
    </>
  );
}
