/**
 * Settings persistence management (FE-08)
 *
 * Explicitly manages client-side harness settings and localStorage persistence.
 * Note: Runtime guardrail settings currently persist in local browser storage only.
 * Centralized backend policy/guardrail endpoints are a pending SHARED-01 dependency.
 */

export interface HarnessSettings {
  aiEnabled: boolean;
  confidenceThreshold: number;
  persistToLocalStorage: boolean;
  requireDeterministicValidation: boolean;
}

export const DEFAULT_HARNESS_SETTINGS: HarnessSettings = {
  aiEnabled: true,
  confidenceThreshold: 0.75,
  persistToLocalStorage: true,
  requireDeterministicValidation: true,
};

export const SETTINGS_STORAGE_KEY = 'resolva_harness_settings';

export function loadHarnessSettings(): HarnessSettings {
  try {
    const raw = localStorage.getItem(SETTINGS_STORAGE_KEY);
    if (!raw) return { ...DEFAULT_HARNESS_SETTINGS };
    const parsed = JSON.parse(raw);
    return {
      aiEnabled: typeof parsed.aiEnabled === 'boolean' ? parsed.aiEnabled : DEFAULT_HARNESS_SETTINGS.aiEnabled,
      confidenceThreshold:
        typeof parsed.confidenceThreshold === 'number' &&
        parsed.confidenceThreshold >= 0.5 &&
        parsed.confidenceThreshold <= 0.95
          ? parsed.confidenceThreshold
          : DEFAULT_HARNESS_SETTINGS.confidenceThreshold,
      persistToLocalStorage:
        typeof parsed.persistToLocalStorage === 'boolean'
          ? parsed.persistToLocalStorage
          : DEFAULT_HARNESS_SETTINGS.persistToLocalStorage,
      requireDeterministicValidation:
        typeof parsed.requireDeterministicValidation === 'boolean'
          ? parsed.requireDeterministicValidation
          : DEFAULT_HARNESS_SETTINGS.requireDeterministicValidation,
    };
  } catch {
    return { ...DEFAULT_HARNESS_SETTINGS };
  }
}

export function saveHarnessSettings(settings: HarnessSettings): { ok: boolean; error?: string } {
  try {
    if (settings.persistToLocalStorage) {
      localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(settings));
    } else {
      localStorage.removeItem(SETTINGS_STORAGE_KEY);
    }
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : 'Storage quota exceeded or restricted' };
  }
}
