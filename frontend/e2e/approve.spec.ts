// Playwright E2E specification for Resolva (FE-05 & FE-06)
// Run with: npx playwright test frontend/e2e/approve.spec.ts
import { test, expect } from '@playwright/test';

test('manager can log in, inspect exception, approve validated proposal, and verify audit trail', async ({ page }) => {
  await page.goto('http://localhost:5173');
  await expect(page.getByText('Resolva')).toBeVisible();

  // Sign in using demo manager preset
  await page.getByText('Priya Menon').click();
  await page.getByRole('button', { name: /Sign In to Resolva/i }).click();

  await expect(page.getByText('Aarav Sharma')).toBeVisible();

  await page.getByRole('button', { name: /Approve Proposal/i }).click();
  await expect(page.getByText(/EXC-101 APPROVED/i)).toBeVisible();

  await page.getByRole('button', { name: /Audit Trail/i }).click();
  await expect(page.getByText('DECISION_APPROVED')).toBeVisible();

  // Verify Sign Out returns to login
  await page.getByRole('button', { name: /Sign Out/i }).click();
  await expect(page.getByRole('button', { name: /Sign In to Resolva/i })).toBeVisible();
});
