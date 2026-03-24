"""Output formatters for CLI commands.

Provides table, tree, and JSON renderers for tasks and projects using
:mod:`rich`.  All renderers write directly to stdout unless a ``Console``
is injected (for testability).

Usage::

    from omnifocus.formatting import render_tasks_table, render_project_tree

    render_tasks_table(model.active_tasks, model.projects)
    render_project_tree(model.folders, model.projects)
"""

from __future__ import annotations

__author__ = "Maciej Szymczak <maciej@szymczak.at>"

import dataclasses
import json
from datetime import date, datetime
from typing import Any, cast

from rich import box
from rich.console import Console
from rich.table import Table
from rich.tree import Tree

from omnifocus.models import Folder, Project, Task

_DEFAULT_CONSOLE = Console()


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------


def render_tasks_table(
    tasks: list[Task],
    projects: dict[str, Project],
    console: Console | None = None,
) -> None:
    """Print a rich table of tasks to the console.

    Args:
        tasks: Tasks to display (already filtered by the caller).
        projects: Project dict for resolving project names.
        console: Optional :class:`rich.console.Console` for output (defaults
            to stdout).
    """
    out = console or _DEFAULT_CONSOLE
    table = Table(box=box.SIMPLE_HEAD, show_header=True, expand=False)
    table.add_column("ID", style="dim", min_width=11, no_wrap=True)
    table.add_column("Name", min_width=30)
    table.add_column("Project", style="cyan", width=24, no_wrap=True)
    table.add_column("Due", style="red", min_width=5, no_wrap=True)
    table.add_column("F", width=2, no_wrap=True)

    for task in sorted(tasks, key=lambda t: (t.due or datetime.max, t.rank)):
        proj_name = _project_name(task.project_id, projects)
        due_str = _format_due(task.due)
        flag = "★" if task.flagged else ""
        table.add_row(task.id, task.name, proj_name, due_str, flag)

    out.print(table)


