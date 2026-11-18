// Playwright E2E for the real backend flow (FE-05). Not run in CI: Playwright is not a dependency yet.
//
// Prerequisites (see backend/docs/ATTENDANCE_API.md and backend/database/docs/seed_data_guide.md):
//   1. PostgreSQL migrated and seeded:  backend/scripts/seed_demo_week.py "$DSN"
//   2. Backend running with ATTENDANCE_ENABLED=true, ATTENDANCE_DATABASE_URL and LLM_PROVIDER=mock
//   3. Frontend dev server pointed at it:  VITE_API_TARGET=http://127.0.0.1:8001 npm run dev
//   4. MANAGER_TOKEN set to the access_token in backend/local/manager-token.json
import { test, expect } from '@playwright/test';

const TOKEN = process.env.MANAGER_TOKEN ?? '';

test('a manager signs in, drafts, approves, and the server records it', async ({ page }) => {
  test.skip(!TOKEN, 'set MANAGER_TOKEN to run against the seeded backend');
  await page.goto('http://localhost:5173');

  // A wrong token must be refused by the server, not accepted.
  await page.getByPlaceholder('name@company.corp').fill('priya.menon@resolva.corp');
  await page.getByPlaceholder('Paste the manager access token').fill('not-a-real-token');
  await page.getByRole('button', { name: /Sign In/i }).click();
  await expect(page.getByText(/session is not valid/i)).toBeVisible();

  await page.getByPlaceholder('Paste the manager access token').fill(TOKEN);
  await page.getByRole('button', { name: /Sign In/i }).click();
  await expect(page.getByText('LIVE BACKEND')).toBeVisible();

  await page.getByText('Missing punch').first().click();
  await page.getByRole('button', { name: /Draft with AI/i }).click();
  await expect(page.getByText(/6\/6 Passed/i)).toBeVisible();

  await page.getByRole('button', { name: /Approve Proposal/i }).click();
  await expect(page.getByText(/RESOLVED — recorded by the server/i)).toBeVisible();
});
