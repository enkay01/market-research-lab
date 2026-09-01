import { expect, test } from "playwright/test";

test("downloads a Security List through the composite dataset request", async ({ page }) => {
  let submittedRequest: unknown;

  await page.route("**/api/health", (route) =>
    route.fulfill({ json: { status: "ok" } }),
  );
  await page.route("**/api/projects", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/datasets", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/security-lists", (route) =>
    route.fulfill({
      json: [
        {
          id: "us-sector-index-etfs",
          name: "US Sector & Index ETFs",
          member_count: 14,
          as_of_date: "2026-08-31",
          source_url: "https://example.com/security-list-source",
        },
      ],
    }),
  );
  await page.route("**/api/datasets/download", async (route) => {
    submittedRequest = route.request().postDataJSON();
    await route.fulfill({
      status: 201,
      json: {
        dataset_version_id: "dataset-1",
        security_list_id: "us-sector-index-etfs",
        parts: [],
      },
    });
  });

  await page.goto("http://127.0.0.1:5173");
  await page.getByRole("button", { name: "Download Provider Data" }).click();
  await page.getByLabel("Security List").selectOption("us-sector-index-etfs");
  await page.getByRole("checkbox", { name: "Tiingo daily bars" }).check();
  await page.getByRole("checkbox", { name: "Massive minute bars" }).check();
  await page.getByRole("checkbox", { name: "SEC EDGAR fundamentals" }).check();
  await page.getByRole("button", { name: "Download & Ingest" }).click();

  await expect.poll(() => submittedRequest).toEqual({
    security_list_id: "us-sector-index-etfs",
    start_date: "2024-01-01",
    end_date: "2024-12-31",
    downloads: [
      { provider: "tiingo", data_types: ["daily_bars"] },
      { provider: "massive", data_types: ["minute_bars"] },
      { provider: "sec_edgar", data_types: ["fundamentals"] },
    ],
  });
});
