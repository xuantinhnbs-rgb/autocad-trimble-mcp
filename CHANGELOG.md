# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Because the two servers are released together from one repository, one version
number covers both.

## [Unreleased]

### Added
- `tests/` — 32 contract tests that run without AutoCAD or Trimble Connect
  installed: tool counts match the documentation, every tool has a description
  and a valid `object` input schema, the `safe()` wrapper never lets an
  exception escape, and the repository layout / `.mcp.json.example` stay in sync
  with `install.py`.
- `pyproject.toml` — ruff and pytest configuration, so lint and test give the
  same result locally and on CI.
- `requirements-dev.txt`, `.editorconfig`.
- Project documentation: `CONTRIBUTING.md`, `CHANGELOG.md`, `SECURITY.md`
  (including the trust model for giving a model control of desktop CAD),
  `CODE_OF_CONDUCT.md`.
- GitHub issue and pull-request templates, and a Dependabot configuration for
  `pip` and GitHub Actions.
- `instructions=` on the AutoCAD MCP server, matching the Trimble one, so a
  model is told up front that AutoCAD must be running and that `batch_draw` is
  the right tool for bulk work.

### Changed
- CI now runs three jobs: lint (ruff), tests (pytest on Python 3.10–3.13), and
  the existing server load check. It also declares read-only permissions and
  cancels superseded runs.
- Source cleaned up to pass lint: unused imports and locals removed, imports
  sorted, trailing whitespace stripped, ambiguous single-letter variables
  renamed, over-long lines wrapped. No behaviour changed — both servers still
  register 49 and 34 tools respectively.

## [1.0.0] - 2026-09-02

First public release.

### Added
- `autocad-2022` MCP server: 49 tools driving AutoCAD 2022+ over COM —
  geometry, layers, dimensions, text, entity queries, AutoLISP, PDF/DXF export,
  and `batch_draw` for up to 5000 entities in a single call. Automatic
  reconnection when AutoCAD is closed and reopened, retry when it is busy, and
  all COM traffic funnelled onto one dedicated thread.
- `trimble-connect` MCP server: 34 tools driving Trimble Connect for Desktop
  through a self-compiling C# bridge (`csc.exe`, no Visual Studio or .NET SDK
  needed) — models, object search, IFC property sets, assembly hierarchy,
  colours, visual states, saved views and camera.
- A shared response contract: every tool returns JSON with an `ok` key, and no
  tool ever lets an exception escape.
- `install.py` — detects the interpreter and project directory on the machine it
  runs on, verifies dependencies, loads both servers to confirm their tools
  register, then writes `.mcp.json`. Flags: `--check`, `--autocad`,
  `--trimble`, `--claude-desktop`.
- Bilingual entry point (`README.md` / `README.vi.md`), per-server
  documentation, MIT licence, and CI that loads both servers on Windows across
  Python 3.10–3.13.

[Unreleased]: https://github.com/xuantinhnbs-rgb/autocad-trimble-mcp/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/xuantinhnbs-rgb/autocad-trimble-mcp/releases/tag/v1.0.0
