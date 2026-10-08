# BrightSync Flow Launcher plugin

Control BrightSync from Flow Launcher with the `bs` keyword. Talks to the local
command API of the running BrightSync tray app on `127.0.0.1`.

## Requirements

- Windows, Flow Launcher 2.x.
- **BrightSync installed and running** (the resident tray app). Get it at https://github.com/bberka/BrightSync. This plugin only talks to that app; it does not control brightness on its own.
- Python 3 on the path Flow Launcher uses. Standard library only, no pip packages.

## Commands

| Query | Action |
| --- | --- |
| `bs` | Show current status and a list of examples |
| `bs 40` | Set master brightness to 40% (0-100) |
| `bs up [step]` / `bs down [step]` | Step brightness (default 10, range 1-100) |
| `bs auto on` / `bs auto off` | Automatic brightness |
| `bs eye on [hours]` / `bs eye off` | Eye protection, optional duration 1-24 h |
| `bs boost on [hours]` / `bs boost off` | Brightness boost, optional duration 1-24 h |
| `bs refresh` | Re-detect monitors |
| `bs settings` | Open BrightSync settings |
| `bs status` | Show status |

When automatic brightness is on, manual brightness commands are blocked by
BrightSync (exit code 4). The plugin shows that message as-is.

## How it connects

1. Reads `%LocalAppData%\BrightSync\command-server.json` (`BaseUrl`, `BearerToken`).
2. Sends `POST /v1/commands` with `Authorization: Bearer <token>` and a PascalCase
   `CommandRequest` body. Enums are sent as integers.
3. If the file is missing, the port refuses, or the server returns 404, the plugin
   reports "BrightSync is not running". It never starts BrightSync.

The token is only sent to a plain `http://127.0.0.1` or `http://localhost` base URL.
Any other base URL in the metadata file is refused.

## Layout

```
BrightSync/
  plugin.json          Flow Launcher manifest (ActionKeyword: bs)
  main.py              Flow JSON-RPC entry point (query, run_command, noop)
  query_parser.py      Query text -> command
  brightsync_client.py HTTP client for the command API
  icon.png             Copy of src/Resources/app.png
  tests/               unittest suites (parser, client against a fake server, plugin)
```

## Tests

From this folder:

```
python -m unittest discover -s tests -p "test_*.py"
```

The client tests start a fake BrightSync server on a random local port. Nothing
here touches the real app or the live Flow Launcher plugin folder.

## Install (manual, not done by the build)

Copy the `BrightSync` folder to
`%AppData%\FlowLauncher\Plugins\` and restart Flow Launcher.

## Keep in sync with BrightSync

`AppCommandType` values are copied into `brightsync_client.py`
(`CommandType`). If the C# enum is reordered or extended, update this file.
The request body and exit codes come from `src/Cli/` in the BrightSync repo.
