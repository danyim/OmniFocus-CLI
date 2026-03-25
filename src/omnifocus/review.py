"""Helpers for OmniFocus project review metadata.

This module centralises parsing and scheduling logic for OmniFocus project
review fields so that parser, store, and MCP surfaces stay consistent.
"""

from __future__ import annotations

__author__ = "Maciej Szymczak <maciej@szymczak.at>"

import calendar
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from omnifocus.models import Project

_REVIEW_INTERVAL_RE = re.compile(r"^(?:[~@])?(?P<count>\d+)(?P<unit>[dwmy])$")


@dataclass(frozen=True)
class ProjectReviewState:
    """Computed review state for a project.

    Attributes:
        due: Whether the project currently requires review.
        basis: Scheduling basis: ``"next_review"``, ``"interval"``, or ``"unknown"``.
        due_at: Effective due timestamp used for sorting, or ``None``.
    """

    due: bool
    basis: str
    due_at: datetime | None


def parse_review_interval(review_interval: str | None) -> tuple[int, str] | None:
    """Parse an OmniFocus review interval token.

    Supported forms are ``[~@]?N[dwmy]``, for example ``@1w`` or ``~4w``.
    Prefixes are preserved semantically by OmniFocus but ignored for scheduling
    here because the current MCP flow only needs a coarse next-review timestamp.
    """

    if not review_interval:
        return None
    match = _REVIEW_INTERVAL_RE.fullmatch(review_interval)
    if match is None:
        return None
    return int(match.group("count")), match.group("unit")


def add_review_interval(base: datetime, review_interval: str | None) -> datetime | None:
    """Return ``base`` shifted forward by the OmniFocus review interval."""

    parsed = parse_review_interval(review_interval)
    if parsed is None:
        return None
    count, unit = parsed
    if unit == "d":
        return base + timedelta(days=count)
    if unit == "w":
        return base + timedelta(weeks=count)
    if unit == "m":
        return _add_months(base, count)
    return _add_months(base, count * 12)


def compute_project_review_state(
    project: Project,
    *,
    now: datetime | None = None,
) -> ProjectReviewState:
    """Compute whether a project is due for review and why."""

    current = now or datetime.now(UTC)
    if project.next_review is not None:
        return ProjectReviewState(
            due=project.next_review <= current,
            basis="next_review",
            due_at=project.next_review,
        )

    if project.last_review is None and parse_review_interval(project.review_interval) is not None:
        return ProjectReviewState(due=True, basis="interval", due_at=None)

    due_at = (
        add_review_interval(project.last_review, project.review_interval)
        if project.last_review is not None
        else None
    )
    if due_at is not None:
        return ProjectReviewState(
            due=due_at <= current,
            basis="interval",
            due_at=due_at,
        )

    return ProjectReviewState(due=False, basis="unknown", due_at=None)


def mark_project_reviewed(
    project: Project,
    *,
    reviewed_at: datetime | None = None,
) -> tuple[Project, bool]:
    """Return a copy of ``project`` stamped as reviewed.

    The returned boolean indicates whether ``next_review`` was recalculated from
    ``review_interval``.
    """

    stamp = reviewed_at or datetime.now(UTC)
    next_review = add_review_interval(stamp, project.review_interval)
    recalculated = next_review is not None
    return (
        Project(
            id=project.id,
            name=project.name,
            folder_id=project.folder_id,
            status=project.status,
            singleton=project.singleton,
            rank=project.rank,
            added=project.added,
            modified=stamp,
            flagged=project.flagged,
            due=project.due,
            start=project.start,
            note=project.note,
            completed=project.completed,
            last_review=stamp,
            next_review=next_review if recalculated else project.next_review,
            review_interval=project.review_interval,
            tag_ids=project.tag_ids,
            repetition_rule=project.repetition_rule,
            repetition_method=project.repetition_method,
            repetition_schedule_type=project.repetition_schedule_type,
            repetition_anchor_date=project.repetition_anchor_date,
            catch_up_automatically=project.catch_up_automatically,
            next_clone_identifier=project.next_clone_identifier,
            due_date_alarm_policy=project.due_date_alarm_policy,
            defer_date_alarm_policy=project.defer_date_alarm_policy,
            latest_time_to_start_alarm_policy=project.latest_time_to_start_alarm_policy,
            planned_date_alarm_policy=project.planned_date_alarm_policy,
        ),
        recalculated,
    )


def _add_months(base: datetime, months: int) -> datetime:
    """Return ``base`` shifted forward by calendar months."""

    month_index = (base.month - 1) + months
    year = base.year + (month_index // 12)
    month = (month_index % 12) + 1
    day = min(base.day, calendar.monthrange(year, month)[1])
    return base.replace(year=year, month=month, day=day)
