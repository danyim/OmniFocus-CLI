"""OmniFocus sync protocol helpers.

Parses the WebDAV bundle listing into baseline ZIPs, delta ZIPs, and client
state files. Real OmniFocus 4 bundles include:

- one baseline ZIP: ``00000000000000=<snapshot_id>+<tail_id>.zip``
- zero or more delta ZIPs:
  ``<YYYYMMDDHHMMSS>=<parent_tail_1>+...+<parent_tail_n>+<new_tail>.zip``
- zero or more client state files: ``<YYYYMMDDHHMMSS>=<client_id>.client``

The delta naming scheme is a small DAG, not a single-parent chain:
all identifiers except the last are accepted parent tails merged by that
transaction and the last identifier is the new tail it produces.
"""

from __future__ import annotations

__author__ = "Maciej Szymczak <maciej@szymczak.at>"

from dataclasses import dataclass
from datetime import UTC, datetime

from omnifocus.errors import OFBundleNotFound

_BASELINE_PREFIX = "00000000000000="


@dataclass(frozen=True)
class BaselineRef:
    """Parsed metadata for the baseline ZIP."""

    filename: str
    snapshot_id: str
    tail_id: str | None


@dataclass(frozen=True)
class DeltaRef:
    """Parsed metadata for a delta ZIP."""

    filename: str
    timestamp: datetime
    tail_id: str
    parent_tail_ids: tuple[str, ...]


@dataclass(frozen=True)
class ClientStateRef:
    """Parsed metadata for a ``.client`` state file."""

    filename: str
    timestamp: datetime
    client_id: str


@dataclass(frozen=True)
class TransactionRef:
    """Backward-compatible alias for parsed delta metadata."""

    filename: str
    client_id: str
    parent_id: str


@dataclass(frozen=True)
class BundleState:
    """Parsed view of the remote OmniFocus bundle listing."""

    baseline: BaselineRef
    deltas: tuple[DeltaRef, ...]
    clients: tuple[ClientStateRef, ...]
    capabilities: tuple[str, ...]
    other_entries: tuple[str, ...]

    @property
    def current_tail_id(self) -> str | None:
        """Return the bundle tail identifier implied by the baseline."""
        return self.baseline.tail_id


def _parse_compact_timestamp(value: str) -> datetime | None:
    """Parse ``YYYYMMDDHHMMSS`` to a UTC datetime."""
    try:
        return datetime.strptime(value, "%Y%m%d%H%M%S").replace(tzinfo=UTC)
    except ValueError:
        return None


def is_baseline(filename: str) -> bool:
    """Return ``True`` if *filename* is the baseline ZIP."""
    return filename.startswith(_BASELINE_PREFIX)


def client_id_from_filename(filename: str) -> str | None:
    """Extract the identifier stored after ``=`` and before ``+``.

    For baseline ZIPs this is the snapshot identifier.
    For delta ZIPs this is the first parent tail identifier.
    """
    stem = filename.removesuffix(".zip")
    if "=" not in stem:
        return None
    after_eq = stem.split("=", 1)[1]
    if "+" in after_eq:
        return after_eq.split("+", 1)[0] or None
    return after_eq or None


def parent_id_from_filename(filename: str) -> str | None:
    """Extract the identifier stored after ``+`` in a baseline ZIP filename."""
    stem = filename.removesuffix(".zip")
    if "=" not in stem:
        return None
    after_eq = stem.split("=", 1)[1]
    if "+" not in after_eq:
        return None
    parent_id = after_eq.split("+", 1)[1]
    return parent_id or None


def delta_tail_ids_from_filename(filename: str) -> tuple[str, tuple[str, ...]] | None:
    """Return ``(new_tail_id, parent_tail_ids)`` for a delta ZIP filename."""
    stem = filename.removesuffix(".zip")
    if is_baseline(filename) or not filename.endswith(".zip") or "=" not in stem:
        return None
    after_eq = stem.split("=", 1)[1]
    parts = tuple(part for part in after_eq.split("+") if part)
    if len(parts) < 2:
        return None
    return parts[-1], parts[:-1]


