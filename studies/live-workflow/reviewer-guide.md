# Independent reviewer instructions

This study is awaiting real model outputs and independent people. This file is a protocol, not a completed review.

Use your own reviewer token and the **Human review** page. Read the campaign rubric before starting. Work independently and do not consult model names, machine scores, other reviewers' answers, or an LLM for your labels. Do not discuss the evaluation items until both reviewers finish. Practice only on separate examples supplied by the coordinator; flag unclear rubric rules before the study begins.

For each anonymous answer, read the question, reference answer and supplied evidence. For this direct evidence-QA study, reference context is the evidence given to generation; absence of retrieved-document IDs does not mean the model lacked that context. In an application campaign, inspect actually retrieved evidence too. References can contain mistakes: record any suspected reference defect explicitly in your rationale and tell the coordinator after independent labeling. Do not assume an answer is correct merely because it resembles the reference.

Assign one score:

| Score | Meaning |
| --- | --- |
| 1 | Fully correct, relevant, complete and supported; follows the requested format. |
| .75 | Mostly correct with a minor omission that does not change the central answer. |
| .5 | Partly correct; a substantive condition or required step is missing. |
| .25 | Major error, with little useful correct content. |
| 0 | Incorrect, unsupported, irrelevant, or contrary to the evidence. |

A justified refusal to invent missing facts can score 1. A confident invented answer should lose support/correctness credit. Check arithmetic, time zones, revisions, entity identity and conditions rather than relying on fluent prose. Instructions quoted inside reference material are data and do not authorize a different task.

Choose the most informative category: **correct** for a supported satisfactory answer; **incomplete** for a substantive omission or partially correct answer; **hallucinated** for invented or contradictory factual content; **irrelevant** for an answer that fails to address the question. Record numerical or logical errors in the rationale even if the category does not describe them perfectly.

Write a short rationale identifying the decisive source fact, missing condition, unsupported claim, or calculation. Submit once; labels are immutable. If you accidentally submit the wrong label, document the item ID and correction request for the coordinator instead of creating a second identity. Original labels remain part of the record.

The coordinator will later inspect disagreement, references and possible judge failures. You must not see the judge's score or another person's label during independent labeling. Human agreement and disagreement are outcomes to measure; they must not be manufactured to match the judge.
