# Blinded human review and judge calibration

Import [the 100-case corpus](../datasets/review/corpus.jsonl), or use your own diverse production-derived cases with appropriate consent and governance. Run one or more compatible configurations with response capture enabled. Create a campaign under **Human review**. Campaigns freeze the selected result identities and the review rubric; all selected runs must use the same immutable dataset version.

Provision at least two real reviewers with distinct personal tokens and project role `reviewer`. Give each person their own token through an appropriate channel outside this tool. Reviewers can see the question, authored reference answer, reference evidence, captured actual retrieval context, and anonymous candidate output. Groundedness can therefore be judged against the same application evidence supplied to the LLM judge. The server does not return run IDs, model names, machine scores, intended fixture perturbations, or other reviewers' labels. Reviewer-role identities cannot access machine results or calibration reports through alternate API routes.

Each reviewer submits a normalized score, a correct/incomplete/hallucinated/irrelevant category, and a rationale. Labels are attributed to the authenticated identity, unique per item/reviewer, and immutable after submission. A single identity cannot supply multiple labels to simulate agreement. Reviewers should follow the rubric independently and avoid discussing answers before submission.

The coordinator's report includes:

- Distinct cases meeting the minimum reviewer count, and whether 100 cases have reached that threshold.
- Distinct attributed reviewer accounts and pairwise mean absolute score differences.
- Pairwise category agreement, including explicit disputed categories when votes tie.
- Per-reviewer-pair unweighted Cohen's kappa (null when undefined), with paired-answer counts.
- Per-item human median, paired judge MAE/agreement within .25, and case-level disagreements sorted by spread or judge divergence.
- Answer-level and per-run completion coverage, plus up to ten retained judge-disagreement examples with the actual output, reference, judge explanation and attributed human rationales. These are candidates for adjudication, not automatically proven judge failures.

The dashboard can download the coordinator's JSON calibration report. The 100-case target additionally requires the configured minimum reviews on every selected answer: reviewing one configuration's 100 answers does not complete a 200-answer campaign. Numeric calibration survives response expiry, but expired answer text is excluded from examples.

Judge pairs require actual stored `llm_judge` scores and the minimum distinct reviews. A single-review annotation on the legacy case inspector is not independent consensus. Missing judge scores remain missing; they are never synthesized. Reports are descriptive and do not pretend repeated reviewers or related cases are independent samples.

The bundled corpus has 100 unique questions across ten task families, clear provenance, and controlled mock-output perturbations. It is not a human-reviewed benchmark. Automated test labels live in explicitly named E2E fixture campaigns and do not constitute independent human research evidence. Distinct accounts alone cannot prove different humans or independent behavior; reviewer recruitment, blinding discipline, and study sign-off remain human responsibilities.

Response retention can remove material before review. Expired responses leave the queue, and submission against expired content returns 410. Numeric labels remain as evidence; rationale text follows content retention. Store/export a study report only under the applicable retention policy.

The [experiment and human-study protocol](live-study.md) supplies two frozen prompts, an independent reviewer guide, and a coordinator sign-off/adjudication template. [Real OpenAI model execution is now recorded](../studies/results/openai-2026-10-21/README.md); independent reviewers are still needed. Neither the real model outputs nor the subsequent automated calendar/JSON checks are independent human labels.
