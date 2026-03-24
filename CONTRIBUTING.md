# Contributing

## Development Setup

### Local Python environment

```bash
python3.14 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Container-based test environment

```bash
podman build --target test -t omnifocus-cli-test .
podman run --rm omnifocus-cli-test
```

## Quality Gate

Every change is expected to pass:

```bash
ruff check src/ tests/
black --check src/ tests/
mypy src/
pip-audit
pytest --cov=src/omnifocus --cov-fail-under=100 -q
```

## CI/CD

GitHub Actions workflows live under `.github/workflows/`.

- `ci.yml`
  Runs linting, formatting checks, `mypy`, full test coverage, and a runtime container build
- `release.yml`
  Builds Python artifacts, publishes the runtime image to GHCR on version tags, and creates a GitHub Release
- `dependabot.yml`
  Keeps Python dependencies and GitHub Actions versions updated

## Release Process

1. Update the version in `pyproject.toml` and `src/omnifocus/__init__.py`.
2. Add a new entry to `CHANGELOG.md`.
3. Run the full quality gate locally.
4. Create and push a tag such as `v1.0.1`.
5. Verify the GitHub Release and GHCR image outputs.
