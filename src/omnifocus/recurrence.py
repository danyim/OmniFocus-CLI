"""Map high-level repeat options onto OmniFocus repetition fields.

OmniFocus stores task recurrence as three independent fields that the writer and parser
round-trip verbatim:

- ``repetition-rule``: an iCalendar RRULE string, e.g. ``FREQ=DAILY;INTERVAL=30``.
- ``repetition-method``: ``fixed`` for rule-driven repeats; omitted for a plain calendar repeat.
- ``repetition-schedule-type``: ``start-after-completion`` / ``due-after-completion`` when the next
  occurrence is anchored to the completion date; omitted for a fixed calendar repeat.

This module exposes a small, convenient vocabulary (``repeat_every`` / ``repeat_from``) and also
accepts raw ``repetition_rule`` / ``repetition_method`` for callers that already know the exact
OmniFocus tokens. Clearing an existing repetition is intentionally out of scope.
"""

from __future__ import annotations

__author__ = "Maciej Szymczak <maciej@szymczak.at>"

from dataclasses import dataclass

from omnifocus.errors import OFHTTPError

_UNIT_TO_FREQ = {"d": "DAILY", "w": "WEEKLY", "m": "MONTHLY", "y": "YEARLY"}

# ``repeat_from`` vocabulary -> repetition-schedule-type token (None == fixed calendar repeat).
_SCHEDULE_TYPE = {
    "fixed": None,
    "due": None,
    "defer": None,
    "completion": "due-after-completion",
    "start-after-completion": "start-after-completion",
    "due-after-completion": "due-after-completion",
}


@dataclass(frozen=True)
class RepetitionFields:
    """Resolved OmniFocus repetition fields for a task."""

    repetition_rule: str
    repetition_method: str | None
    repetition_schedule_type: str | None


def _rrule_from_repeat_every(repeat_every: str) -> str:
    """Translate a token like ``30d`` into an iCalendar RRULE string."""
    token = repeat_every.strip().lower()
    unit = token[-1:] if token else ""
    count = token[:-1]
    if unit not in _UNIT_TO_FREQ or not count.isdigit() or int(count) < 1:
        raise OFHTTPError(
            f"Invalid repeat_every: {repeat_every!r} (expected e.g. '30d', '6w', '3m', '1y')",
            status_code=422,
            code="validation_error",
        )
    return f"FREQ={_UNIT_TO_FREQ[unit]};INTERVAL={int(count)}"


def build_repetition(
    *,
    repeat_every: str | None = None,
    repeat_from: str | None = None,
    repetition_rule: str | None = None,
    repetition_method: str | None = None,
) -> RepetitionFields | None:
    """Resolve repetition inputs into concrete OmniFocus fields.

    Returns ``None`` when no recurrence was requested. A raw ``repetition_rule`` takes precedence
    over ``repeat_every``. ``repeat_from`` selects the schedule type; an explicit
    ``repetition_method`` overrides the derived method.
    """
    if repetition_rule:
        rule = repetition_rule
    elif repeat_every:
        rule = _rrule_from_repeat_every(repeat_every)
    else:
        if repeat_from is not None or repetition_method:
            raise OFHTTPError(
                "repeat_from/repetition_method require repeat_every or repetition_rule",
                status_code=422,
                code="validation_error",
            )
        return None

    schedule_key = repeat_from if repeat_from is not None else "fixed"
    if schedule_key not in _SCHEDULE_TYPE:
        allowed = ", ".join(sorted(_SCHEDULE_TYPE))
        raise OFHTTPError(
            f"Invalid repeat_from: {repeat_from!r} (expected one of: {allowed})",
            status_code=422,
            code="validation_error",
        )
    schedule_type = _SCHEDULE_TYPE[schedule_key]
    if repetition_method:
        method: str | None = repetition_method
    else:
        method = "fixed" if schedule_type is not None else None
    return RepetitionFields(
        repetition_rule=rule,
        repetition_method=method,
        repetition_schedule_type=schedule_type,
    )
