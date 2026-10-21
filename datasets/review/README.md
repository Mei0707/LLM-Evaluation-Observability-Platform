# Diverse review corpus

`corpus.jsonl` contains 100 distinct fictional questions spanning arithmetic, multi-hop routing, UTC deadlines, policy boundaries, missing evidence, conflicting revisions, injected instructions, structured JSON, unavailable tools, and entity disambiguation. It replaces repeated support scenarios for research-oriented review. `knowledge.json` is the reference application's independent knowledge store.

Rebuild deterministically with `python scripts/build_review_corpus.py`. Each case includes source document IDs, reference context, an authored reference answer, and explicit provenance. Mock outputs contain controlled correct/incomplete/incorrect/irrelevant perturbations. They are fixtures, not measured model behavior or human labels. The intended perturbation is never shown in the blinded review payload.

No independent human scores are bundled. Import the corpus, run captured responses, create a review campaign, and collect at least two distinct authenticated reviewers per answer. The calibration report counts distinct cases, displays disagreement, and reports whether 100 cases meet that review threshold. Distinct accounts do not themselves prove that reviews were independently performed by different humans; that remains a study-management responsibility.

The reference app uses lexical retrieval, a real filesystem metadata tool call, and an extractive generator. It makes no LLM calls and reports zero LLM tokens. It is an application-integration fixture, not a semantic-reasoning baseline.
