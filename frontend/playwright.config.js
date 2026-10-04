const { defineConfig } = require("@playwright/test");
module.exports = defineConfig({
  testDir: "./e2e",
  timeout: 60000,
  workers: 1,
  fullyParallel: false,
  outputDir: process.env.CMS_BROWSER_RESULTS || "test-results",
  reporter: [["list"]],
  use: {
    baseURL: process.env.CMS_BASE_URL || "http://localhost:8080",
    viewport: { width: 390, height: 844 },
    hasTouch: true,
    launchOptions: { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || undefined, args: ["--no-sandbox", "--disable-dev-shm-usage"] },
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
});
