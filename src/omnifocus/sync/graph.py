"""OmniFocus sync DAG traversal helpers.

This module contains the pure graph logic used to reconstruct the current
read-view of an OmniFocus bundle. The WebDAV bundle is a DAG of delta ZIPs:
each delta produces a new tail and may merge multiple parent tails.
"""

from __future__ import annotations

__author__ = "Maciej Szymczak <maciej@szymczak.at>"

from omnifocus.errors import OFError
from omnifocus.sync.client_state import ClientStateDocument
from omnifocus.sync.protocol import BundleState


def current_tail_id(
    state: BundleState,
    remote_clients: dict[str, ClientStateDocument],
) -> str | None:
    """Return the best-known current tail identifier for the bundle."""
    frontier = current_frontier_tail_ids(state, remote_clients)
    return frontier[0] if frontier else None


def current_frontier_tail_ids(
    state: BundleState,
    remote_clients: dict[str, ClientStateDocument],
) -> tuple[str, ...]:
    """Return the current frontier tails used to build the read model."""
    if state.deltas and state.baseline.tail_id is not None:
        sink_tails = tuple(
            delta.tail_id
            for delta in reversed(state.deltas)
            if is_frontier_tail(state, delta.tail_id)
            and tail_reachable_from_baseline(state, delta.tail_id)
        )
        maximal_sink_tails = maximal_tail_ids(state, sink_tails)
        if maximal_sink_tails:
            return maximal_sink_tails

    reachable_client_tails: list[str] = []
    for ref in reversed(state.clients):
        document = remote_clients.get(ref.client_id)
        if document is None:
            continue
        for candidate in document.tail_identifiers:
            if candidate not in reachable_client_tails and tail_reachable_from_baseline(
                state, candidate
            ):
                reachable_client_tails.append(candidate)

    maximal_client_tails = maximal_tail_ids(state, tuple(reachable_client_tails))
    if maximal_client_tails:
        return maximal_client_tails

    if state.deltas and state.baseline.tail_id is not None:
        return (state.baseline.tail_id,)
    if state.deltas:
        return (state.deltas[-1].tail_id,)
    if state.baseline.tail_id:
        return (state.baseline.tail_id,)
    return ()


def transaction_filenames_for_frontier(
    state: BundleState,
    frontier_tail_identifiers: tuple[str, ...],
) -> list[str]:
    """Return delta filenames reachable from the given frontier tails."""
    if not frontier_tail_identifiers:
        return []
    selected_tail_ids = reachable_delta_tail_ids(state, frontier_tail_identifiers)
    return topologically_sorted_delta_filenames(state, selected_tail_ids)


def is_frontier_tail(state: BundleState, tail_id: str) -> bool:
    """Return whether *tail_id* is not referenced as a parent by any delta."""
    all_parent_tail_ids = {
        parent_tail_id for delta in state.deltas for parent_tail_id in delta.parent_tail_ids
    }
    return tail_id not in all_parent_tail_ids


def topologically_sorted_delta_filenames(
    state: BundleState,
    selected_tail_ids: set[str],
) -> list[str]:
    """Return selected delta filenames in parent-before-child order."""
    deltas_by_tail = {delta.tail_id: delta for delta in state.deltas}
    ordered: list[str] = []
    visited: set[str] = set()

    # Iterative post-order DFS (explicit stack) to avoid recursion on deep
    # delta chains. Each frame is (tail_id, parents_emitted): the second time we
    # pop a tail — after its parents — we record its filename.
    for root in state.deltas:
        if root.tail_id not in selected_tail_ids:
            continue
        stack: list[tuple[str, bool]] = [(root.tail_id, False)]
        while stack:
            tail_id, parents_emitted = stack.pop()
            if parents_emitted:
                visited.add(tail_id)
                ordered.append(deltas_by_tail[tail_id].filename)
                continue
            if tail_id in visited or tail_id not in selected_tail_ids:
                continue
            stack.append((tail_id, True))
            # Push parents in reverse so the first parent is processed first,
            # preserving the recursive parent-before-child emission order.
            for parent_tail_id in reversed(deltas_by_tail[tail_id].parent_tail_ids):
                stack.append((parent_tail_id, False))
    return ordered


