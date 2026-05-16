# Active Tracker Browser Bridge

Streams the active browser tab URL and title to the local Rust agent over `ws://127.0.0.1:5006`.

## Token

Start the Rust agent first, then read:

```bash
cat ~/.active_tracker/token
```

Paste that token into the extension popup.

## Install

Chrome / Edge / Brave / Arc:

1. Open `chrome://extensions` or the equivalent extensions page.
2. Enable developer mode.
3. Load this `browser_extension/` directory as an unpacked extension.
4. Open the extension popup, paste the token, and save.

Firefox temporary install:

1. Open `about:debugging#/runtime/this-firefox`.
2. Load `manifest.json` as a temporary add-on.
3. Configure the token from the popup.

The extension only reads the active tab URL/title and sends it to `127.0.0.1`.
