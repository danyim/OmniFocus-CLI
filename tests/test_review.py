"""Tests for :mod:`omnifocus.review`."""

from __future__ import annotations

__author__ = "Maciej Szymczak <maciej@szymczak.at>"

from datetime import UTC, datetime

from omnifocus.models import Project
from omnifocus.review import (
    add_review_interval,
    compute_project_review_state,
    mark_project_reviewed,
    parse_review_interval,
)

NOW = datetime(2026, 3, 25, 12, 0, 0, tzinfo=UTC)


def _project() -> Project:
    """Return a stable project fixture."""
    return Project(
        id="p1",
        name="Engineering",
        folder_id=None,
        status="active",
        singleton=False,
        rank=10,
        added=NOW,
        modified=NOW,
        flagged=False,
        due=None,
        start=None,
        note="",
        completed=None,
        last_review=datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC),
        next_review=None,
        review_interval="@1m",
    )


class TestParseReviewInterval:
    def test_parses_supported_token(self) -> None:
        assert parse_review_interval("@4w") == (4, "w")

    def test_rejects_empty_token(self) -> None:
        assert parse_review_interval(None) is None

    def test_rejects_unknown_token(self) -> None:
        assert parse_review_interval("bogus") is None


class TestAddReviewInterval:
    def test_adds_days(self) -> None:
        due_at = add_review_interval(datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC), "@3d")
        assert due_at == datetime(2026, 3, 4, 12, 0, 0, tzinfo=UTC)

    def test_adds_weeks(self) -> None:
        due_at = add_review_interval(datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC), "@2w")
        assert due_at == datetime(2026, 3, 15, 12, 0, 0, tzinfo=UTC)

    def test_adds_months_with_day_clamping(self) -> None:
        due_at = add_review_interval(datetime(2026, 1, 31, 12, 0, 0, tzinfo=UTC), "@1m")
        assert due_at == datetime(2026, 2, 28, 12, 0, 0, tzinfo=UTC)

    def test_adds_years(self) -> None:
        due_at = add_review_interval(datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC), "@1y")
        assert due_at == datetime(2027, 3, 1, 12, 0, 0, tzinfo=UTC)


class TestComputeProjectReviewState:
    def test_uses_explicit_next_review_when_present(self) -> None:
        project = Project(
            id="p1",
            name="Engineering",
            folder_id=None,
            status="active",
            singleton=False,
            rank=10,
            added=NOW,
            modified=NOW,
            flagged=False,
            due=None,
            start=None,
            note="",
            completed=None,
            next_review=datetime(2026, 3, 24, 12, 0, 0, tzinfo=UTC),
        )
        state = compute_project_review_state(project, now=NOW)
        assert state.due is True
        assert state.basis == "next_review"

    def test_uses_interval_when_next_review_missing(self) -> None:
        state = compute_project_review_state(_project(), now=NOW)
        assert state.due is False
        assert state.basis == "interval"
        assert state.due_at == datetime(2026, 4, 1, 12, 0, 0, tzinfo=UTC)

    def test_never_reviewed_interval_project_is_due(self) -> None:
        project = Project(
            id="p1",
            name="Engineering",
            folder_id=None,
            status="active",
            singleton=False,
            rank=10,
            added=NOW,
            modified=NOW,
            flagged=False,
            due=None,
            start=None,
            note="",
            completed=None,
            review_interval="@1w",
        )
        state = compute_project_review_state(project, now=NOW)
        assert state.due is True
        assert state.basis == "interval"

    def test_unknown_schedule_is_not_due(self) -> None:
        project = Project(
            id="p1",
            name="Engineering",
            folder_id=None,
            status="active",
            singleton=False,
            rank=10,
            added=NOW,
            modified=NOW,
            flagged=False,
            due=None,
            start=None,
            note="",
            completed=None,
            review_interval="bogus",
        )
        state = compute_project_review_state(project, now=NOW)
        assert state.due is False
        assert state.basis == "unknown"


class TestMarkProjectReviewed:
    def test_recalculates_next_review_when_interval_parseable(self) -> None:
        updated, recalculated = mark_project_reviewed(_project(), reviewed_at=NOW)
        assert recalculated is True
        assert updated.last_review == NOW
        assert updated.next_review == datetime(2026, 4, 25, 12, 0, 0, tzinfo=UTC)

    def test_keeps_existing_next_review_when_interval_unparseable(self) -> None:
        project = Project(
            id="p1",
            name="Engineering",
            folder_id=None,
            status="active",
            singleton=False,
            rank=10,
            added=NOW,
            modified=NOW,
            flagged=False,
            due=None,
            start=None,
            note="",
            completed=None,
            next_review=datetime(2026, 4, 10, 12, 0, 0, tzinfo=UTC),
            review_interval="bogus",
        )
        updated, recalculated = mark_project_reviewed(project, reviewed_at=NOW)
        assert recalculated is False
        assert updated.last_review == NOW
        assert updated.next_review == datetime(2026, 4, 10, 12, 0, 0, tzinfo=UTC)
