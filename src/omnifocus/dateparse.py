"""Shared human-friendly due/defer date parsing helpers.

The CLI, MCP, and HTTPS API all accept the same compact date inputs:

- ``today``
- ``tomorrow``
- weekday abbreviations like ``mon`` or ``fri``
- ISO ``YYYY-MM-DD``
- shorthand ``MM-DD`` in the current year
"""

from __future__ import annotations

__author__ = "Maciej Szymczak <maciej@szymczak.at>"

import re
from datetime import datetime, timedelta

import click


def parse_due(value: str) -> datetime:
    """Parse a user-facing due/defer date token into a local datetime.

    Args:
        value: Input token such as ``today`` or ``2026-04-06``.

    Returns:
        Parsed datetime with a conventional 19:00 local time for date-only
        inputs.

    Raises:
        click.BadParameter: If ``value`` is not recognised.
    """
    today = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    s = value.strip().lower()

    if s in ("today", "tod"):
        return today.replace(hour=19)
    if s in ("tomorrow", "tom"):
        return today.replace(hour=19) + timedelta(days=1)

    weekdays = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
    if s[:3] in weekdays:
        target_wd = weekdays[s[:3]]
        days_ahead = (target_wd - today.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
        return today.replace(hour=19) + timedelta(days=days_ahead)

    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        try:
            parsed = datetime.fromisoformat(s)
            return parsed.replace(hour=19)
        except ValueError:
            pass

    if re.match(r"^\d{2}-\d{2}$", s):
        try:
            parsed = datetime.fromisoformat(f"{today.year}-{s}")
            return parsed.replace(hour=19)
        except ValueError:
            pass

    raise click.BadParameter(
        f"{value!r} is not a recognised date. "
        "Use YYYY-MM-DD, MM-DD, today, tomorrow, or mon/tue/wed/thu/fri/sat/sun.",
        param_hint="--due",
    )
