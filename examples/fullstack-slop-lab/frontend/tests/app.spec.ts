import { expect, test, type Page } from "@playwright/test";

function captureRuntimeFailures(page: Page) {
  const failures: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") failures.push(message.text());
  });
  page.on("pageerror", (error) => failures.push(error.message));
  page.on("response", (response) => {
    if (response.status() >= 500) {
      failures.push(`${response.status()} ${response.url()}`);
    }
  });
  return failures;
}

test("project search truthfully reflects and follows the URL", async ({ page }) => {
  const runtimeFailures = captureRuntimeFailures(page);
  await page.goto("/projects");

  const globalSearch = page.locator(".global-search input");
  const projectFilter = page.locator(".toolbar input[type=search]");
  await globalSearch.fill("Website");
  await page.locator(".global-search button").click();

  await expect(page).toHaveURL(/\/projects\?search=Website$/);
  await expect(globalSearch).toHaveValue("Website");
  await expect(projectFilter).toHaveValue("Website");
  await expect(page.getByRole("row", { name: /Website Redesign/ })).toBeVisible();

  await page.goBack();
  await expect(globalSearch).toHaveValue("");
  await expect(projectFilter).toHaveValue("");
  expect(runtimeFailures).toEqual([]);
});

test("create and delete flows use blocking dialogs and persist", async ({ page }) => {
  const runtimeFailures = captureRuntimeFailures(page);
  await page.goto("/projects");

  await page.getByRole("button", { name: "Create project" }).click();
  const createDialog = page.getByRole("dialog", { name: "Create project" });
  await expect(createDialog).toBeVisible();
  await expect
    .poll(() => createDialog.evaluate((dialog) => dialog.matches(":modal")))
    .toBe(true);

  await page.keyboard.press("Escape");
  await expect(createDialog).toBeHidden();

  await page.getByRole("button", { name: "Create project" }).click();
  await createDialog.getByLabel("Project name").fill("Browser contract project");
  await createDialog.getByLabel("Description").fill("Created by Playwright.");
  await createDialog.getByLabel("Budget").fill("4100");
  await createDialog.getByRole("button", { name: "Create project" }).click();

  await expect(page.getByText("Project created.")).toBeVisible();
  await expect(
    page.getByRole("row", { name: /Browser contract project/ }),
  ).toBeVisible();

  await page.getByRole("button", { name: "Delete Browser contract project" }).click();
  const deleteDialog = page.getByRole("dialog", { name: "Delete project?" });
  await expect
    .poll(() => deleteDialog.evaluate((dialog) => dialog.matches(":modal")))
    .toBe(true);
  await deleteDialog.getByRole("button", { name: "Yes, delete it" }).click();
  await expect(
    page.getByRole("row", { name: /Browser contract project/ }),
  ).toHaveCount(0);
  expect(runtimeFailures).toEqual([]);
});

test("malformed backend payloads surface a contract error", async ({ page }) => {
  const runtimeFailures = captureRuntimeFailures(page);
  await page.route("**/api/metrics", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ activeProjects: "not-a-number" }),
    }),
  );

  await page.goto("/");
  await expect(page.getByRole("alert")).toContainText(
    "Response contract mismatch for /api/metrics",
  );
  expect(runtimeFailures).toEqual([]);
});

test("review queue leads to an actionable project and preserves its audit trail", async ({ page }) => {
  const runtimeFailures = captureRuntimeFailures(page);
  await page.goto("/");

  await page.getByRole("link", { name: /Review AI Content Engine/ }).click();
  await expect(page).toHaveURL(/\/projects\/2$/);
  await expect(page.getByRole("heading", { name: "Needs review" })).toBeVisible();
  await expect(page.getByText(/Confirm the next delivery checkpoint with Imani Cole/)).toBeVisible();

  const progress = page.getByLabel("Recorded project progress");
  const nextProgress = Math.min(99, Number(await progress.inputValue()) + 1);
  await progress.fill(String(nextProgress));
  await page.getByRole("button", { name: "Save progress" }).click();

  await expect(page.locator(".toast")).toContainText("Project progress saved");
  await expect(page.getByText("Northstar Operator", { exact: true }).last()).toBeVisible();
  await expect(page.getByText(`Changed project progress to ${nextProgress}%`)).toBeVisible();
  expect(runtimeFailures).toEqual([]);
});

test("project load failure explains recovery and retry succeeds", async ({ page }) => {
  await page.route("**/api/projects/2", (route) => route.abort("failed"));
  await page.goto("/projects/2");

  await expect(page.getByRole("heading", { name: "Project unavailable" })).toBeVisible();
  await expect(page.getByText(/could not load the project record/i)).toBeVisible();
  await expect(page.getByRole("link", { name: "Back to projects" })).toBeVisible();

  await page.unroute("**/api/projects/2");
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(page.getByRole("heading", { name: "AI Content Engine" })).toBeVisible();
});

