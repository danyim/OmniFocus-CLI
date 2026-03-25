"""MCP server for OmniFocus CLI.

Exposes OmniFocus task management as MCP tools consumable by Claude.
Runs over stdio transport (suitable for ``podman run --rm -i``).

Tools
-----
``list_tasks``      Filter active tasks by inbox/today/flagged/project/due.
``search_tasks``    Fuzzy search tasks by name.
``get_task``        Retrieve a single task by id.
``add_task``        Create a new task.
``complete_task``   Mark a task as completed.
``update_task``     Update task fields and state.
``get_project``     Retrieve a single project by id.
``add_project``     Create a new project.
``update_project``  Update a project.
``complete_project`` Mark a project completed.
``list_projects``   List projects (optionally filtered by status).
``list_projects_for_review`` List projects that are due for review.
``mark_project_reviewed`` Stamp a project as reviewed.
``list_folders``    List all folders.
``get_folder``      Retrieve a single folder by id.
``get_folder_tree`` Return the nested folder/project tree.
``add_folder``      Create a new folder.
``update_folder``   Update a folder.
``drop_folder``     Drop a folder.
``sync_now``        Trigger a full WebDAV sync.

Usage::

    # Native Python entry point
    of-mcp

    # Container default: MCP server mode (stdin/stdout)
    podman run --rm -i of

    # Explicit container MCP mode
    podman run --rm -i of mcp

    # In Claude MCP config (settings.json):
    {
      "mcpServers": {
        "omnifocus": {
          "command": "podman",
          "args": ["run", "--rm", "-i",
                   "-e", "OF_WEBDAV_URL",
                   "-e", "OF_WEBDAV_USER",
                   "-e", "OF_WEBDAV_PASS",
                   "-e", "OF_ENCRYPTION_PASSPHRASE",
                   "of:latest"]
        }
      }
    }
"""

from __future__ import annotations

__author__ = "Maciej Szymczak <maciej@szymczak.at>"

import asyncio
import dataclasses
import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, cast

import click
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from omnifocus.errors import OFError
from omnifocus.formatting import build_folder_tree_data
from omnifocus.fuzzy import find_tasks
from omnifocus.models import Folder, OFModel, Project, Task
from omnifocus.review import (
    ProjectReviewState,
    compute_project_review_state,
    mark_project_reviewed,
)
from omnifocus.store import OFocusStore

# ---------------------------------------------------------------------------
# Server instance
# ---------------------------------------------------------------------------

server: Server = Server("omnifocus")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _serialise(obj: Any) -> Any:
    """Recursively serialise an object to a JSON-safe form."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {k: _serialise(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, dict):
        return {k: _serialise(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serialise(item) for item in obj]
    return obj


def _text(data: Any) -> list[TextContent]:
    """Wrap any JSON-serialisable data as a list of MCP TextContent."""
    return [
        TextContent(
            type="text",
            text=json.dumps(_serialise(data), ensure_ascii=False, indent=2),
        )
    ]


async def _load_model(force: bool = False) -> OFModel:
    """Load the current OFModel via the store."""
    async with OFocusStore.from_env() as store:
        return await store.load(force_refresh=force)


def _parse_optional_date(value: str | None) -> datetime | None:
    """Parse an ISO 8601 date string or return None."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _parse_optional_utc_datetime(value: str | None) -> datetime | None:
    """Parse an ISO 8601 timestamp and normalise naive values to UTC."""
    parsed = _parse_optional_date(value)
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


# ---------------------------------------------------------------------------
# Tool: list_tasks
# ---------------------------------------------------------------------------


