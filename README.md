# autocad-trimble-mcp

***English** · [Tiếng Việt](README.vi.md)*

[![CI](https://github.com/xuantinhnbs-rgb/autocad-trimble-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/xuantinhnbs-rgb/autocad-trimble-mcp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Windows-lightgrey.svg)](#requirements)

Two independent MCP servers that let Claude — or any MCP client such as Claude
Code, Claude Desktop, Cursor or Cline — drive CAD and BIM software running on
your Windows machine.

| Server | Drives | Tools | Transport | Docs |
|---|---|---|---|---|
| `autocad-2022` | AutoCAD 2022+ | 49 | COM | [autocad-mcp/](autocad-mcp/README.md) |
| `trimble-connect` | Trimble Connect for Desktop | 34 | .NET Desktop API via a C# bridge | [trimble-mcp/](trimble-mcp/README.md) |

Both servers share one response contract: **every tool returns JSON with an `ok`
key** — `{"ok": true, ...}` on success, `{"ok": false, "error": "..."}` on failure.
No tool ever lets an exception escape, so the model always receives a readable
message instead of a raw COM or .NET stack trace.

> **Note on documentation language.** The detailed per-server docs and all code
> comments are written in Vietnamese. This README is the English entry point.

---

## What you can do with it

**AutoCAD** — draw lines, polylines, arcs, circles, splines and hatches; batch-draw
hundreds of entities in one call; create and manage layers; add dimensions, leaders
and text; find and replace text across a drawing; query entities and drawing
statistics; run AutoLISP; export to PDF or DXF.

**Trimble Connect** — list and load models; find objects by IFC type, attribute or
selection; read full IFC property sets; walk the assembly hierarchy; colour, hide
and isolate objects; save and activate views; drive the camera; reposition models.

---

## Requirements

- **Windows.** Both servers talk to desktop applications through Windows-only APIs.
- **Python 3.10 or newer.**
- **AutoCAD 2022 or newer** for the AutoCAD server (needs `pywin32`).
- **Trimble Connect for Desktop** plus **.NET Framework 4.x** for the Trimble server.
  .NET Framework ships with Windows 10 and 11 — no Visual Studio or .NET SDK needed.

You only need the software for the server you actually intend to use.

---

## Install

```powershell
git clone https://github.com/xuantinhnbs-rgb/autocad-trimble-mcp.git
cd autocad-trimble-mcp

pip install -r autocad-mcp/requirements.txt     # for AutoCAD
pip install -r trimble-mcp/requirements.txt     # for Trimble Connect

python install.py
```

`install.py` detects the Python interpreter and project directory **on the machine
it is running on**, verifies the required packages, loads each server to confirm
its tools register, and only then writes `.mcp.json`. You never edit a path by hand.

```powershell
python install.py --check            # verify only, write nothing
python install.py --autocad          # configure AutoCAD only
python install.py --trimble          # configure Trimble Connect only
python install.py --claude-desktop   # also write Claude Desktop's config
```

Then open Claude Code **in the project root** (where `.mcp.json` was written) and
run `/mcp` to confirm the servers connected.

`.mcp.json` is deliberately **not** in the repository: it contains absolute paths
that are valid on exactly one machine. See [.mcp.json.example](.mcp.json.example)
for its shape.

---

## How the Trimble bridge works

Trimble Connect for Desktop exposes no COM API. It opens a .NET Desktop API
(`Trimble.Connect.Desktop.API.dll`, .NET Framework 4.8) over an internal IPC
channel, and Python has no `pythonnet` build for recent versions. This project
bridges the gap with a small C# helper:

```
Claude ──MCP/stdio──► trimble_server.py ──JSON lines──► TrimbleBridge.exe ──► Trimble Connect
                          (Python)          (stdin/stdout)     (.NET 4.8)
```

`TrimbleBridge.exe` is **compiled on first run** by `csc.exe`, which ships with
every Windows install — so there is no build step and no `.exe` in the repository.
The connection is held open for the server's lifetime, and the bridge reconnects
by itself if Trimble Connect is closed and reopened.

---

## Project layout

```
autocad-trimble-mcp/
├── install.py            # detects this machine's paths, writes .mcp.json
├── .mcp.json.example     # reference shape of the config
├── autocad-mcp/          # everything for the AutoCAD server
├── trimble-mcp/          # everything for the Trimble server
└── .github/workflows/    # CI: loads both servers on Windows
```

Each server folder is **self-contained** — its own README, `requirements.txt` and
entry point. To share just one of them, zip that folder and send it.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `/mcp` shows the server as not connected | Run `python install.py --check` to see what is missing |
| `ModuleNotFoundError: mcp` | `pip install -r <server-folder>/requirements.txt` |
| Server starts but every tool returns an error | The application is not running, or has no drawing/project open |
| Garbled output running scripts by hand | Set `PYTHONIOENCODING=utf-8` first |
| `No Trimble Connect instance found` | Open Trimble Connect for Desktop, then call `refresh` |

Per-server troubleshooting lives in [autocad-mcp/README.md](autocad-mcp/README.md)
and [trimble-mcp/README.md](trimble-mcp/README.md).

---

## License

[MIT](LICENSE) — free for any use including commercial, keep the copyright notice.
