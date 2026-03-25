# Container and Runtime Notes

`omnifocus-cli` is designed for headless operation.

You do not need:
- OmniFocus.app
- macOS
- AppleScript
- Omni Automation permissions

You do need:
- network access to the OmniFocus WebDAV bundle
- valid WebDAV credentials
- the encryption passphrase when the bundle is encrypted

## Build

```bash
podman build --target runtime -t of .
```

## Persistent Cache

Mount a writable cache directory for faster warm starts:

```bash
mkdir -p .of-cache

podman run --rm \
  -v "$PWD/.of-cache":/cache \
  -e OF_CACHE_DIR=/cache \
  -e OF_WEBDAV_URL=https://dav.example.com/OmniFocus.ofocus/ \
  -e OF_WEBDAV_USER=username \
  -e OF_WEBDAV_PASS=password \
  of sync
```

## CLI vs MCP

- `podman run --rm of sync`
  Runs a CLI command.
- `podman run --rm -i of`
  Starts the MCP server over stdio.
- `podman run --rm -i of mcp`
  Starts the MCP server explicitly.

## Image Freshness

If you track `latest`, refresh the local image before debugging behavior:

```bash
podman pull ghcr.io/szymczag/omnifocus-cli:latest
```

or:

```bash
podman run --rm --pull=always ghcr.io/szymczag/omnifocus-cli:latest --version
```

## Environment Variables

| Variable | Required | Description |
| --- | --- | --- |
| `OF_WEBDAV_URL` | Yes | WebDAV bundle URL |
| `OF_WEBDAV_USER` | No | Explicit WebDAV username |
| `OF_WEBDAV_PASS` | No | Explicit WebDAV password |
| `OF_ENCRYPTION_PASSPHRASE` | No | Bundle decryption passphrase |
| `OF_CACHE_DIR` | No | Writable cache directory |

## Operational Notes

- The runtime image is intended to stay non-root.
- Cache invalidation happens automatically after write operations.
- The CLI and MCP server both operate on the same underlying WebDAV sync and parse layer.