@server.list_tools()  # type: ignore[no-untyped-call, untyped-decorator]
async def list_tools() -> list[Tool]:
    """Return the list of all MCP tools provided by this server."""
    return [
        Tool(
            name="list_tasks",
            description=(
                "List active OmniFocus tasks. "
                "Optionally filter by inbox, today (due today or overdue), "
                "flagged, project name (substring), or tasks with a due date."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "inbox": {"type": "boolean", "description": "Inbox tasks only"},
                    "today": {"type": "boolean", "description": "Due today or overdue"},
                    "flagged": {"type": "boolean", "description": "Flagged tasks only"},
                    "due": {"type": "boolean", "description": "Tasks with any due date"},
                    "project": {"type": "string", "description": "Project name substring"},
                    "limit": {"type": "integer", "description": "Max tasks to return (default 50)"},
                },
            },
        ),
        Tool(
            name="search_tasks",
            description="Fuzzy search tasks by name or ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "limit": {"type": "integer", "description": "Max results (default 10)"},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="get_task",
            description="Get a single task by its OmniFocus ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Task ID"},
                },
                "required": ["task_id"],
            },
        ),
        Tool(
            name="add_task",
            description="Create a new OmniFocus task.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Task name"},
                    "project": {"type": "string", "description": "Project name (substring)"},
                    "due": {
                        "type": "string",
                        "description": "Due date ISO 8601 or natural (today/tomorrow/mon-sun)",
                    },
                    "flagged": {"type": "boolean"},
                    "note": {"type": "string"},
                },
                "required": ["name"],
            },
        ),
        Tool(
            name="complete_task",
            description="Mark a task as completed by ID or fuzzy name.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Task ID or name fragment"},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="update_task",
            description="Update a task's fields or mark it dropped.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string"},
                    "name": {"type": "string"},
                    "project_id": {"type": "string", "description": "Move task into this project"},
                    "clear_project": {
                        "type": "boolean",
                        "description": "Remove project assignment and move task to inbox",
                    },
                    "inbox": {
                        "type": "boolean",
                        "description": "When true, move task to inbox",
                    },
                    "due": {"type": "string", "description": "ISO 8601 datetime or empty to clear"},
                    "defer": {
                        "type": "string",
                        "description": "ISO 8601 datetime or empty to clear",
                    },
                    "flagged": {"type": "boolean"},
                    "note": {"type": "string"},
                    "estimate": {
                        "type": ["integer", "string"],
                        "description": "Estimated minutes or empty to clear",
                    },
                    "tag_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Replace tag IDs on the task",
                    },
                    "clear_tags": {"type": "boolean"},
                    "dropped": {"type": "boolean"},
                },
                "required": ["task_id"],
            },
        ),
        Tool(
            name="get_project",
            description="Get a single project by its OmniFocus ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {"type": "string", "description": "Project ID"},
                },
                "required": ["project_id"],
            },
        ),
        Tool(
            name="add_project",
            description="Create a new OmniFocus project.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "folder": {"type": "string", "description": "Folder name substring"},
                    "due": {"type": "string", "description": "Due date ISO 8601 or natural"},
                    "defer": {"type": "string", "description": "Defer date ISO 8601 or natural"},
                    "flagged": {"type": "boolean"},
                    "note": {"type": "string"},
                    "status": {"type": "string", "enum": ["active", "inactive"]},
                },
                "required": ["name"],
            },
        ),
        Tool(
            name="update_project",
            description="Update a project's fields, status, or folder assignment.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {"type": "string"},
                    "name": {"type": "string"},
                    "folder_id": {"type": "string", "description": "Move project into this folder"},
                    "clear_folder": {
                        "type": "boolean",
                        "description": "Remove folder assignment from the project",
                    },
                    "due": {"type": "string", "description": "ISO 8601 datetime or empty to clear"},
                    "defer": {
                        "type": "string",
                        "description": "ISO 8601 datetime or empty to clear",
                    },
                    "flagged": {"type": "boolean"},
                    "note": {"type": "string"},
                    "status": {"type": "string", "enum": ["active", "inactive", "done", "dropped"]},
                },
                "required": ["project_id"],
            },
        ),
        Tool(
            name="complete_project",
            description="Mark a project as completed by ID or fuzzy name.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Project ID or name fragment"},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="list_projects",
            description="List OmniFocus projects.",
            inputSchema={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["active", "all", "inactive", "done", "dropped"],
                        "description": "Filter by status (default: active)",
                    },
                },
            },
        ),
        Tool(
            name="list_projects_for_review",
            description="List active and inactive projects that are due for review.",
            inputSchema={
                "type": "object",
                "properties": {
                    "due_only": {
                        "type": "boolean",
                        "description": "When false, include non-due projects as well",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max projects to return (default 50)",
                    },
                },
            },
        ),
        Tool(
            name="mark_project_reviewed",
            description="Stamp a project as reviewed and recalculate next review when possible.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {"type": "string", "description": "Project ID"},
                    "reviewed_at": {
                        "type": "string",
                        "description": "Optional ISO 8601 timestamp; defaults to now in UTC",
                    },
                },
                "required": ["project_id"],
            },
        ),
        Tool(
            name="list_folders",
            description="List all OmniFocus folders.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="get_folder",
            description="Get a single folder by its OmniFocus ID.",
            inputSchema={
                "type": "object",
                "properties": {"folder_id": {"type": "string", "description": "Folder ID"}},
                "required": ["folder_id"],
            },
        ),
        Tool(
            name="get_folder_tree",
            description="Return the nested folder hierarchy with direct child projects.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="add_folder",
            description="Create a new OmniFocus folder.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "parent_folder_id": {"type": "string"},
                },
                "required": ["name"],
            },
        ),
        Tool(
            name="update_folder",
            description="Rename or move a folder under another folder.",
            inputSchema={
                "type": "object",
                "properties": {
                    "folder_id": {"type": "string"},
                    "name": {"type": "string"},
                    "parent_folder_id": {"type": "string"},
                    "clear_parent": {"type": "boolean"},
                },
                "required": ["folder_id"],
            },
        ),
        Tool(
            name="drop_folder",
            description="Drop a folder by ID.",
            inputSchema={
                "type": "object",
                "properties": {"folder_id": {"type": "string"}},
                "required": ["folder_id"],
            },
        ),
        Tool(
            name="sync_now",
            description="Trigger a full sync from the WebDAV server.",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


@server.call_tool()  # type: ignore[untyped-decorator]
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Dispatch incoming tool calls to the appropriate handler."""
    handlers: dict[str, Any] = {
        "list_tasks": _handle_list_tasks,
        "search_tasks": _handle_search_tasks,
        "get_task": _handle_get_task,
        "add_task": _handle_add_task,
        "complete_task": _handle_complete_task,
        "update_task": _handle_update_task,
        "get_project": _handle_get_project,
        "add_project": _handle_add_project,
        "update_project": _handle_update_project,
        "complete_project": _handle_complete_project,
        "list_projects": _handle_list_projects,
        "list_projects_for_review": _handle_list_projects_for_review,
        "mark_project_reviewed": _handle_mark_project_reviewed,
        "list_folders": _handle_list_folders,
        "get_folder": _handle_get_folder,
        "get_folder_tree": _handle_get_folder_tree,
        "add_folder": _handle_add_folder,
        "update_folder": _handle_update_folder,
        "drop_folder": _handle_drop_folder,
        "sync_now": _handle_sync_now,
    }
    handler = handlers.get(name)
    if handler is None:
        return _text({"error": f"Unknown tool: {name}"})
    try:
        typed_handler = cast(Callable[[dict[str, Any]], Awaitable[list[TextContent]]], handler)
        return await typed_handler(arguments)
    except OFError as exc:
        return _text({"error": str(exc)})


async def _handle_list_tasks(args: dict[str, Any]) -> list[TextContent]:
    model = await _load_model()
    tasks = model.active_tasks
    limit = int(args.get("limit", 50))

    if args.get("inbox"):
        tasks = [t for t in tasks if t.inbox]
    if args.get("today"):
        now_date = datetime.today().date()
        tasks = [t for t in tasks if t.due is not None and t.due.date() <= now_date]
    if args.get("flagged"):
        tasks = [t for t in tasks if t.flagged]
    if args.get("due"):
        tasks = [t for t in tasks if t.due is not None]
    if args.get("project"):
        needle = args["project"].lower()
        matching = {pid for pid, p in model.projects.items() if needle in p.name.lower()}
        tasks = [t for t in tasks if t.project_id in matching]

    return _text([_task_summary(t, model) for t in tasks[:limit]])


async def _handle_search_tasks(args: dict[str, Any]) -> list[TextContent]:
    query = str(args.get("query", ""))
    limit = int(args.get("limit", 10))
    model = await _load_model()
    results = find_tasks(query, model.active_tasks, limit=limit)
    return _text([{"score": round(r.score, 3), **_task_summary(r.task, model)} for r in results])


async def _handle_get_task(args: dict[str, Any]) -> list[TextContent]:
    task_id = str(args.get("task_id", ""))
    model = await _load_model()
    task = model.tasks.get(task_id)
    if task is None:
        return _text({"error": f"Task not found: {task_id}"})
    return _text(_task_summary(task, model))


async def _handle_add_task(args: dict[str, Any]) -> list[TextContent]:
    from omnifocus.cli import _parse_due

    name = str(args.get("name", ""))
    if not name:
        return _text({"error": "name is required"})

    model = await _load_model()
    parent_task_id: str | None = None
    inbox = True

    if args.get("project"):
        needle = str(args["project"]).lower()
        matches = [
            p for p in model.projects.values() if needle in p.name.lower() and p.status == "active"
        ]
        if not matches:
            return _text({"error": f"No active project matching {args['project']!r}"})
        parent_task_id = matches[0].id
        inbox = False

    due_dt: datetime | None = None
    if args.get("due"):
        try:
            due_dt = _parse_due(str(args["due"]))
        except click.BadParameter:
            try:
                due_dt = datetime.fromisoformat(str(args["due"]))
            except ValueError:
                return _text({"error": f"Invalid due date: {args['due']!r}"})

    async with OFocusStore.from_env() as store:
        result = await store.add_task(
            name=name,
            parent_task_id=parent_task_id,
            inbox=inbox,
            flagged=bool(args.get("flagged", False)),
            due_dt=due_dt,
            note=str(args.get("note", "")),
        )

    return _text(result)


async def _handle_complete_task(args: dict[str, Any]) -> list[TextContent]:
    query = str(args.get("query", ""))
    model = await _load_model()
    results = find_tasks(query, model.active_tasks, limit=5)
    if not results:
        return _text({"error": f"No active task matching {query!r}"})
    task = results[0].task

    async with OFocusStore.from_env() as store:
        result = await store.complete_task(task)

    return _text(result)


async def _handle_update_task(args: dict[str, Any]) -> list[TextContent]:
    task_id = str(args.get("task_id", ""))
    model = await _load_model()
    task = model.tasks.get(task_id)
    if task is None:
        return _text({"error": f"Task not found: {task_id}"})

    project_id_value = str(args["project_id"]) if "project_id" in args else None
    clear_project = bool(args.get("clear_project", False))
    inbox_requested = "inbox" in args
    inbox_value = bool(args.get("inbox")) if inbox_requested else None

    if project_id_value and clear_project:
        return _text({"error": "project_id and clear_project cannot be combined"})
    if project_id_value and inbox_value is True:
        return _text({"error": "project_id and inbox=true cannot be combined"})
    if clear_project and inbox_value is False:
        return _text({"error": "clear_project cannot be combined with inbox=false"})

    new_parent_task_id = task.parent_task_id
    new_project_id = task.project_id
    new_inbox = task.inbox

    if project_id_value:
        project = model.projects.get(project_id_value)
        if project is None:
            return _text({"error": f"Project not found: {project_id_value}"})
        if project.status != "active":
            return _text({"error": f"Project is not active: {project_id_value}"})
        new_parent_task_id = project.id
        new_project_id = project.id
        new_inbox = False
    elif clear_project or inbox_value is True:
        new_parent_task_id = None
        new_project_id = None
        new_inbox = True

    now = datetime.now(UTC)
    estimate_value = task.estimated_minutes
    if "estimate" in args:
        raw_estimate = args["estimate"]
        if raw_estimate in ("", None):
            estimate_value = None
        else:
            try:
                estimate_value = int(raw_estimate)
            except TypeError, ValueError:
                return _text({"error": f"Invalid estimate: {raw_estimate!r}"})

    hidden_value = task.hidden
    if args.get("dropped") is True:
        hidden_value = now
    elif "dropped" in args and args.get("dropped") is False:
        hidden_value = None

    if args.get("clear_tags") and "tag_ids" in args:
        return _text({"error": "tag_ids and clear_tags cannot be combined"})

    tag_ids: tuple[str, ...]
    if args.get("clear_tags"):
        tag_ids = ()
    elif "tag_ids" in args:
        tag_ids = tuple(str(tag_id) for tag_id in args["tag_ids"])
        missing_tag_ids = [tag_id for tag_id in tag_ids if tag_id not in model.tags]
        if missing_tag_ids:
            joined = ", ".join(missing_tag_ids)
            return _text({"error": f"Unknown tag IDs: {joined}"})
    else:
        tag_ids = task.tag_ids

    updated = dataclasses.replace(
        task,
        name=str(args["name"]) if "name" in args else task.name,
        parent_task_id=new_parent_task_id,
        project_id=new_project_id,
        inbox=new_inbox,
        flagged=bool(args["flagged"]) if "flagged" in args else task.flagged,
        note=str(args["note"]) if "note" in args else task.note,
        due=_parse_optional_date(str(args["due"])) if "due" in args else task.due,
        start=_parse_optional_date(str(args["defer"])) if "defer" in args else task.start,
        estimated_minutes=estimate_value,
        tag_ids=tag_ids,
        hidden=hidden_value,
        modified=now,
    )

    async with OFocusStore.from_env() as store:
        if args.get("dropped") is True:
            result = await store.drop_task(updated)
        else:
            result = await store.update_task(updated)

    return _text(result)


async def _handle_add_project(args: dict[str, Any]) -> list[TextContent]:
    from omnifocus.cli import _parse_due

    name = str(args.get("name", ""))
    if not name:
        return _text({"error": "name is required"})

    model = await _load_model()
    folder_id: str | None = None
    if args.get("folder"):
        needle = str(args["folder"]).lower()
        matches = [folder for folder in model.folders.values() if needle in folder.name.lower()]
        if not matches:
            return _text({"error": f"No folder matching {args['folder']!r}"})
        if len(matches) > 1:
            return _text({"error": f"Multiple folders match {args['folder']!r}"})
        folder_id = matches[0].id

    def _parse_natural(value: Any) -> datetime | None:
        if not value:
            return None
        try:
            return _parse_due(str(value))
        except click.BadParameter:
            try:
                return datetime.fromisoformat(str(value))
            except ValueError:
                return None

    due_dt = _parse_natural(args.get("due"))
    if args.get("due") and due_dt is None:
        return _text({"error": f"Invalid due date: {args['due']!r}"})
    defer_dt = _parse_natural(args.get("defer"))
    if args.get("defer") and defer_dt is None:
        return _text({"error": f"Invalid defer date: {args['defer']!r}"})

    async with OFocusStore.from_env() as store:
        result = await store.add_project(
            name=name,
            folder_id=folder_id,
            status=str(args.get("status", "active")),
            flagged=bool(args.get("flagged", False)),
            due_dt=due_dt,
            start_dt=defer_dt,
            note=str(args.get("note", "")),
        )

    return _text(result)


async def _handle_get_project(args: dict[str, Any]) -> list[TextContent]:
    project_id = str(args.get("project_id", ""))
    model = await _load_model()
    project = model.projects.get(project_id)
    if project is None:
        return _text({"error": f"Project not found: {project_id}"})
    return _text(_project_summary(project, model))


async def _handle_update_project(args: dict[str, Any]) -> list[TextContent]:
    project_id = str(args.get("project_id", ""))
    model = await _load_model()
    project = model.projects.get(project_id)
    if project is None:
        return _text({"error": f"Project not found: {project_id}"})

    folder_id_value = str(args["folder_id"]) if "folder_id" in args else None
    clear_folder = bool(args.get("clear_folder", False))
    if folder_id_value and clear_folder:
        return _text({"error": "folder_id and clear_folder cannot be combined"})
    if folder_id_value:
        folder = model.folders.get(folder_id_value)
        if folder is None:
            return _text({"error": f"Folder not found: {folder_id_value}"})
        new_folder_id = folder.id
    elif clear_folder:
        new_folder_id = None
    else:
        new_folder_id = project.folder_id

    updated = dataclasses.replace(
        project,
        name=str(args["name"]) if "name" in args else project.name,
        folder_id=new_folder_id,
        status=str(args["status"]) if "status" in args else project.status,
        modified=datetime.now(UTC),
        flagged=bool(args["flagged"]) if "flagged" in args else project.flagged,
        due=_parse_optional_date(str(args["due"])) if "due" in args else project.due,
        start=_parse_optional_date(str(args["defer"])) if "defer" in args else project.start,
        note=str(args["note"]) if "note" in args else project.note,
    )
    if "status" in args and args["status"] == "done" and updated.completed is None:
        updated = dataclasses.replace(updated, completed=datetime.now(UTC))

    async with OFocusStore.from_env() as store:
        status = str(args["status"]) if "status" in args else updated.status
        if status == "done":
            result = await store.complete_project(updated)
        elif status == "dropped":
            result = await store.drop_project(updated)
        else:
            result = await store.update_project(updated)

    return _text(result)


async def _handle_complete_project(args: dict[str, Any]) -> list[TextContent]:
    query = str(args.get("query", ""))
    model = await _load_model()
    project = model.projects.get(query)
    if project is None:
        needle = query.lower()
        matches = [
            candidate for candidate in model.projects.values() if needle in candidate.name.lower()
        ]
        if not matches:
            return _text({"error": f"No project matching {query!r}"})
        if len(matches) > 1:
            return _text({"error": f"Multiple projects match {query!r}"})
        project = matches[0]

    async with OFocusStore.from_env() as store:
        result = await store.complete_project(project)

    return _text(result)


async def _handle_list_projects(args: dict[str, Any]) -> list[TextContent]:
    status = str(args.get("status", "active"))
    model = await _load_model()
    projects = [p for p in model.projects.values() if status == "all" or p.status == status]
    return _text([_project_summary(project, model) for project in projects])


async def _handle_list_projects_for_review(args: dict[str, Any]) -> list[TextContent]:
    model = await _load_model()
    due_only = bool(args.get("due_only", True))
    limit = int(args.get("limit", 50))
    now = datetime.now(UTC)
    candidates = [
        project for project in model.projects.values() if project.status in {"active", "inactive"}
    ]
    summaries: list[tuple[dict[str, Any], ProjectReviewState]] = [
        (_project_summary(project, model, now=now), compute_project_review_state(project, now=now))
        for project in candidates
    ]
    if due_only:
        summaries = [item for item in summaries if item[1].due]
    summaries.sort(key=lambda item: _project_review_sort_key(item[0], item[1]))
    return _text([summary for summary, _state in summaries[:limit]])


async def _handle_mark_project_reviewed(args: dict[str, Any]) -> list[TextContent]:
    project_id = str(args.get("project_id", ""))
    reviewed_at_raw = str(args["reviewed_at"]) if "reviewed_at" in args else None
    reviewed_at = _parse_optional_utc_datetime(reviewed_at_raw)
    if reviewed_at_raw is not None and reviewed_at is None:
        return _text({"error": f"Invalid reviewed_at timestamp: {reviewed_at_raw!r}"})

    model = await _load_model()
    project = model.projects.get(project_id)
    if project is None:
        return _text({"error": f"Project not found: {project_id}"})

    updated_project, recalculated = mark_project_reviewed(project, reviewed_at=reviewed_at)
    async with OFocusStore.from_env() as store:
        await store.mark_project_reviewed(project, reviewed_at=reviewed_at)

    summary = _project_summary(updated_project, model, now=reviewed_at or datetime.now(UTC))
    summary["next_review_recalculated"] = recalculated
    summary["status"] = "reviewed"
    return _text(summary)


async def _handle_list_folders(args: dict[str, Any]) -> list[TextContent]:
    model = await _load_model()
    folders = sorted(model.folders.values(), key=lambda folder: (folder.rank, folder.name.lower()))
    return _text([dataclasses.asdict(folder) for folder in folders])


async def _handle_get_folder(args: dict[str, Any]) -> list[TextContent]:
    folder_id = str(args.get("folder_id", ""))
    model = await _load_model()
    folder = model.folders.get(folder_id)
    if folder is None:
        return _text({"error": f"Folder not found: {folder_id}"})
    return _text(_folder_summary(folder, model))


async def _handle_get_folder_tree(args: dict[str, Any]) -> list[TextContent]:
    model = await _load_model()
    return _text(build_folder_tree_data(model.folders, model.projects))


async def _handle_add_folder(args: dict[str, Any]) -> list[TextContent]:
    name = str(args.get("name", ""))
    if not name:
        return _text({"error": "name is required"})
    model = await _load_model()
    parent_folder_id = str(args["parent_folder_id"]) if "parent_folder_id" in args else None
    if parent_folder_id is not None and parent_folder_id not in model.folders:
        return _text({"error": f"Folder not found: {parent_folder_id}"})
    async with OFocusStore.from_env() as store:
        result = await store.add_folder(name=name, parent_folder_id=parent_folder_id)
    return _text(result)


async def _handle_update_folder(args: dict[str, Any]) -> list[TextContent]:
    folder_id = str(args.get("folder_id", ""))
    model = await _load_model()
    folder = model.folders.get(folder_id)
    if folder is None:
        return _text({"error": f"Folder not found: {folder_id}"})

    parent_folder_id = str(args["parent_folder_id"]) if "parent_folder_id" in args else None
    clear_parent = bool(args.get("clear_parent", False))
    validation_error = _validate_folder_parent_change(
        model=model,
        folder_id=folder_id,
        parent_folder_id=parent_folder_id,
        clear_parent=clear_parent,
    )
    if validation_error is not None:
        return _text({"error": validation_error})

    if parent_folder_id is not None:
        new_parent_folder_id = parent_folder_id
    elif clear_parent:
        new_parent_folder_id = None
    else:
        new_parent_folder_id = folder.parent_folder_id

    updated = dataclasses.replace(
        folder,
        name=str(args["name"]) if "name" in args else folder.name,
        parent_folder_id=new_parent_folder_id,
        modified=datetime.now(UTC),
    )
    async with OFocusStore.from_env() as store:
        result = await store.update_folder(updated)
    return _text(result)


async def _handle_drop_folder(args: dict[str, Any]) -> list[TextContent]:
    folder_id = str(args.get("folder_id", ""))
    model = await _load_model()
    folder = model.folders.get(folder_id)
    if folder is None:
        return _text({"error": f"Folder not found: {folder_id}"})
    async with OFocusStore.from_env() as store:
        result = await store.drop_folder(folder)
    return _text(result)


async def _handle_sync_now(args: dict[str, Any]) -> list[TextContent]:
    async with OFocusStore.from_env() as store:
        model = await store.load(force_refresh=True)
    return _text(
        {
            "status": "synced",
            "tasks": len(model.tasks),
            "projects": len(model.projects),
            "folders": len(model.folders),
        }
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _task_summary(task: Task, model: OFModel) -> dict[str, Any]:
    """Return a concise dict representation of a task."""
    proj = model.projects.get(task.project_id or "")
    return {
        "id": task.id,
        "name": task.name,
        "project": proj.name if proj else None,
        "inbox": task.inbox,
        "flagged": task.flagged,
        "due": task.due.isoformat() if task.due else None,
        "start": task.start.isoformat() if task.start else None,
        "completed": task.completed.isoformat() if task.completed else None,
        "note": task.note,
        "tag_ids": list(task.tag_ids),
    }


def _project_summary(
    project: Project,
    model: OFModel,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return a concise dict representation of a project."""
    folder = model.folders.get(project.folder_id or "")
    review_state = compute_project_review_state(project, now=now)
    return {
        **dataclasses.asdict(project),
        "folder_name": folder.name if folder is not None else None,
        "review_due": review_state.due,
        "review_basis": review_state.basis,
    }


def _project_review_sort_key(
    summary: dict[str, Any],
    review_state: ProjectReviewState,
) -> tuple[int, datetime, int, str, str]:
    """Return a stable sort key for review queues."""
    due_at = review_state.due_at or datetime.max.replace(tzinfo=UTC)
    if review_state.basis == "unknown":
        bucket = 2
    elif review_state.due:
        bucket = 0
    else:
        bucket = 1
    rank = int(summary.get("rank", 0))
    name = str(summary.get("name", "")).lower()
    project_id = str(summary.get("id", ""))
    return (bucket, due_at, rank, name, project_id)


def _folder_summary(folder: Folder, model: OFModel) -> dict[str, Any]:
    """Return a concise dict representation of a folder."""
    child_folders = sorted(
        (
            candidate
            for candidate in model.folders.values()
            if candidate.parent_folder_id == folder.id
        ),
        key=lambda item: (item.rank, item.name.lower(), item.id),
    )
    child_projects = sorted(
        (project for project in model.projects.values() if project.folder_id == folder.id),
        key=lambda item: (item.rank, item.name.lower(), item.id),
    )
    return {
        **dataclasses.asdict(folder),
        "child_folder_ids": [candidate.id for candidate in child_folders],
        "project_ids": [project.id for project in child_projects],
    }


def _validate_folder_parent_change(
    *,
    model: OFModel,
    folder_id: str,
    parent_folder_id: str | None,
    clear_parent: bool,
) -> str | None:
    """Validate requested folder reparenting."""
    if parent_folder_id and clear_parent:
        return "parent_folder_id and clear_parent cannot be combined"
    if parent_folder_id is None:
        return None
    if parent_folder_id not in model.folders:
        return f"Folder not found: {parent_folder_id}"
    if parent_folder_id == folder_id:
        return "Folder cannot be its own parent"
    seen: set[str] = {folder_id}
    current_id: str | None = parent_folder_id
    while current_id is not None:
        if current_id in seen:
            return "Folder move would create a cycle"
        seen.add(current_id)
        parent = model.folders.get(current_id)
        current_id = None if parent is None else parent.parent_folder_id
    return None


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Start the MCP server over stdio.

    This is the entry point registered as ``of-mcp`` in ``pyproject.toml``.
    """

    async def _serve() -> None:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )

    asyncio.run(_serve())


if __name__ == "__main__":  # pragma: no cover
    main()
