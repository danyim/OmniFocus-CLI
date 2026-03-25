# MCP Reference

`omnifocus-cli` can run as an MCP server over stdio.

Default container behavior:

```bash
podman run --rm -i of
```

Explicit mode:

```bash
podman run --rm -i of mcp
```

## Host Configuration

```json
{
  "mcpServers": {
    "omnifocus": {
      "command": "podman",
      "args": [
        "run",
        "--rm",
        "-i",
        "-v",
        "/absolute/path/to/cache:/cache",
        "-e",
        "OF_CACHE_DIR=/cache",
        "-e",
        "OF_WEBDAV_URL=https://dav.example.com/OmniFocus.ofocus/",
        "-e",
        "OF_WEBDAV_USER=username",
        "-e",
        "OF_WEBDAV_PASS=password",
        "-e",
        "OF_ENCRYPTION_PASSPHRASE=passphrase",
        "of:latest"
      ]
    }
  }
}
```

## Tool Surface

### Tasks

- `list_tasks`
  Filters: `inbox`, `today`, `flagged`, `due`, `project`, `tag`, `tag_id`, `limit`
- `search_tasks`
- `get_task`
- `add_task`
- `complete_task`
- `update_task`

Task responses include:
- `id`
- `name`
- `project`
- `inbox`
- `flagged`
- `due`
- `start`
- `completed`
- `note`
- `tag_ids`
- `tag_names`

### Projects

- `list_projects`
  Filters: `status`, `tag`, `tag_id`
- `get_project`
- `add_project`
- `update_project`
- `complete_project`

Project responses include:
- core project fields from the parsed model
- `folder_name`
- `tag_names`
- `review_due`
- `review_basis`

### Project Review

- `list_projects_for_review`
  Inputs: `due_only`, `limit`
- `mark_project_reviewed`
  Inputs: `project_id`, optional `reviewed_at`

Review fields:
- `last_review`
- `next_review`
- `review_interval`
- `review_due`
- `review_basis`

### Folders

- `list_folders`
- `get_folder`
- `get_folder_tree`
- `add_folder`
- `update_folder`
- `drop_folder`

### Tags

- `list_tags`
  Inputs: `all`
- `get_tag`
- `add_tag`
- `update_tag`
- `drop_tag`

Tag responses include:
- core tag fields from the parsed model
- `parent_name`
- `child_tag_ids`

### Sync

- `sync_now`

## Behavioral Notes

- MCP tools return structured dictionaries serialized as JSON text content.
- Mutation tools prefer stable IDs.
- List tools support some name-based filters for convenience.
- Tags are first-class entities; assigning tags to tasks or projects is separate from creating/updating tag objects.

## Not Yet Implemented

- perspectives
- statistics tools
- dedicated inbox MCP tools