def parse_baseline_filename(filename: str) -> BaselineRef | None:
    """Parse a baseline ZIP filename."""
    if not is_baseline(filename) or not filename.endswith(".zip"):
        return None
    snapshot_id = client_id_from_filename(filename)
    tail_id = parent_id_from_filename(filename)
    if snapshot_id is None:
        return None
    return BaselineRef(filename=filename, snapshot_id=snapshot_id, tail_id=tail_id)


def parse_delta_filename(filename: str) -> DeltaRef | None:
    """Parse a delta ZIP filename."""
    if is_baseline(filename) or not filename.endswith(".zip") or "=" not in filename:
        return None
    timestamp_raw = filename.split("=", 1)[0]
    timestamp = _parse_compact_timestamp(timestamp_raw)
    delta_tail_ids = delta_tail_ids_from_filename(filename)
    if timestamp is None or delta_tail_ids is None:
        return None
    tail_id, parent_tail_ids = delta_tail_ids
    return DeltaRef(
        filename=filename,
        timestamp=timestamp,
        tail_id=tail_id,
        parent_tail_ids=parent_tail_ids,
    )


def parse_client_state_filename(filename: str) -> ClientStateRef | None:
    """Parse a ``.client`` filename."""
    if not filename.endswith(".client") or "=" not in filename:
        return None
    timestamp_raw, client_part = filename.split("=", 1)
    timestamp = _parse_compact_timestamp(timestamp_raw)
    client_id = client_part.removesuffix(".client")
    if timestamp is None or not client_id:
        return None
    return ClientStateRef(filename=filename, timestamp=timestamp, client_id=client_id)


def parse_transaction_filename(filename: str) -> TransactionRef | None:
    """Parse a delta ZIP filename into its id pair."""
    delta = parse_delta_filename(filename)
    if delta is None:
        return None
    return TransactionRef(
        filename=delta.filename,
        client_id=delta.tail_id,
        parent_id="+".join(delta.parent_tail_ids),
    )


def latest_transaction_ref(filenames: list[str]) -> TransactionRef | None:
    """Return metadata for the latest delta ZIP in the bundle listing."""
    state = build_bundle_state(filenames)
    if not state.deltas:
        return None
    latest = state.deltas[-1]
    return TransactionRef(
        filename=latest.filename,
        client_id=latest.tail_id,
        parent_id="+".join(latest.parent_tail_ids),
    )


def classify_bundle_files(filenames: list[str]) -> tuple[str, list[str]]:
    """Separate the baseline ZIP from delta ZIPs.

    Non-ZIP files are ignored.
    """
    state = build_bundle_state(filenames)
    return state.baseline.filename, [delta.filename for delta in state.deltas]


def build_bundle_state(filenames: list[str]) -> BundleState:
    """Parse a full WebDAV bundle listing into a structured state."""
    baseline: BaselineRef | None = None
    deltas: list[DeltaRef] = []
    clients: list[ClientStateRef] = []
    capabilities: list[str] = []
    other_entries: list[str] = []

    for name in sorted(filenames):
        parsed_baseline = parse_baseline_filename(name)
        if parsed_baseline is not None:
            baseline = parsed_baseline
            continue

        parsed_delta = parse_delta_filename(name)
        if parsed_delta is not None:
            deltas.append(parsed_delta)
            continue

        parsed_client = parse_client_state_filename(name)
        if parsed_client is not None:
            clients.append(parsed_client)
            continue

        if name.endswith(".capability"):
            capabilities.append(name.removesuffix(".capability"))
        else:
            other_entries.append(name)

    if baseline is None:
        raise OFBundleNotFound(
            "No baseline ZIP found in the .ofocus bundle. "
            f"Expected a file starting with '{_BASELINE_PREFIX}'. "
            f"Found: {filenames!r}"
        )

    return BundleState(
        baseline=baseline,
        deltas=tuple(sorted(deltas, key=lambda delta: delta.filename)),
        clients=tuple(sorted(clients, key=lambda client: client.filename)),
        capabilities=tuple(capabilities),
        other_entries=tuple(other_entries),
    )
