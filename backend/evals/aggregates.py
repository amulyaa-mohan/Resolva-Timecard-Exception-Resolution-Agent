"""Trusted weekly/quarterly totals for evaluation, and the real validator bound to them.

Track A's `make_validator(load_aggregates)` needs a trusted source of other-day totals. In
production that is the attendance database; here it is each eval case's `AggregateSpec`, keyed by
the case's own exception id (never by anything the model wrote). The loader is called on every
validation, as Track A requires.

Period boundaries come from the policy pack (contract 0.2.0: `week_start`, `quarter_start_month`),
in the employee's local calendar, so the totals always name the week and quarter they cover.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from app.core.contracts import CaseContext, PolicyRules, Weekday
from app.policies.registry import PolicyRegistry, PolicyResolutionError, resolve_policy
from app.rules.engine import RULE_VERSION, AggregateEvidence
from app.rules.validator import make_validator
from evals.schema import EvalCase

NAME = f"track-a {RULE_VERSION} (make_validator + eval totals)"


def week_start(day: date, first: Weekday) -> date:
    return day - timedelta(days=(day.weekday() - first.number) % 7)


def quarter_start(day: date, first_month: int) -> date:
    offset = (day.month - first_month) % 3
    month = day.month - offset
    year = day.year
    if month < 1:
        month += 12
        year -= 1
    return date(year, month, 1)


def build_aggregates(
    case: EvalCase, ctx: CaseContext, rules: PolicyRules
) -> AggregateEvidence | None:
    spec = case.input.aggregates
    if spec is None:
        return None
    return AggregateEvidence(
        work_date_complete=spec.work_date_complete,
        week_other_worked_hours=spec.week_other_worked_hours,
        week_remaining_scheduled_hours=spec.week_remaining_scheduled_hours,
        quarter_other_overtime_hours=spec.quarter_other_overtime_hours,
        week_start=week_start(ctx.work_date, rules.week_start)
        + timedelta(days=spec.week_offset_days),
        quarter_start=quarter_start(ctx.work_date, rules.quarter_start_month),
        as_of=ctx.as_of or datetime.now(UTC),
    )


def real_validator(cases: list[EvalCase], registry: PolicyRegistry):
    """Track A's validator with a loader over the eval cases' trusted totals."""
    by_exception = {f"X-{c.id}": c for c in cases}

    def load(ctx: CaseContext) -> AggregateEvidence | None:
        case = by_exception.get(ctx.exception_id)
        if case is None:
            return None  # unknown case: totals unavailable, never invented
        try:
            policy = resolve_policy(ctx.employee, ctx.work_date, registry)
        except PolicyResolutionError:
            return None
        return build_aggregates(case, ctx, policy.rules)

    return make_validator(load)
