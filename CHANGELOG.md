# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.6] - 2026-03-24

### Added

- Support task reassignment during updates in both CLI and MCP, including moving tasks into a
  project by `project_id`, moving them back to inbox, replacing tags, and clearing tags

### Fixed

- Persist sync client identity separately from transient writer state so the same cache
  directory reuses the same OmniFocus registered client identity across restarts and repairs
- Use a stable default sync client device name instead of the container hostname

## [1.0.5] - 2026-03-24

### Fixed

- Preserve freshly created tasks in the parsed model when later OmniFocus `op="update"`
  deltas omit `<name>`, so MCP `get_task` and `update_task` can immediately resolve IDs
  returned by `add_task`
- Merge partial task updates in the parser instead of treating name-less update deltas as
  deletion markers

## [1.0.4] - 2026-03-24

### Fixed

- CLI and container `--version` output now reads the installed package metadata instead of a stale hardcoded module constant
- Release `v1.0.4` restores consistency between Git tag, package metadata, release assets, and runtime version reporting

## [1.0.3] - 2026-03-24

### Changed

- Split CI badge publishing into a separate write-scoped job while keeping the public badge URL stable
- Normalized release metadata so package version, changelog, tags, and release assets are aligned again
- Refreshed the local agent operating rules for the now-public repository and hardened release process

### Fixed

- Main branch protection readiness for required checks and signed-commit enforcement
- Public-repo release hygiene around version drift between `pyproject.toml`, changelog entries, and release tags

## [1.0.2] - 2026-03-24

### Changed

- Pinned GitHub Actions workflow dependencies to full commit SHAs for public-repo policy compliance
- Improved README release badging and container release presentation

### Fixed

- Release workflow deprecation warnings by removing the remaining Node 20-based actions
- Coverage badge branch publishing by configuring Git identity in the temporary checkout
- Coverage badge workflow YAML errors discovered during release hardening

## [1.0.1] - 2026-03-24

### Added

- `pip-audit` in the release-quality verification workflow
- runtime container smoke tests in CI for the `of` launcher
- dynamic coverage badge publishing for the default branch

### Changed

- Simplified container CLI invocation around the `of` launcher
- Improved CLI help output and container-mode messaging
- Refreshed README, contribution guide, and release automation docs
- Clarified GHCR and GitHub Releases as the active publish channels
- Aligned internal engineering guidance with the Python 3.14 runtime baseline

### Fixed

- GitHub Actions readiness for the Node 24 transition
- CI regressions around formatting and CLI launcher coverage discovered during release hardening

## [1.0.0] - 2026-03-23

### Added

- Initial OmniFocus CLI and MCP server release
