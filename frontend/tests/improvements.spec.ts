import { test, expect, request } from "@playwright/test";
import { readFileSync } from "node:fs";

test("evaluate an HTTP application, inspect all-stage usage, and submit a blind review", async ({
  page,
}) => {
  const stamp = Date.now().toString();
  const dataset = await page.request.post("/api/v1/datasets", {
    data: {
      name: `Application dataset ${stamp}`,
      cases: [
        {
          case_id: "app-001",
          input: "Who owns service S0?",
          reference_answer: "Owner-0.",
          tags: ["e2e"],
        },
      ],
    },
  });
  expect(dataset.status()).toBe(201);
  const prompt = await page.request.post("/api/v1/prompts", {
    data: {
      name: `Application prompt ${stamp}`,
      template: "Answer {input} from the retrieved evidence.",
    },
  });
  expect(prompt.status()).toBe(201);
  await page.goto("/#applications");
  await page
    .getByRole("button", { name: "Register application", exact: true })
    .click();
  await page.getByLabel("Application name").fill(`Reference RAG ${stamp}`);
  await page
    .getByLabel("Evaluation endpoint")
    .fill(
      process.env.EVALSCOPE_APPLICATION_URL ||
        "http://reference-app:8080/evaluate",
    );
  await page
    .getByRole("button", { name: "Register target", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("button", { name: "Experiments", exact: true }).click();
  await page
    .getByRole("button", { name: "New evaluation", exact: true })
    .click();
  await page.getByLabel("Experiment name").fill(`Application run ${stamp}`);
  await page
    .getByLabel("Evaluation application")
    .selectOption({ label: `Reference RAG ${stamp}` });
  await page
    .getByLabel("Dataset version")
    .selectOption({ label: `Application dataset ${stamp} · v1 (1 cases)` });
  await page
    .getByLabel("Prompt version", { exact: true })
    .selectOption({ label: `Application prompt ${stamp}` });
  await page.getByLabel("Capture response content").check();
  await page
    .getByRole("button", { name: "Start evaluation", exact: true })
    .click();
  await expect(page.getByText("100% complete", { exact: true })).toBeVisible({
    timeout: 30000,
  });
  await expect(
    page.getByRole("heading", { name: "Usage ledger · every attempt" }),
  ).toBeVisible();
  await expect(
    page.getByText("unknown / unpriced", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "app-001", exact: true }).click();
  await expect(
    page.getByText("application.retrieval", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("application.tool", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("results.persist", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Close dialog", exact: true }).click();
  await page.getByRole("button", { name: "Human review", exact: true }).click();
  await page
    .getByRole("button", { name: "New review campaign", exact: true })
    .click();
  await page.getByLabel("Campaign name").fill(`E2E automated review ${stamp}`);
  await page
    .getByRole("checkbox", { name: new RegExp(`Application run ${stamp}`) })
    .check();
  await page
    .getByRole("button", { name: "Create campaign", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page
    .getByRole("button", { name: new RegExp(`E2E automated review ${stamp}`) })
    .click();
  await expect(
    page.getByRole("heading", { name: "ANONYMOUS RESPONSE" }),
  ).toBeVisible();
  await page.getByLabel("Independent quality score").fill("0.75");
  await page.getByLabel("Response category").selectOption("incomplete");
  await page
    .getByLabel("Your reasoning")
    .fill(
      "Automated workflow fixture only; this is not independent human research evidence.",
    );
  await page
    .getByRole("button", { name: "Submit independent review", exact: true })
    .click();
  await expect(
    page.getByRole("heading", {
      name: "You have reviewed every available answer",
    }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Calibration report", exact: true })
    .click();
  await expect(
    page.getByText(/Human review target still pending/),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", {
      name: "Judge disagreement examples",
      exact: true,
    }),
  ).toBeVisible();
  const downloaded = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Download calibration report", exact: true })
    .click();
  const reportFile = await downloaded;
  const report = JSON.parse(readFileSync((await reportFile.path())!, "utf8"));
  expect(report.campaign_complete).toBe(false);
  expect(report.consensus_item_count).toBe(0);
  expect(report.judge_consensus_pairs).toBe(0);
  expect(report.judge_disagreement_examples).toEqual([]);
});

test("HTTPS personal identities enforce project membership and reader permissions", async ({
  browser,
}) => {
  const url = process.env.EVALSCOPE_SECURE_URL;
  test.skip(!url, "Requires the isolated HTTPS deployment");
  const token = readFileSync("../.secrets/admin-token", "utf8").trim();
  const admin = await request.newContext({
    baseURL: url,
    ignoreHTTPSErrors: true,
    extraHTTPHeaders: { Authorization: `Bearer ${token}` },
  });
  const projectResponse = await admin.post("/api/v1/projects", {
    data: { name: `E2E private project ${Date.now()}` },
  });
  expect(projectResponse.status()).toBe(201);
  const project = await projectResponse.json();
  const response = await admin.post("/api/v1/users", {
    data: { name: "E2E reader identity" },
  });
  expect(response.status()).toBe(201);
  const user = await response.json();
  expect(
    (
      await admin.put("/api/v1/members", {
        headers: { "X-Project-ID": project.id },
        data: { user_id: user.id, role: "reader" },
      })
    ).status(),
  ).toBe(200);
  const reader = await request.newContext({
    baseURL: url,
    ignoreHTTPSErrors: true,
    extraHTTPHeaders: {
      Authorization: `Bearer ${user.token}`,
      "X-Project-ID": project.id,
    },
  });
  expect((await reader.get("/api/v1/datasets")).status()).toBe(200);
  expect(
    (
      await reader.post("/api/v1/prompts", {
        data: { name: "Forbidden", template: "{input}" },
      })
    ).status(),
  ).toBe(403);
  expect(
    (
      await reader.get("/api/v1/datasets", {
        headers: { "X-Project-ID": "00000000-0000-4000-8000-000000000001" },
      })
    ).status(),
  ).toBe(403);
  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  await context.addInitScript(
    ({ token, projectId }) => {
      sessionStorage.setItem("evalscope-token", token);
      sessionStorage.setItem("evalscope-project", projectId);
    },
    { token: user.token, projectId: project.id },
  );
  const page = await context.newPage();
  await page.goto(url!);
  await expect(
    page.getByText("E2E reader identity", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText(project.name, { exact: true })).toBeVisible();
  await context.close();
  await reader.dispose();
  await admin.dispose();
});