test("project first-run and filtered-empty states offer distinct next steps", async ({ page }) => {
  await page.route("**/api/projects", (route) =>
    route.fulfill({ contentType: "application/json", body: "[]" }),
  );
  await page.goto("/projects");
  await expect(page.getByRole("heading", { name: "Start your project register" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Create first project" })).toBeVisible();

  await page.unroute("**/api/projects");
  await page.reload();
  await page.getByLabel("Filter projects").fill("no-such-project");
  await expect(page.getByRole("heading", { name: "No projects found" })).toBeVisible();
  await page.getByRole("button", { name: "Clear filters" }).click();
  await expect(page.getByRole("row", { name: /AI Content Engine/ })).toBeVisible();
  await expect(page.getByLabel("Search portfolio")).toBeVisible();
});

test("mobile primary navigation keeps every route reachable", async ({ page }) => {
  const runtimeFailures = captureRuntimeFailures(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");

  const navigationToggle = page.getByText("Navigate workspace", { exact: true });
  const settingsLink = page.getByRole("link", { name: "Settings", exact: true });
  await expect(settingsLink).toBeHidden();
  await navigationToggle.click();
  await expect(settingsLink).toBeVisible();
  await settingsLink.click();

  await expect(page).toHaveURL(/\/settings$/);

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await expect(navigationToggle).toBeHidden();
  await expect(settingsLink).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Fixture provenance", exact: true })
  ).toBeInViewport();
  expect(runtimeFailures).toEqual([]);
});

test("responsive canaries are remediated without hiding their content", async ({ page }) => {
  const runtimeFailures = captureRuntimeFailures(page);
  await page.setViewportSize({ width: 768, height: 1024 });

  await page.goto("/campaigns");
  const campaignBoard = page.locator(".campaign-board");
  await expect
    .poll(() =>
      campaignBoard.evaluate((element) => element.scrollWidth <= element.clientWidth),
    )
    .toBe(true);

  await page.goto("/segments");
  const definition = page.locator(".clipped-definition").first();
  await expect
    .poll(() => definition.evaluate((element) => element.scrollHeight <= element.clientHeight))
    .toBe(true);

  expect(runtimeFailures).toEqual([]);
});

test("support response accelerators are keyboard operable", async ({ page }) => {
  const runtimeFailures = captureRuntimeFailures(page);
  await page.goto("/service-levels");

  const macro = page.getByRole("button", {
    name: /Duplicate contact investigation/,
  });
  await macro.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Duplicate contact investigation" })).toBeVisible();
  await expect(page.getByText(/reconciling identity across your connected sources/i)).toBeVisible();
  expect(runtimeFailures).toEqual([]);
});

test("pipeline detail mutation persists through revenue operations", async ({ page }) => {
  const runtimeFailures = captureRuntimeFailures(page);
  await page.goto("/pipeline");

  const firstDeal = page.getByRole("link", { name: /Acme expansion/i });
  await expect(firstDeal).toBeVisible();
  await firstDeal.click();
  await expect(page).toHaveURL(/\/pipeline\/\d+$/);

  await page.getByLabel("Deal stage").selectOption("proposal");
  await page.getByLabel("Probability").fill("74");
  await page.getByRole("button", { name: "Save deal" }).click();
  await expect(page.getByRole("status")).toContainText("Deal updated");
  expect(runtimeFailures).toEqual([]);
});

test("support case can be inspected and assigned", async ({ page }) => {
  const runtimeFailures = captureRuntimeFailures(page);
  await page.goto("/support");

  await page.getByRole("link", { name: /Export job never finishes/i }).click();
  await expect(page).toHaveURL(/\/support\/\d+$/);
  await expect(page.getByRole("heading", { name: /Export job never finishes/i })).toBeVisible();
  await page.getByLabel("Assignee").selectOption("Mara Voss");
  await page.getByRole("button", { name: "Assign case" }).click();
  await expect(page.getByRole("status")).toContainText("Assigned to Mara Voss");
  expect(runtimeFailures).toEqual([]);
});

test("fulfillment routes expose order lineage and live status", async ({ page }) => {
  const runtimeFailures = captureRuntimeFailures(page);
  await page.goto("/orders");

  await page.getByRole("link", { name: /NF-ORDER-2401/i }).click();
  await expect(page).toHaveURL(/\/orders\/\d+$/);
  await expect(page.getByRole("table", { name: "Order lines" })).toBeVisible();
  await page.getByRole("button", { name: "Advance order" }).click();
  await expect(page.getByRole("status")).toContainText("Order advanced");

  await page.goto("/inventory");
  await expect(page.getByRole("heading", { name: "Inventory" })).toBeVisible();
  await page.goto("/shipments");
  await expect(page.getByRole("heading", { name: "Shipments" })).toBeVisible();
  expect(runtimeFailures).toEqual([]);
});

test("control-plane routes and campaign mutations align with the API", async ({ page }) => {
  const runtimeFailures = captureRuntimeFailures(page);
  for (const path of [
    "/audit-log",
    "/feature-flags",
    "/service-health",
    "/marketplace",
    "/work-queue",
  ]) {
    await page.goto(path);
    await expect(page.locator("main h1")).toBeVisible();
  }

  await page.goto("/campaigns");
  await page.getByRole("button", { name: /Launch enterprise revival/i }).click();
  await expect(page.getByRole("status")).toContainText(/launched/i);
  expect(runtimeFailures).toEqual([]);
});

test("every expanded route renders its primary page shell", async ({ page }) => {
  const runtimeFailures = captureRuntimeFailures(page);
  const routes = [
    "/",
    "/projects",
    "/projects/1",
    "/analytics",
    "/automations",
    "/inbox",
    "/billing",
    "/experiments",
    "/customers",
    "/data-hub",
    "/approvals",
    "/journeys",
    "/pipeline",
    "/pipeline/2",
    "/forecast",
    "/support",
    "/support/1",
    "/service-levels",
    "/catalog",
    "/orders",
    "/orders/1",
    "/inventory",
    "/shipments",
    "/campaigns",
    "/segments",
    "/content-library",
    "/surveys",
    "/audit-log",
    "/feature-flags",
    "/service-health",
    "/marketplace",
    "/work-queue",
    "/team",
    "/settings",
    "/fixture-provenance",
  ];

  for (const route of routes) {
    await test.step(route, async () => {
      await page.goto(route);
      await expect(page.locator("main h1").first()).toBeVisible();
    });
  }

  expect(runtimeFailures).toEqual([]);
});
