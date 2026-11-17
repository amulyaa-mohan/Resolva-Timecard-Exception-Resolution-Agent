"""Deterministic evidence-sufficiency gate (B-03), checked BEFORE the model is called.

Design doc section 8 lists cases that must always escalate. When the evidence needed to justify a
fix is absent, the model is never asked, so it cannot guess. Found in the live Qwen2.5-7B check:
with no schedule the model invented a clock-out 30 minutes after clock-in, and no rule would have
flagged that shift.

Requirements for other codes depend on detection_details keys that Track A has not agreed yet
(see TRACK_B_INTEGRATION.md); they are added once SHARED-01 fixes those keys.
"""

from __future__ import annotations

from app.core.contracts import CaseContext, ExceptionCode


def missing_evidence(case: CaseContext) -> list[str]:
    """Human-readable list of missing evidence; empty when a proposal may be attempted."""
    if case.code == ExceptionCode.MISSING_PUNCH:
        weekday = case.work_date.weekday()
        same_weekday_history = any(p.ts.date().weekday() == weekday for p in case.punch_history)
        if case.schedule is None and not same_weekday_history:
            return [
                "No scheduled shift for the work date",
                "No punch history for this weekday to infer the missing time",
                "Actual time from the employee or manager",
            ]
    return []
