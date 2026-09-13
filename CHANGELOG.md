# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Because the two servers are released together from one repository, one version
number covers both.

## [Unreleased]

### Added
- `docs/images/` — screenshots taken from AutoCAD and Trimble Connect while both
  MCP servers were driving them, plus a terminal run of the three CI commands.
  `docs/images/README.md` records the exact tool sequence behind every image so
  each one can be reproduced instead of being taken on trust.
- `scripts/capture-window.ps1` — captures an application window to PNG, including
  hardware-accelerated 3D viewports, which Win32 `PrintWindow` returns as a black
  rectangle.
- `scripts/redact-image.ps1` — paints over identifying text and crops a screenshot
  before it is committed. Once an image is committed it lives in git history
  permanently; deleting the file in a later commit does not remove it.
- `tests/test_autocad_client.py` — 8 behaviour tests with fake COM objects,
  covering the three defects fixed below. They need no AutoCAD, like the rest of
  the suite.
- Two layout tests guarding the screenshots: that `.gitignore` does not swallow
  `docs/images/*.png` (a broken exclusion shows as intact images locally and as
  broken ones on GitHub), and that every image is referenced by at least one
  README.

### Changed
- The README no longer states how many tests there are. The count appeared in
  four places plus a screenshot; a screenshot cannot be kept in sync by grep or
  by a test, so it silently becomes the most-trusted stale copy in the docs.
  `pytest` prints the number itself.
- `.gitignore` now blocks the working files that accumulate in the repository
  root of a folder used for daily engineering work — `*.xlsx`, `*.pdf`, `*.dwg`,
  `*.ifc`, render folders — with an explicit exception for `docs/images/*.png`.
  The repository is public, and one `git add .` would have put client quantity
  spreadsheets and drawings into its history permanently. Two more MCP servers
  kept loose in the same folder are ignored for the same reason, which also makes
  a local `ruff check .` agree with CI.

### Fixed
- **`draw_hatch` failed with "Invalid input" whenever more than one boundary was
  passed.** `AppendOuterLoop` takes a single closed loop, so handing it an array
  of N disjoint boundaries made AutoCAD read them as N curves forming one loop,
  which cannot close. Each boundary is now appended as its own loop. The
  single-boundary path always worked, which is why the plural — the parameter
  name, the docstring, and the documented contract — went untested.
- **Dimensions ignored the `DIM*` system variables.** `AddDimAligned` and friends
  read their properties from the current dimension style, not from the system
  variables, so `set_system_variable("DIMSCALE", 80)` changed the variable and
  nothing else. On a millimetre drawing started from the imperial default
  template that left `DIMTXT` at 0.18, i.e. text 0.18 mm tall on a 6000 mm
  drawing — dimensions that render as bare extension lines with no number and no
  error message. The variables are now applied to each dimension as it is created.
- **A transient COM error while resolving a handle was reported as "handle not
  found".** `delete_entities` caught every exception per handle, which swallowed
  the dead-pointer and server-busy errors that `_guard` exists to recover from:
  the whole batch came back as "not found" while the objects were still in the
  drawing. Transient errors now propagate so the connection is rebuilt and the
  call retried; the resolve loop runs before anything is deleted, so replaying it
  is safe.
- **"Handle not found" did not say which drawing was searched.** A handle is
  unique within one drawing and the server follows AutoCAD's active document, so
  switching tabs between two calls invalidates it. The message now names the
  drawing and says so.
- **`add_leader` left an orphaned MText behind when it failed.** The annotation is
  created before the leader; if `AddLeader` then threw, the text stayed in the
  drawing with nothing pointing at it — a line of text floating in the model with
  no visible cause. It is now removed when the leader cannot be created.

### Added (earlier in this cycle)
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