def maximal_tail_ids(
    state: BundleState,
    tail_ids: tuple[str, ...],
) -> tuple[str, ...]:
    """Return tails with ancestor tails removed while preserving order."""
    unique_tail_ids = tuple(dict.fromkeys(tail_ids))
    maximal: list[str] = []
    for candidate in unique_tail_ids:
        if any(
            other != candidate and tail_depends_on(state, other, candidate)
            for other in unique_tail_ids
        ):
            continue
        maximal.append(candidate)
    return tuple(maximal)


def reachable_delta_tail_ids(
    state: BundleState,
    frontier_tail_identifiers: tuple[str, ...],
) -> set[str]:
    """Return the closure of delta tails reachable from the frontier."""
    baseline_tail = state.baseline.tail_id
    deltas_by_tail = {delta.tail_id: delta for delta in state.deltas}
    selected: set[str] = set()
    on_path: set[str] = set()

    # Iterative DFS (explicit stack) to avoid recursion on deep delta chains.
    # ``on_path`` is the set of tails currently on the traversal path, used to
    # detect cycles; tails are added to ``selected`` in post-order.
    for frontier_tail in frontier_tail_identifiers:
        stack = [frontier_tail]
        while stack:
            tail_id = stack[-1]
            if tail_id == baseline_tail or tail_id in selected:
                stack.pop()
                continue
            if tail_id not in on_path:
                delta = deltas_by_tail.get(tail_id)
                if delta is None:
                    raise OFError(
                        f"Could not resolve the current OmniFocus delta DAG for tail {tail_id!r}"
                    )
                on_path.add(tail_id)
                for parent_tail_id in delta.parent_tail_ids:
                    if parent_tail_id == baseline_tail or parent_tail_id in selected:
                        continue
                    if parent_tail_id in on_path:
                        raise OFError(
                            "Detected a cycle while resolving delta DAG "
                            f"at tail {parent_tail_id!r}"
                        )
                    stack.append(parent_tail_id)
                continue
            # Second visit: all parents resolved — record in post-order.
            on_path.discard(tail_id)
            selected.add(tail_id)
            stack.pop()

    return selected


def tail_reachable_from_baseline(state: BundleState, tail_id: str) -> bool:
    """Return whether *tail_id* can be walked back to the baseline tail."""
    baseline_tail = state.baseline.tail_id
    if baseline_tail is None or not state.deltas:
        return True
    if tail_id == baseline_tail:
        return True

    deltas_by_tail = {delta.tail_id: delta for delta in state.deltas}
    memo: dict[str, bool] = {}
    on_path: set[str] = set()

    # Iterative DFS (explicit stack) to avoid recursion on deep delta chains.
    # A tail is reachable iff every parent chain terminates at the baseline; an
    # unresolved parent still on the path is a cycle and counts as unreachable.
    stack = [tail_id]
    while stack:
        cursor = stack[-1]
        if cursor in memo:
            stack.pop()
            continue
        delta = deltas_by_tail.get(cursor)
        if delta is None:
            memo[cursor] = False
            stack.pop()
            continue
        if cursor not in on_path:
            on_path.add(cursor)
            for parent_tail_id in delta.parent_tail_ids:
                if (
                    parent_tail_id != baseline_tail
                    and parent_tail_id not in memo
                    and parent_tail_id not in on_path
                ):
                    stack.append(parent_tail_id)
            continue
        # Second visit: fold parent results with AND semantics.
        on_path.discard(cursor)
        reachable = True
        for parent_tail_id in delta.parent_tail_ids:
            if parent_tail_id == baseline_tail:
                continue
            if not memo.get(parent_tail_id, False):
                reachable = False
                break
        memo[cursor] = reachable
        stack.pop()

    return memo[tail_id]


def tail_depends_on(state: BundleState, tail_id: str, ancestor_tail_id: str) -> bool:
    """Return whether *tail_id* transitively depends on *ancestor_tail_id*."""
    if tail_id == ancestor_tail_id:
        return False
    deltas_by_tail = {delta.tail_id: delta for delta in state.deltas}
    visited: set[str] = set()

    # Iterative reachability (explicit stack) over parent edges: is
    # ``ancestor_tail_id`` a parent of any tail reachable from ``tail_id``?
    stack = [tail_id]
    while stack:
        cursor = stack.pop()
        if cursor in visited:
            continue
        visited.add(cursor)
        delta = deltas_by_tail.get(cursor)
        if delta is None:
            continue
        if ancestor_tail_id in delta.parent_tail_ids:
            return True
        stack.extend(delta.parent_tail_ids)

    return False
