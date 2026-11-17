// Playwright E2E specification for Resolva (FE-05)
// Run with: npx playwright test frontend/e2e/approve.spec.ts
import { test, expect } from '@playwright/test';

test('manager can inspect exception, approve validated proposal, and verify audit trail', async ({ page }) => {
  await page.goto('http://localhost:5173');
  await expect(page.getByText('Resolva')).toBeVisible();
  await expect(page.getByText('Aarav Sharma')).toBeVisible();

  await page.getByRole('button', { name: /Approve Proposal/i }).click();
  await expect(page.getByText(/EXC-101 APPROVED/i)).toBeVisible();

  await page.getByRole('button', { name: /Audit Trail/i }).click();
  await expect(page.getByText('DECISION_APPROVED')).toBeVisible();
});
