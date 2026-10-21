import { test, expect } from "@playwright/test";

test("import, version, run, inspect trace, compare, and reject a regression", async ({
  page,
}) => {
  const stamp = Date.now().toString();
  await page.goto("/");
  await page.getByRole("button", { name: "Datasets", exact: true }).click();
  await page
    .getByRole("button", { name: "Import dataset", exact: true })
    .click();
  await page.getByLabel("Dataset name").fill(`E2E dataset ${stamp}`);
  const cases = Array.from({ length: 10 }, (_, i) => ({
    case_id: `case-${i}`,
    input: `Question ${i}`,
    reference_answer: `Answer ${i}`,
    tags: ["e2e"],
  }));
  await page
    .getByLabel("Dataset content")
    .fill(cases.map((c) => JSON.stringify(c)).join("\n"));
  await page.getByRole("button", { name: "Import & version" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page
    .getByRole("button", { name: new RegExp(`E2E dataset ${stamp}`) })
    .click();
  await expect(page.getByText("case-0", { exact: true })).toBeVisible();
  await page
    .getByRole("button", { name: "Create version", exact: true })
    .click();
  await page.getByLabel("Test cases · JSON array").fill(JSON.stringify(cases));
  await page.getByRole("button", { name: "Save version" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.getByLabel("Dataset version")).toContainText("Version 2");
  await page
    .getByRole("button", { name: "Prompt library", exact: true })
    .click();
  await page.getByRole("button", { name: "New prompt version" }).click();
  await page.getByLabel("Version name").fill(`E2E prompt ${stamp}`);
  await page.getByLabel("Prompt template").fill("Answer this: {input}");
  await page.getByRole("button", { name: "Save prompt version" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);

  for (const [label, model] of [
    ["baseline", "mock-precise"],
    ["candidate", "mock-regressed"],
  ]) {
    await page
      .getByRole("button", { name: "Experiments", exact: true })
      .click();
    await page
      .getByRole("button", { name: "New evaluation", exact: true })
      .click();
    await page.getByLabel("Experiment name").fill(`E2E ${label} ${stamp}`);
    await page
      .getByLabel("Dataset version")
      .selectOption({ label: `E2E dataset ${stamp} · v2 (10 cases)` });
    await page
      .getByLabel("Prompt version", { exact: true })
      .selectOption({ label: `E2E prompt ${stamp}` });
    await page.getByLabel("Model", { exact: true }).selectOption(model);
    await page.getByLabel("Capture response content").check();
    await page.getByRole("button", { name: "Start evaluation" }).click();
    await expect(
      page.getByRole("heading", { name: `E2E ${label} ${stamp}`, exact: true }),
    ).toBeVisible();
    await expect(page.getByText("100% complete", { exact: true })).toBeVisible({
      timeout: 30000,
    });
    await page.getByRole("button", { name: "case-0", exact: true }).click();
    await expect(page.getByText("llm.generate", { exact: true })).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "MODEL RESPONSE", exact: true }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Close dialog" }).click();
  }
  await page.getByRole("button", { name: "Comparisons", exact: true }).click();
  const baseOption = page
    .getByLabel("Baseline run")
    .locator("option")
    .filter({ hasText: `E2E baseline ${stamp}` });
  const candidateOption = page
    .getByLabel("Candidate run")
    .locator("option")
    .filter({ hasText: `E2E candidate ${stamp}` });
  await page
    .getByLabel("Baseline run")
    .selectOption((await baseOption.getAttribute("value")) || "");
  await page
    .getByLabel("Candidate run")
    .selectOption((await candidateOption.getAttribute("value")) || "");
  await page
    .getByRole("button", { name: "Check quality gate", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Release criteria failed" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Case-by-case changes" }),
  ).toBeVisible();
  await page.getByRole("button", { name: /regressed cases/ }).click();
  await expect(page.locator(".comparison-stat.regressed")).toHaveClass(
    /selected/,
  );
});

test("dashboard is usable on a narrow screen", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Evaluation overview" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page.getByRole("button", { name: "Datasets", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Datasets", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
});
