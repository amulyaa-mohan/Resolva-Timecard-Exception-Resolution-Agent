"""Regression tests for audit findings A2 and A3 (2026-11-18), on SQLite and PostgreSQL.

A2: drafting a proposal must not hold the write lock while the model runs, and a proposal
drafted on evidence that changed meanwhile must not be stored.
A3: a reused X-Trace-Id must not crash a proposal.
"""

from __future__ import annotations

import pytest

from app.ai.providers import MockProvider
from app.core.contracts import GateStatus
from app.resolution.store import DecisionConflict
from tests.integration.test_resolution_api import auth, env, propose  # noqa: F401 (fixture)


class ModelThatWritesMeanwhile:
    """A model that, while 'thinking', lets another writer act on the database."""

    name = "mock"
    model_id = "audit-writer"

    def __init__(self, during):
        self.during = during
        self.inner = MockProvider()
        self.side_effect_error: Exception | None = None

    def is_reachable(self) -> bool:
        return True

    def complete(self, request):
        try:
            self.during()
        except Exception as exc:  # recorded and asserted by the test
            self.side_effect_error = exc
        return self.inner.complete(request)


def test_a2_other_writers_proceed_while_the_model_runs(env, settings):  # noqa: F811
    client, store, database = env

    def another_manager_writes():
        # Before the fix the proposal held the global write lock here: SQLite raised
        # "database is locked" and PostgreSQL blocked until the model call timed out.
        with store._transaction() as connection:
            connection.execute("SELECT 1").fetchone()

    model = ModelThatWritesMeanwhile(another_manager_writes)
    result = store.propose("X-1", "M-1", provider=model, settings=settings)
    assert model.side_effect_error is None, model.side_effect_error
    assert result.status == GateStatus.ELIGIBLE, result.reasons
    assert database.scalar("SELECT count(*) FROM proposals WHERE exception_id=?", ("X-1",))[0] == 1


def test_a2_proposal_on_changed_evidence_is_not_stored(env, settings):  # noqa: F811
    client, store, database = env

    def evidence_changes_meanwhile():
        with store._transaction() as connection:
            _, revision = store._load(connection, "X-1", "M-1", lock=True)
            store.backend.mark_resolved(connection, "X-1", revision, revision + 1)

    model = ModelThatWritesMeanwhile(evidence_changes_meanwhile)
    with pytest.raises(DecisionConflict, match="evidence changed"):
        store.propose("X-1", "M-1", provider=model, settings=settings)
    assert model.side_effect_error is None, model.side_effect_error
    assert database.scalar("SELECT count(*) FROM proposals WHERE exception_id=?", ("X-1",))[0] == 0


def test_a2_changed_evidence_is_a_409_over_http(env, settings, monkeypatch):  # noqa: F811
    client, store, _ = env
    original = store.propose

    def racing_propose(exception_id, manager_id, *, provider, settings):
        def bump():
            with store._transaction() as connection:
                _, revision = store._load(connection, exception_id, manager_id, lock=True)
                store.backend.mark_resolved(connection, exception_id, revision, revision + 1)

        return original(
            exception_id,
            manager_id,
            provider=ModelThatWritesMeanwhile(bump),
            settings=settings,
        )

    monkeypatch.setattr(store, "propose", racing_propose)
    response = propose(client)
    assert response.status_code == 409
    assert "evidence changed" in response.json()["detail"]


def test_a3_reused_trace_id_does_not_crash(env):  # noqa: F811
    client, _, database = env
    headers = {**auth(), "X-Trace-Id": "sametrace01"}
    first = client.post("/exceptions/X-1/proposal", headers=headers)
    second = client.post("/exceptions/X-1/proposal", headers=headers)
    assert first.status_code == second.status_code == 200, second.text
    count = database.scalar(
        "SELECT count(*) FROM llm_traces WHERE trace_id LIKE ?", ("sametrace01:PRP-%",)
    )[0]
    assert count == 2
    raw = database.scalar(
        "SELECT count(*) FROM llm_raw_outputs WHERE trace_id LIKE ?", ("sametrace01:%",)
    )[0]
    assert raw == 2
