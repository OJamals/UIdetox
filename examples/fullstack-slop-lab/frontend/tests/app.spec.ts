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

test("mobile primary navigation keeps every route reachable", async ({ page }) => {
  const runtimeFailures = captureRuntimeFailures(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");

  const settingsLink = page.getByRole("link", { name: "Settings", exact: true });
  await settingsLink.scrollIntoViewIfNeeded();
  await expect(settingsLink).toBeVisible();
  await settingsLink.click();

  await expect(page).toHaveURL(/\/settings$/);
  expect(runtimeFailures).toEqual([]);
});
