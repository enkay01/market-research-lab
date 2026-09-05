import { expect, test } from "playwright/test";

test("downloads a Security List through the asynchronous download workflow with backgrounding and reattachment", async ({ page }) => {
  let submittedRequest: unknown;

  await page.route("**/api/health", (route) =>
    route.fulfill({ json: { status: "ok" } }),
  );
  await page.route("**/api/projects", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/datasets", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/downloads/latest", (route) =>
    route.fulfill({ status: 404, json: { code: "download_not_found", message: "Not found" } }),
  );
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

  let pollCount = 0;
  await page.route("**/api/downloads", async (route) => {
    submittedRequest = route.request().postDataJSON();
    await route.fulfill({
      status: 202,
      json: {
        download_id: "dl-test-1",
        status_url: "/api/downloads/dl-test-1",
        snapshot: {
          download_id: "dl-test-1",
          state: "running",
          phase: "FETCHING",
          started_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          security_list_id: "us-sector-index-etfs",
          total_logical_units: 3,
          completed_logical_units: 1,
          total_requests: 3,
          completed_requests: 1,
          active_provider: "tiingo",
          active_operation: "Downloading daily bars",
          rate_limit_wait_seconds: 0,
          recent_events: [
            {
              timestamp: new Date().toISOString(),
              phase: "FETCHING",
              message: "Fetching tiingo daily bars",
            },
          ],
        },
      },
    });
  });

  await page.route("**/api/downloads/dl-test-1", async (route) => {
    pollCount += 1;
    const isDone = pollCount >= 3;
    await route.fulfill({
      status: 200,
      json: {
        download_id: "dl-test-1",
        state: isDone ? "succeeded" : "running",
        phase: isDone ? "COMPLETE" : "FETCHING",
        started_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        dataset_version_id: isDone ? "dataset-version-123" : null,
        security_list_id: "us-sector-index-etfs",
        total_logical_units: 3,
        completed_logical_units: isDone ? 3 : 2,
        total_requests: 3,
        completed_requests: isDone ? 3 : 2,
        active_provider: "tiingo",
        active_operation: isDone ? "Complete" : "Downloading daily bars",
        rate_limit_wait_seconds: 0,
        recent_events: [
          {
            timestamp: new Date().toISOString(),
            phase: isDone ? "COMPLETE" : "FETCHING",
            message: isDone ? "Download complete" : "Fetching tiingo daily bars",
          },
        ],
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

  // Verify that the dialog shows the running task
  await expect(page.getByText("Download in Progress")).toBeVisible();
  await expect(page.getByText("Work Units Completed")).toBeVisible();

  // Background the dialog and verify banner
  await page.getByRole("button", { name: "Keep in Background" }).click();
  await expect(page.getByText("Download in Progress")).not.toBeVisible();
  await expect(page.getByText(/Downloading us-sector-index-etfs:/)).toBeVisible();

  // Reopen via banner
  await page.getByRole("button", { name: "Open Progress Dialog" }).click();
  await expect(page.getByText("Download in Progress")).toBeVisible();
});

test("page reload reattaches to active download via localStorage", async ({ page }) => {
  await page.route("**/api/health", (route) => route.fulfill({ json: { status: "ok" } }));
  await page.route("**/api/projects", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/datasets", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/downloads/latest", (route) =>
    route.fulfill({ status: 404, json: { code: "download_not_found", message: "Not found" } }),
  );
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

  await page.route("**/api/downloads/dl-reattach-1", async (route) => {
    await route.fulfill({
      status: 200,
      json: {
        download_id: "dl-reattach-1",
        state: "running",
        phase: "FETCHING",
        started_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        dataset_version_id: null,
        security_list_id: "us-sector-index-etfs",
        total_logical_units: 4,
        completed_logical_units: 2,
        total_requests: 4,
        completed_requests: 2,
        active_provider: "massive",
        active_operation: "Fetching minute bars",
        rate_limit_wait_seconds: 1.5,
        recent_events: [
          {
            timestamp: new Date().toISOString(),
            phase: "FETCHING",
            message: "Fetching massive minute bars",
          },
        ],
      },
    });
  });

  await page.goto("http://127.0.0.1:5173");
  await page.evaluate(() => {
    localStorage.setItem("active_download_id", "dl-reattach-1");
  });

  await page.reload();

  // Banner should appear automatically on mount
  await expect(page.getByText(/Downloading us-sector-index-etfs:/)).toBeVisible();
  await expect(page.getByRole("button", { name: "View Download Progress" })).toBeVisible();

  await page.getByRole("button", { name: "View Download Progress" }).click();
  await expect(page.getByText("Download in Progress")).toBeVisible();
  await expect(page.getByText("Active Provider")).toBeVisible();
  await expect(page.getByText("massive", { exact: true })).toBeVisible();
});

test("cancelling active download issues cancellation request to backend", async ({ page }) => {
  let cancelCalled = false;

  await page.route("**/api/health", (route) => route.fulfill({ json: { status: "ok" } }));
  await page.route("**/api/projects", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/datasets", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/downloads/latest", (route) =>
    route.fulfill({ status: 404, json: { code: "download_not_found", message: "Not found" } }),
  );
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

  await page.route("**/api/downloads/dl-cancel-1", async (route) => {
    await route.fulfill({
      status: 200,
      json: {
        download_id: "dl-cancel-1",
        state: "running",
        phase: "FETCHING",
        started_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        dataset_version_id: null,
        security_list_id: "us-sector-index-etfs",
        total_logical_units: 5,
        completed_logical_units: 1,
        total_requests: 5,
        completed_requests: 1,
        active_provider: "tiingo",
        active_operation: "Fetching bars",
        rate_limit_wait_seconds: 0,
        recent_events: [],
      },
    });
  });

  await page.route("**/api/downloads/dl-cancel-1/cancel", async (route) => {
    cancelCalled = true;
    await route.fulfill({
      status: 200,
      json: {
        download_id: "dl-cancel-1",
        state: "cancelled",
        phase: "COMPLETE",
        started_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        dataset_version_id: null,
        security_list_id: "us-sector-index-etfs",
        total_logical_units: 5,
        completed_logical_units: 1,
        total_requests: 5,
        completed_requests: 1,
        active_provider: "tiingo",
        active_operation: "Cancelled",
        rate_limit_wait_seconds: 0,
        recent_events: [],
      },
    });
  });

  await page.goto("http://127.0.0.1:5173");
  await page.evaluate(() => {
    localStorage.setItem("active_download_id", "dl-cancel-1");
  });
  await page.reload();

  await page.getByRole("button", { name: "View Download Progress" }).click();
  await expect(page.getByText("Download in Progress")).toBeVisible();

  // Click Cancel Download
  await page.getByRole("button", { name: "Cancel Download" }).click();
  await expect.poll(() => cancelCalled).toBe(true);
});
