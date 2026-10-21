from sqlalchemy import select
from .models import Project, Dataset, PromptVersion, Experiment, Baseline, Run, uid
from .schemas import CaseInput, RunConfig
from .services import create_version, start_run

DEFAULT_PROJECT = "00000000-0000-4000-8000-000000000001"
POLICIES = [
    ("What is the refund policy?", "Refunds are available within 30 days.", "policy"),
    (
        "How do I reset my password?",
        "Select Forgot password on the sign-in page.",
        "account",
    ),
    (
        "How long does standard shipping take?",
        "Standard shipping takes 3 to 5 business days.",
        "shipping",
    ),
    (
        "Can I change my subscription plan?",
        "You can change your plan from Billing settings.",
        "billing",
    ),
    (
        "Is two-factor authentication available?",
        "Two-factor authentication is available in Security settings.",
        "security",
    ),
    (
        "What payment methods are accepted?",
        "We accept credit cards and bank transfers.",
        "billing",
    ),
    (
        "Can I export my data?",
        "You can export your data as CSV from Settings.",
        "account",
    ),
    ("How do I contact support?", "Contact support at support@example.com.", "support"),
    (
        "Are API requests rate limited?",
        "The standard API limit is 100 requests per minute.",
        "technical",
    ),
    (
        "How do I cancel my subscription?",
        "Cancel your subscription in Billing settings before renewal.",
        "billing",
    ),
]


def seed(session):
    if not session.get(Project, DEFAULT_PROJECT):
        session.add(Project(id=DEFAULT_PROJECT, name="Acme AI workspace"))
        session.flush()
    if session.scalar(
        select(Dataset.id).where(Dataset.project_id == DEFAULT_PROJECT).limit(1)
    ):
        return
    dataset = Dataset(
        id=uid(),
        project_id=DEFAULT_PROJECT,
        name="Customer support · Golden set",
        description="100 synthetic policy cases for deterministic demonstrations. References are authored fixtures, not independent human-reviewed labels.",
    )
    session.add(dataset)
    session.flush()
    cases = []
    for index in range(100):
        question, answer, tag = POLICIES[index % len(POLICIES)]
        cases.append(
            CaseInput(
                case_id=f"support-{index+1:03}",
                input=question
                + (f" (Customer scenario {index//10+1})" if index >= 10 else ""),
                reference_answer=answer,
                reference_contexts=[answer],
                relevant_document_ids=[f"policy-{index%10}"],
                retrieved_document_ids=[f"policy-{index%10}", "general-faq"],
                tags=[tag, "synthetic"],
            )
        )
    version = create_version(session, dataset, cases)
    prompt = PromptVersion(
        id=uid(),
        project_id=DEFAULT_PROJECT,
        name="Support assistant · v1",
        template="Use the policy context to answer the customer accurately.\nContext: {contexts}\nQuestion: {input}",
    )
    session.add(prompt)
    session.flush()
    for name, model in [
        ("Support assistant · baseline", "mock-precise"),
        ("Support assistant · candidate", "mock-regressed"),
    ]:
        config = RunConfig(
            dataset_version_id=version.id,
            prompt_version_id=prompt.id,
            model=model,
            capture_content=True,
            mock_latency_ms=45,
        ).model_dump()
        experiment = Experiment(
            id=uid(), project_id=DEFAULT_PROJECT, name=name, config=config
        )
        session.add(experiment)
        session.flush()
        start_run(session, experiment)
