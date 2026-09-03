# Contributing

Thanks for taking an interest in this project. Issues and pull requests are
welcome — **in English or Vietnamese**, whichever you are comfortable with.

---

## Before you start

Both servers drive **Windows desktop applications**, so meaningful development
needs Windows. You can still work on documentation, `install.py`, the test suite
and the repository layout from any platform — `tests/test_repo_layout.py` is the
part of the suite that runs everywhere.

---

## Setting up

```powershell
git clone https://github.com/xuantinhnbs-rgb/autocad-trimble-mcp.git
cd autocad-trimble-mcp

pip install -r autocad-mcp/requirements.txt     # only if you touch the AutoCAD server
pip install -r trimble-mcp/requirements.txt     # only if you touch the Trimble server
pip install -r requirements-dev.txt             # ruff + pytest

python install.py --check                       # both servers load, tool counts printed
```

---

## Before opening a pull request

Run the same three checks CI runs:

```powershell
ruff check .                                    # lint (config lives in pyproject.toml)
pytest                                          # 30+ contract tests, no CAD software needed
python install.py --check                       # loads both servers, counts their tools
```

All three must pass. Nothing in the test suite requires AutoCAD or Trimble
Connect to be installed — both clients connect lazily, so registering tools
never touches the applications.

---

## Code conventions

- **Comments and docstrings are written in Vietnamese.** Keep it that way in
  the server code; the docstring of a tool is what the model reads to decide
  when to call it, and rewriting them mid-project would fragment the docs.
- **Line length 120.** Enforced by ruff. `autocad-mcp/app.py` (the optional
  Tkinter GUI) is exempt from the line-length rule only.
- **`from __future__` is not used.** Python 3.10 is the minimum supported
  version; `pyupgrade` rules are deliberately off — see the comment in
  `pyproject.toml` for why.

### Adding a tool

1. Write the function in the server module and decorate it
   `@mcp.tool()` then `@safe` — in that order.
2. Return a `dict`. `safe()` adds `"ok": true` if you do not set it, so return
   plain data on success and raise on failure.
3. Raise a domain error (`AcadError` / `TrimbleError`) with a message that says
   **how to fix the problem**, not just what broke. That message goes straight
   to the model.
4. Never let an exception escape a tool. `safe()` is the safety net, not the
   plan — validate inputs explicitly.
5. Document the parameters with `:param name:` lines. They become the JSON
   schema description the model sees.
6. Update the tool table in that server's `README.md` **and** the count in
   `tests/test_tool_contracts.py` (`EXPECTED_COUNTS`) — the test fails
   otherwise, on purpose.

### Touching the Trimble bridge

`trimble_mcp/bridge/*.cs` is compiled on first run by `csc.exe`. After editing
a `.cs` file, delete `TrimbleBridge.exe` (or just run the server — it detects
the newer source and rebuilds). Never commit the `.exe`.

---

## Commits and pull requests

- One logical change per commit; a short imperative subject line is enough.
- Say in the pull request **which of the three checks you ran** and on which
  Windows / Python / application versions you tested.
- If a change can only be verified with AutoCAD or Trimble Connect open, say so
  — CI cannot cover that, and a reviewer needs to know what to try by hand.

---

## Reporting bugs

Use the issue templates. The single most useful thing you can attach is the
output of:

```powershell
python install.py --check
```

For the Trimble server, also attach `%TEMP%\trimble_mcp_bridge.err.log`.
