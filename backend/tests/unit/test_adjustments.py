"""Step 2: AI proposals for codes fixed by moving a recorded punch to a stated time.

SCHEDULE_DEVIATION, SPREAD_OVER_BREACH and OVERLAPPING_SHIFT. Synthetic data only.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from app.ai.evidence import STATED_TIME_CODES, anchor_times, missing_evidence
from app.ai.pipeline import build_messages, case_facts, generate_proposal
from app.ai.providers import MockProvider
from app.core.config import Settings
from app.core.contracts import (
    DEFAULT_SEVERITY,
    EvidenceKind,
    ExceptionCode,
    GateStatus,
    ProposedAction,
    PunchRecord,
    PunchSource,
    PunchType,
)
from app.retrieval.hybrid import retrieve
from tests.factories import IST, make_case, passing_validator

TOL = timedelta(minutes=5)


def _punch(pid: str, kind: PunchType, hhmm: str) -> PunchRecord:
    h, m = (int(x) for x in hhmm.split(":"))
    return PunchRecord(
        punch_id=pid,
        employee_id="E-001",
        ts=datetime(2026, 11, 12, h, m, tzinfo=IST),
        type=kind,
        source=PunchSource.KIOSK,
    )


def _case(code: ExceptionCode, punches, notes=()):
    base = make_case(notes=notes)
    return base.model_copy(
        update={"code": code, "severity": DEFAULT_SEVERITY[code], "punches": punches}
    )


def _late(notes=("Kiosk was down at the gate. I arrived at 09:05.",)):
    return _case(
        ExceptionCode.SCHEDULE_DEVIATION,
        [_punch("P-1", PunchType.IN, "09:25"), _punch("P-2", PunchType.OUT, "18:00")],
        notes,
    )


def _adjust(pid: str, hhmm: str) -> ProposedAction:
    return ProposedAction(
        type="adjust_punch",
        punch_id=pid,
        new_ts=datetime.fromisoformat(f"2026-11-12T{hhmm}:00+05:30"),
    )


# ------------------------------------------------------------------ pre-model gate


@pytest.mark.parametrize("code", sorted(STATED_TIME_CODES))
def test_no_stated_time_escalates_before_the_model(code, policy, settings):
    case = _case(
        code, [_punch("P-1", PunchType.IN, "09:25"), _punch("P-2", PunchType.OUT, "18:00")]
    )
    gaps = missing_evidence(case, policy)
    assert gaps and "No time stated" in gaps[0]
    provider = MockProvider()
    result = generate_proposal(
        case, policy, provider=provider, validator=passing_validator, settings=settings
    )
    assert result.status == GateStatus.ESCALATED and provider.calls == []


def test_stated_time_too_far_from_any_punch_escalates(policy):
    case = _late(notes=("I was here at 08:30 sharp.",))  # 55 min from 09:25, window 30
    gaps = missing_evidence(case, policy)
    assert gaps and "more than 30 min away" in gaps[0]


def test_stated_time_near_a_punch_passes_the_gate(policy):
    assert missing_evidence(_late(), policy) == []


# ------------------------------------------------------------------ one-sided rounding


def test_stated_clock_in_rounds_only_later():
    case = _late()
    assert anchor_times(case, [_adjust("P-1", "09:05")], TOL)[1] == []
    assert anchor_times(case, [_adjust("P-1", "09:08")], TOL)[1] == []  # later: fine
    _, problems = anchor_times(case, [_adjust("P-1", "09:00")], TOL)  # earlier: adds pay
    assert problems and "no extra paid time" in problems[0]


def test_stated_clock_out_rounds_only_earlier():
    case = _case(
        ExceptionCode.SCHEDULE_DEVIATION,
        [_punch("P-1", PunchType.IN, "09:00"), _punch("P-2", PunchType.OUT, "18:25")],
        ("Queue at the kiosk; I actually left at 18:02.",),
    )
    assert anchor_times(case, [_adjust("P-2", "18:00")], TOL)[1] == []  # earlier: fine
    assert anchor_times(case, [_adjust("P-2", "18:05")], TOL)[1]  # later: adds pay


def test_history_habit_rounds_one_way_for_add_punch():
    base = make_case()
    habit = base.punches[0].model_copy(
        update={
            "punch_id": "H-1",
            "type": PunchType.OUT,
            "ts": base.schedule.end - timedelta(days=7) + timedelta(minutes=20),  # 18:20
        }
    )
    case = base.model_copy(update={"punch_history": [habit]})

    def add(hhmm):
        return ProposedAction.model_validate_json(
            f'{{"type":"add_punch","punch_type":"out","new_ts":"2026-11-12T{hhmm}:00+05:30"}}'
        )

    anchored, problems = anchor_times(case, [add("18:17")], TOL)
    assert not problems and anchored[0].evidence_ref.kind == EvidenceKind.HISTORY_PUNCH
    assert anchor_times(case, [add("18:23")], TOL)[1]  # later than the habit: adds pay


def test_schedule_anchor_stays_two_sided():
    case = make_case()
    for hhmm in ("17:57", "18:03"):
        action = ProposedAction.model_validate_json(
            f'{{"type":"add_punch","punch_type":"out","new_ts":"2026-11-12T{hhmm}:00+05:30"}}'
        )
        assert anchor_times(case, [action], TOL)[1] == []


# ------------------------------------------------------------------ facts and prompt


def test_facts_explain_a_late_arrival(policy):
    facts = case_facts(_late(), policy)
    assert "Times stated in employee notes (claims, not proof): 09:05 (note N-0)" in facts
    assert "First clock-in P-1 is 25 min after the scheduled start (tolerance 7 min)" in facts
    assert "Allowed fix: adjust_punch" in facts and "Inference window" not in facts


def test_facts_explain_spread_and_overlap(policy):
    spread = _case(
        ExceptionCode.SPREAD_OVER_BREACH,
        [_punch("P-1", PunchType.IN, "07:00"), _punch("P-2", PunchType.OUT, "19:20")],
        ("I left at 19:00.",),
    )
    assert "Spread from first clock-in P-1 to last clock-out P-2: 12 h 20 min (limit 12 h)" in (
        case_facts(spread, policy)
    )
    overlap = _case(
        ExceptionCode.OVERLAPPING_SHIFT,
        [
            _punch("P-1", PunchType.IN, "09:00"),
            _punch("P-2", PunchType.OUT, "13:20"),
            _punch("P-3", PunchType.IN, "13:00"),
            _punch("P-4", PunchType.OUT, "18:00"),
        ],
        ("I left at 12:55.",),
    )
    assert "Session P-1-P-2 overlaps session P-3-P-4 by 20 min" in case_facts(overlap, policy)


def test_missing_punch_facts_are_unchanged(policy):
    facts = case_facts(make_case(), policy)
    assert "Inference window: within 30 minutes" in facts and "Allowed fix" not in facts


def test_prompt_v3_is_selectable_and_states_the_adjustment_rule(policy):
    settings = Settings(prompt_version="propose_v3")
    case = _late()
    retrieved = retrieve(case, policy, top_k=4).clauses
    system, user = build_messages(case, retrieved, settings.prompts_dir, "propose_v3", policy)
    assert "For adjust_punch, set punch_id" in system.content
    assert "<facts>" in user.content and "Allowed fix" in user.content


# ------------------------------------------------------------------ end to end (mock)


def test_mock_adjusts_the_late_arrival_to_the_stated_time(policy, settings):
    result = generate_proposal(
        _late(), policy, provider=MockProvider(), validator=passing_validator, settings=settings
    )
    assert result.status == GateStatus.ELIGIBLE, result.reasons
    action = result.proposal.actions[0]
    assert action.type == "adjust_punch" and action.punch_id == "P-1"
    assert action.new_ts.astimezone(IST).strftime("%H:%M") == "09:05"
    assert action.evidence_ref.kind == EvidenceKind.NOTE


def test_model_moving_a_late_arrival_to_the_schedule_is_blocked(policy, settings):
    body = {
        "exception_id": "X-1",
        "decision": "propose",
        "actions": [
            {"type": "adjust_punch", "punch_id": "P-1", "new_ts": "2026-11-12T09:00:00+05:30"}
        ],
        "rationale": "Align with the schedule.",
        "citations": [
            {
                "chunk_id": "IN-KA@2025.1#KA-9",
                "quote": "A clock-in more than 7 minutes after the scheduled start",
            }
        ],
        "confidence": 0.95,
        "missing_information": [],
    }
    result = generate_proposal(
        _late(),
        policy,
        provider=MockProvider(script=[json.dumps(body)]),
        validator=passing_validator,
        settings=settings,
    )
    assert result.status == GateStatus.BLOCKED
    assert any("not a time the employee stated" in r for r in result.reasons)


# ------------------------------------------------------------------ citation id normalisation


def _overlap_body(chunk_id: str) -> str:
    return json.dumps(
        {
            "exception_id": "X-1",
            "decision": "propose",
            "actions": [
                {"type": "adjust_punch", "punch_id": "P-2", "new_ts": "2026-11-12T12:55:00+05:30"}
            ],
            "rationale": "Employee states 12:55.",
            "citations": [
                {
                    "chunk_id": chunk_id,
                    "quote": "Worked periods for the same employee must not overlap in time.",
                }
            ],
            "confidence": 0.9,
            "missing_information": [],
        }
    )


def _overlap():
    return _case(
        ExceptionCode.OVERLAPPING_SHIFT,
        [
            _punch("P-1", PunchType.IN, "09:00"),
            _punch("P-2", PunchType.OUT, "13:20"),
            _punch("P-3", PunchType.IN, "13:00"),
            _punch("P-4", PunchType.OUT, "18:00"),
        ],
        ("I clocked out late for lunch; I actually left at 12:55.",),
    )


def _run_overlap(policy, settings, chunk_id):
    return generate_proposal(
        _overlap(),
        policy,
        provider=MockProvider(script=[_overlap_body(chunk_id)]),
        validator=passing_validator,
        settings=settings,
    )


def test_mangled_active_clause_id_is_normalised_and_traced(policy, settings):
    result = _run_overlap(policy, settings, "IN-KA@2025.1#KA-2025.1#KA-11")  # seen live
    assert result.status == GateStatus.ELIGIBLE, result.reasons
    assert result.proposal.citations[0].chunk_id == "IN-KA@2025.1#KA-11"
    check = next(g for g in result.gate_checks if g.name == "citation_ids_normalised")
    assert "KA-2025.1#KA-11 -> IN-KA@2025.1#KA-11" in check.detail


@pytest.mark.parametrize(
    "chunk_id",
    [
        "IN-KA@2025.2-proposed#KA-11",  # proposed version: never in force
        "US-FED@2025.1#KA-11",  # another pack
        "IN-KA@2025.1#KA-99",  # clause that does not exist
        "IN-KA@2025.1#KA-1",  # real clause, but not retrieved for this case
    ],
)
def test_other_unretrieved_citations_are_still_blocked(policy, settings, chunk_id):
    result = _run_overlap(policy, settings, chunk_id)
    assert result.status == GateStatus.BLOCKED
    assert any("not in the retrieved policy evidence" in r for r in result.reasons)


# ------------------------------------------------------------------ UTC storage (live demo finding)


def test_case_json_shows_local_times_when_storage_is_utc(policy, settings):
    from datetime import UTC

    case = _late()
    utc = case.model_copy(
        update={
            "punches": [p.model_copy(update={"ts": p.ts.astimezone(UTC)}) for p in case.punches],
            "schedule": case.schedule.model_copy(
                update={
                    "start": case.schedule.start.astimezone(UTC),
                    "end": case.schedule.end.astimezone(UTC),
                }
            ),
        }
    )
    retrieved = retrieve(utc, policy, top_k=4).clauses
    user = build_messages(utc, retrieved, settings.prompts_dir, "propose_v3", policy)[1].content
    case_json = user.split("<case_json>")[1].split("</case_json>")[0]
    assert "+05:30" in case_json and "+00:00" not in case_json and 'Z"' not in case_json
    assert "2026-11-12T09:25:00+05:30" in case_json


def test_utc_stored_case_end_to_end_with_mock(policy, settings):
    from datetime import UTC

    case = _late()
    utc = case.model_copy(
        update={
            "punches": [p.model_copy(update={"ts": p.ts.astimezone(UTC)}) for p in case.punches],
            "schedule": case.schedule.model_copy(
                update={
                    "start": case.schedule.start.astimezone(UTC),
                    "end": case.schedule.end.astimezone(UTC),
                }
            ),
        }
    )
    result = generate_proposal(
        utc, policy, provider=MockProvider(), validator=passing_validator, settings=settings
    )
    assert result.status == GateStatus.ELIGIBLE, result.reasons
    assert result.proposal.actions[0].new_ts.astimezone(IST).strftime("%H:%M") == "09:05"


def test_stated_times_that_equal_recorded_punches_escalate(policy):
    # Live demo: a double tap at 09:00 and 10:00 with the note "my real shift was 9:00 to
    # 6:00 pm". Both stated times equal recorded punches, so neither describes an error.
    case = _case(
        ExceptionCode.OVERLAPPING_SHIFT,
        [
            _punch("P-1", PunchType.IN, "09:00"),
            _punch("P-2", PunchType.IN, "10:00"),
            _punch("P-3", PunchType.OUT, "17:00"),
            _punch("P-4", PunchType.OUT, "18:00"),
        ],
        ("I tapped in twice by mistake. My real shift was 9:00 to 6:00 pm.",),
    )
    gaps = missing_evidence(case, policy)
    assert gaps and "do not correct any recorded punch" in gaps[0]
