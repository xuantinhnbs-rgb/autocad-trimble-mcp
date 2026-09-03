# Security Policy

## Trust model — read this before you connect the servers

These two MCP servers hand a language model **direct control of desktop
software on your machine**. That is the whole point of the project, and it is
also the main thing to be aware of:

| Capability | What it means in practice |
|---|---|
| `run_autolisp`, `send_autocad_command` | Arbitrary AutoLISP and arbitrary AutoCAD commands run inside your AutoCAD session |
| `save_document`, `close_document`, `open_dwg_document` | Drawings on disk can be overwritten, closed without saving, or opened |
| `delete_entities`, `delete_layer`, `purge_drawing` | Drawing content can be deleted, including in bulk |
| `export_drawing_to_pdf`, `export_drawing_to_dxf` | Files are written to paths the model chooses |
| `set_model_placement`, `set_visual_state`, `create_view` | Trimble Connect project state is modified for the open project |

There is **no sandbox and no confirmation prompt inside the servers**. Every
guard rail lives in the MCP client. So:

- **Only connect these servers to an MCP client you trust**, and keep that
  client's tool-approval prompts on rather than blanket-approving everything.
- **Work on copies of drawings** while you are getting used to it. `_UNDO` in
  AutoCAD covers a lot, but not a `save_document` that already happened.
- **Do not run this on a machine where AutoCAD holds drawings you cannot afford
  to lose**, unless those drawings are backed up or under version control.
- Treat drawing and model content as untrusted input if it came from outside:
  text inside a DWG or an IFC property can carry prompt-injection payloads that
  the model will read when it queries the drawing.

Neither server opens a network port, and neither sends your data anywhere. Both
communicate over stdio with the local MCP client only; the Trimble bridge talks
to Trimble Connect over its local IPC channel.

## Supported versions

Only the latest commit on `main` is supported. There are no maintenance
branches.

## Reporting a vulnerability

Please **do not** open a public issue for a security problem.

Report it privately through GitHub:
[**Security → Report a vulnerability**](https://github.com/xuantinhnbs-rgb/autocad-trimble-mcp/security/advisories/new)

Please include the affected file or tool, what an attacker could achieve, and a
minimal way to reproduce it. Reports in English or Vietnamese are both fine.

This is a personal, unpaid project — expect an answer in days, not hours, and
no formal SLA. Credit will be given in the changelog unless you prefer
otherwise.
