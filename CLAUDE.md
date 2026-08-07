# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Run

This project uses **uv** as its Python package manager. Python >= 3.13 required.

```bash
uv sync                       # Install dependencies (prod + dev)
uv run command-status-indicator -c <config.yaml>   # Run the indicator
uv run command-status-indicator -c <config.yaml> -v # Run with debug logging
```

There is no test suite or linter configured. The `dev` dependency group only includes `pygobject-stubs` for type checking.

## Architecture

A lightweight system tray / menu bar indicator that periodically runs a user-configured shell command, parses its JSON output, and updates the tray icon, label, and context menu accordingly.

**Entry point:** `command_status_indicator/__init__.py` → `command_status_indicator/main.py:main()`.

**Package entry point** (declared in `pyproject.toml`): `command-status-indicator` maps to `command_status_indicator:main`.

**Single file architecture** — all logic lives in `main.py`. There is no separation into modules.

## Cross-Platform Strategy

**Two backends** share the same config models, template rendering, and command execution. Platform detection at import time (`sys.platform == "darwin"`) selects the active backend:

| | Linux (GTK) | macOS (rumps) |
|---|---|---|
| **Imports** | `gi` (Gtk 3.0, AppIndicator3 0.1) | `rumps` (≥0.4.0), `PyObjCTools.AppHelper` |
| **Dependency group** | `linux = ["PyGObject>=3.40"]` | `osx = ["rumps>=0.4.0"]` |
| **Event loop** | `Gtk.main()` / `Gtk.main_quit()` | `AppHelper.runEventLoop()` / `rumps.quit_application()` |
| **Periodic timer** | `GLib.timeout_add(ms, callback, state)` | `rumps.Timer(callback, interval)` — NSTimer on Cocoa run loop |
| **Debounce** | `GLib.timeout_add(ms, callback, state)`, with `GLib.source_remove` to cancel | `AppHelper.callLater(delay, func, *args)` — one-shot main-thread dispatch |
| **Menu build** | `Gtk.Menu` + `Gtk.MenuItem` | `rumps.MenuItem` list assigned to `app.menu` |
| **State** | `@dataclass State` — config, indicator, timer ID, last JSON | `@dataclass State` — config, app, refresh_timer, last JSON, `debouncing` flag |

Both backends are defined in the same file (`main.py`), gated by `if IS_MACOS:` / `else:`. The `main()` function dispatches to `create_rumps_app(config)` on macOS or `run_gtk_indicator(config)` on Linux.

### Data Flow

1. **Config loading** (`load_config`): YAML file → pydantic `Config` model. The config defines the shell command (`cmd`), polling interval (`refresh`), status-to-icon/menu mappings (`statuses`), and an optional `fallback_status`.
2. **Polling loop** (`update_indicator` / `update_indicator_rumps`): Platform-specific timer fires every `refresh` seconds, runs the shell command via `subprocess.run`, parses JSON stdout looking for the `status_key` field.
3. **Status resolution**: The returned status string is looked up in `Config.statuses` dict. If found, the corresponding `ConfigEntry` (icon, text, menu_items) is applied. If not found, `fallback_status` is used (if configured), otherwise a generic "Unknown!" error state.
4. **Menu actions**: Menu item clicks run the associated shell command, then force a refresh. If `debounce_refresh_on_command > 0`, the refresh is delayed by that many seconds (with visual feedback — ATTENTION indicator on Linux, loading icon on macOS).

### Key Models (pydantic)

- **`MenuItem`**: label + events dict (GTK signal name or `activate` → shell command string).
- **`ConfigEntry`**: icon, optional text/alt_text, list of `MenuItem`.
- **`Config`**: indicator_id, cmd, status_key (default "status"), refresh interval (seconds), debounce_refresh_on_command (seconds), statuses dict (`str → ConfigEntry`), optional fallback_status, optional `extra_paths` (added to PATH).

### State

Two platform-specific `@dataclass` `State` classes defined inside the `if IS_MACOS:` / `else:` blocks. Both hold the parsed `Config` and last JSON response. There is no global mutable state.

**GTK/Linux State:** `config`, `indicator` (AppIndicator3), `timer` (GLib timer ID), `last_json_data`.

**macOS/rumps State:** `config`, `app` (rumps.App), `refresh_timer` (rumps.Timer), `last_json_data`, `debouncing` (bool flag to prevent duplicate debounce callbacks).

### GTK/Linux Implementation

- Requires `Gtk` 3.0 and `AppIndicator3` 0.1.
- Uses `GLib.timeout_add` for periodic refresh and debounced updates.
- Timer IDs are tracked in `State.timer` so they can be cancelled (`GLib.source_remove`) before debouncing or quitting.
- `Gtk.main()` is the blocking event loop; `Gtk.main_quit()` stops it.
- Debounce visual feedback uses `appindicator.IndicatorStatus.ATTENTION` (only shown when debounce ≥ 100ms).
- Menu is rebuilt from scratch on each update: a new `Gtk.Menu` is created, populated with config menu items, a Quit entry is appended, and `indicator.set_menu(menu)` is called.

### macOS/rumps Implementation

- Requires `rumps` ≥0.4.0 and `PyObjCTools.AppHelper` (bundled with PyObjC).
- **Periodic refresh** uses `rumps.Timer`, which wraps `NSTimer` on the Cocoa main run loop (`repeats=True`). Callbacks run on the main thread, so NSMenu modifications are safe.
- **Debounce** uses `AppHelper.callLater(delay, func, *args)` — a one-shot main-thread dispatch that fires `func` on the main run loop after `delay` seconds. This is the correct way to defer a callback on macOS with PyObjC.
- **No restart of rumps.Timer**: When the refresh timer is stopped for debounce, a new `rumps.Timer` instance is created and started from `_debounce_done` (which runs on the main thread). This avoids the rumps.Timer `stop()`/`start()` issue (broken from background threads).
- **`debouncing` flag** on State prevents clicks from queuing multiple `AppHelper.callLater` callbacks during an active debounce period.
- **Menu rebuild** (`_rebuild_rumps_menu`): Clears `app.menu` with `.clear()`, then sets it to a new list of `rumps.MenuItem` objects. A Quit entry (calling `rumps.quit_application()`) is always appended. `quit_button=None` is set on the `rumps.App` to disable the framework's default Quit button.
- **macOS autoload** (`_run_autoload`): When no `-c` flag is given on macOS, the app scans `~/.config/command-status-indicator/*.{yaml,yml}` and spawns one subprocess per config file. Each child runs independently; the parent manages their lifecycle via SIGTERM/SIGINT handlers.
- **Thread safety is critical**: All NSMenu modifications must happen on the main thread. `threading.Timer` was previously used but caused intermittent duplicate Quit buttons due to background-thread NSMenu access. The switch to `rumps.Timer` + `AppHelper.callLater` ensures all UI work stays on the main Cocoa run loop.