def render_tasks_json(tasks: list[Task], console: Console | None = None) -> None:
    """Print tasks as a JSON array to the console.

    Args:
        tasks: Tasks to serialise.
        console: Optional console (defaults to stdout).
    """
    out = console or _DEFAULT_CONSOLE
    data = [_task_to_dict(t) for t in tasks]
    out.print(json.dumps(data, default=_json_default, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


def render_project_tree(
    folders: dict[str, Folder],
    projects: dict[str, Project],
    status_filter: str = "active",
    console: Console | None = None,
) -> None:
    """Print a hierarchical folder/project tree.

    Args:
        folders: All folders from the model.
        projects: All projects from the model.
        status_filter: ``"active"`` to show only active projects, ``"all"``
            to show all projects.
        console: Optional console (defaults to stdout).
    """
    out = console or _DEFAULT_CONSOLE

    filtered_projects = [
        p for p in projects.values() if status_filter == "all" or p.status == status_filter
    ]

    root_tree = Tree("[bold]OmniFocus[/bold]")

    # Build folder sub-trees (only top-level folders for now)
    folder_nodes: dict[str, Tree] = {}

    def get_or_create_folder_node(fid: str) -> Tree:
        if fid in folder_nodes:
            return folder_nodes[fid]
        folder = folders.get(fid)
        if folder is None:
            node = root_tree.add(f"[dim]({fid})[/dim]")
            folder_nodes[fid] = node
            return node
        # Recurse to ensure parent is created first
        if folder.parent_folder_id:
            parent_node = get_or_create_folder_node(folder.parent_folder_id)
        else:
            parent_node = root_tree
        node = parent_node.add(f"[bold]{folder.name}[/bold]")
        folder_nodes[fid] = node
        return node

    # Create all folder nodes
    for fid in sorted(folders.keys(), key=lambda x: folders[x].rank):
        get_or_create_folder_node(fid)

    # Slot projects under their folder nodes
    no_folder_node: Tree | None = None

    for project in sorted(filtered_projects, key=lambda p: p.rank):
        status_icon = _project_icon(project.status)
        flag_icon = " ★" if project.flagged else ""
        label = f"{status_icon} {project.name}{flag_icon}"

        if project.folder_id and project.folder_id in folder_nodes:
            folder_nodes[project.folder_id].add(label)
        else:
            if no_folder_node is None:
                no_folder_node = root_tree.add("[dim]No Folder[/dim]")
            no_folder_node.add(label)

    out.print(root_tree)


def render_projects_json(
    projects: dict[str, Project],
    console: Console | None = None,
) -> None:
    """Print projects as a JSON array.

    Args:
        projects: Projects to serialise.
        console: Optional console (defaults to stdout).
    """
    out = console or _DEFAULT_CONSOLE
    data = [_project_to_dict(p) for p in projects.values()]
    out.print(json.dumps(data, default=_json_default, ensure_ascii=False, indent=2))


def build_folder_tree_data(
    folders: dict[str, Folder],
    projects: dict[str, Project],
) -> dict[str, Any]:
    """Build a nested folder/project hierarchy for JSON and MCP output.

    Args:
        folders: All folders from the model.
        projects: All projects from the model.

    Returns:
        A dict containing nested folder nodes under ``folders`` and projects
        without folder assignment under ``no_folder_projects``.
    """
    folder_nodes: dict[str, dict[str, Any]] = {}

    for folder in folders.values():
        folder_nodes[folder.id] = {
            "folder": _folder_to_dict(folder),
            "children": [],
            "projects": [],
        }

    roots: list[dict[str, Any]] = []
    for folder in sorted(
        folders.values(), key=lambda item: (item.rank, item.name.lower(), item.id)
    ):
        node = folder_nodes[folder.id]
        if folder.parent_folder_id and folder.parent_folder_id in folder_nodes:
            folder_nodes[folder.parent_folder_id]["children"].append(node)
        else:
            roots.append(node)

    for project in sorted(
        projects.values(), key=lambda item: (item.rank, item.name.lower(), item.id)
    ):
        target = folder_nodes.get(project.folder_id or "")
        summary = _project_to_dict(project)
        if target is None:
            continue
        target["projects"].append(summary)

    no_folder_projects = [
        _project_to_dict(project)
        for project in sorted(
            (project for project in projects.values() if project.folder_id is None),
            key=lambda item: (item.rank, item.name.lower(), item.id),
        )
    ]
    dangling_folder_projects = [
        _project_to_dict(project)
        for project in sorted(
            (
                project
                for project in projects.values()
                if project.folder_id is not None and project.folder_id not in folder_nodes
            ),
            key=lambda item: (item.rank, item.name.lower(), item.id),
        )
    ]
    return {
        "folders": roots,
        "no_folder_projects": no_folder_projects,
        "dangling_folder_projects": dangling_folder_projects,
    }


def render_folder_tree(
    folders: dict[str, Folder],
    projects: dict[str, Project],
    console: Console | None = None,
) -> None:
    """Print a hierarchical folder tree with direct child projects."""
    out = console or _DEFAULT_CONSOLE
    data = build_folder_tree_data(folders, projects)
    root_tree = Tree("[bold]Folders[/bold]")

    def add_folder_node(parent: Tree, node: dict[str, Any]) -> None:
        folder = cast(dict[str, Any], node["folder"])
        branch = parent.add(f"[bold]{folder['name']}[/bold]")
        for child in cast(list[dict[str, Any]], node["children"]):
            add_folder_node(branch, child)
        for project in cast(list[dict[str, Any]], node["projects"]):
            branch.add(f"{_project_icon(str(project['status']))} {project['name']}")

    for node in cast(list[dict[str, Any]], data["folders"]):
        add_folder_node(root_tree, node)

    no_folder_projects = cast(list[dict[str, Any]], data["no_folder_projects"])
    if no_folder_projects:
        no_folder_branch = root_tree.add("[dim]No Folder[/dim]")
        for project in no_folder_projects:
            no_folder_branch.add(f"{_project_icon(str(project['status']))} {project['name']}")

    dangling_folder_projects = cast(list[dict[str, Any]], data["dangling_folder_projects"])
    if dangling_folder_projects:
        dangling_branch = root_tree.add("[dim]Missing Folder[/dim]")
        for project in dangling_folder_projects:
            folder_id = project["folder_id"]
            label = f"{_project_icon(str(project['status']))} {project['name']}"
            dangling_branch.add(f"{label} [dim]({folder_id})[/dim]")

    out.print(root_tree)


def render_folders_json(
    folders: dict[str, Folder],
    projects: dict[str, Project],
    console: Console | None = None,
) -> None:
    """Print nested folder/project hierarchy as JSON."""
    out = console or _DEFAULT_CONSOLE
    out.print(
        json.dumps(
            build_folder_tree_data(folders, projects),
            default=_json_default,
            ensure_ascii=False,
            indent=2,
        )
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _project_name(project_id: str | None, projects: dict[str, Project]) -> str:
    if project_id is None:
        return "Inbox"
    proj = projects.get(project_id)
    return proj.name if proj else f"({project_id})"


def _format_due(due: datetime | None) -> str:
    if due is None:
        return ""
    today = datetime.today()
    if due.date() < today.date():
        return f"[red]{due.strftime('%m-%d')}[/red]"
    if due.date() == today.date():
        return f"[yellow]{due.strftime('%m-%d')}[/yellow]"
    return due.strftime("%m-%d")


def _project_icon(status: str) -> str:
    icons = {"active": "●", "inactive": "○", "done": "✓", "dropped": "✗"}
    return icons.get(status, "?")


def _json_default(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serialisable")


def _task_to_dict(task: Task) -> dict[str, Any]:
    d = dataclasses.asdict(task)
    return d


def _project_to_dict(project: Project) -> dict[str, Any]:
    d = dataclasses.asdict(project)
    return d


def _folder_to_dict(folder: Folder) -> dict[str, Any]:
    d = dataclasses.asdict(folder)
    return d
