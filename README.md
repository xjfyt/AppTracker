# Active Tracker

Rust/Tauri version of Active Tracker. The real core is a headless Rust agent; the Tauri app is only a page that consumes the local API.

## One-command workflow

Run these commands from the project root.

```powershell
# Start the Tauri UI. The embedded Rust agent starts with it.
npm run dev

# Start only the headless agent, for sidecar integration.
npm run agent

# Build the release headless agent and the Tauri app in one command.
npm run package

# Format/check/test Rust code.
npm run check
```

The first `npm run dev` or `npm run package` automatically installs the Tauri npm dependency under `desktop/`.

## Build outputs

```text
target/release/active-tracker-agent.exe
target/release/active-tracker-tauri.exe
```

On macOS/Linux the executable suffix differs, but the same commands apply.

## API

Default listeners:

- API: `http://127.0.0.1:5007`
- Browser bridge: `ws://127.0.0.1:5006`

Routes:

- `GET /api/v1/health`
- `GET /api/v1/snapshot`
- `GET /api/v1/screenshot`
- `GET /api/v1/events`
- `GET /api/v1/ws`
- `GET/POST /api/v1/pause`

The browser extension still uses `~/.active_tracker/token` for authentication.

## Platform capabilities

- Windows: Win32 foreground window, process info, cmdline/cwd document detection, Office/WPS COM document detection, UI Automation document detection, Explorer COM, terminal process tree, shell cwd files, screenshots, keyboard/mouse activity.
- macOS: System Events / AppleScript foreground window, Finder AppleScript, process tree, shell cwd files, screenshots, keyboard/mouse activity. Requires Accessibility / Input Monitoring / Automation permissions.
- Linux: X11 uses `xdotool` / `xprop` / `xwininfo`; file manager support is cwd/title best-effort. Wayland is limited by the desktop security model.

## Integration advice

For another product, prefer launching `tracker-agent` as a sidecar process and consuming the local HTTP/SSE/WebSocket API. This keeps platform permissions and capture failures isolated from the host app.

