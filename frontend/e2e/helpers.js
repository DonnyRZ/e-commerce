const { expect } = require("@playwright/test");
async function login(context) {
  const response = await context.request.post("/api/v1/auth/login", { data: {
    email: process.env.CMS_ADMIN_EMAIL || "operator@example.com",
    password: process.env.CMS_ADMIN_PASSWORD || "AdminPass123!",
  } });
  expect(response.ok(), "Isolated CMS operator login").toBeTruthy();
}
module.exports = { login };
