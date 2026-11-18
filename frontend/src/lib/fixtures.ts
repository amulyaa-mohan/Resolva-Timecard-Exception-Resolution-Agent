import { PolicyPack } from '../types/contracts';


export const INITIAL_POLICY_PACKS: PolicyPack[] = [
  {
    id: 'IN-KA',
    version: '2025.1',
    jurisdiction: 'Karnataka Shops & Commercial Establishments Act (Synthetic Demo)',
    daily_regular_hours: 9,
    weekly_regular_hours: 48,
    overtime_rate: 2.0,
    quarterly_ot_cap: 50,
    rest_after_hours: 5,
    rest_minutes: 60,
    max_spread_hours: 12,
    late_tolerance_min: 7,
  },
  {
    id: 'IN-KA',
    version: '2025.2-proposed',
    jurisdiction: 'Karnataka S&E Proposed Amendment (Synthetic Demo)',
    daily_regular_hours: 12,
    weekly_regular_hours: 48,
    overtime_rate: 2.0,
    quarterly_ot_cap: 144,
    rest_after_hours: 5,
    rest_minutes: 60,
    max_spread_hours: 13,
    late_tolerance_min: 7,
  },
  {
    id: 'US-FED+CA',
    version: '2025.1',
    jurisdiction: 'US Federal + California Meal/Daily OT Overlay (Synthetic Demo)',
    daily_regular_hours: 8,
    weekly_regular_hours: 40,
    overtime_rate: 1.5,
    quarterly_ot_cap: null,
    rest_after_hours: 5,
    rest_minutes: 30,
    max_spread_hours: null,
    late_tolerance_min: 7,
  },
];
