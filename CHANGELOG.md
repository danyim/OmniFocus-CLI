# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
