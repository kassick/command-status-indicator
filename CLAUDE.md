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

A lightweight GTK3 system tray indicator that periodically runs a user-configured shell command, parses its JSON output, and updates the tray icon, label, and context menu accordingly.

**Entry point:** `command_status_indicator/__init__.py` → `command_status_indicator/main.py:main()`.

**Package entry point** (declared in `pyproject.toml`): `command-status-indicator` maps to `command_status_indicator:main`.

**Single file architecture** — all logic lives in `main.py` (~270 lines). There is no separation into modules.

### Data Flow

1. **Config loading** (`load_config`): YAML file → pydantic `Config` model. The config defines the shell command (`cmd`), polling interval (`refresh`), status-to-icon/menu mappings (`statuses`), and an optional `fallback_status`.
2. **Polling loop** (`update_indicator`): GLib timer fires every `refresh` seconds, runs the shell command via `subprocess.run`, parses JSON stdout looking for the `status_key` field.
3. **Status resolution**: The returned status string is looked up in `Config.statuses` dict. If found, the corresponding `ConfigEntry` (icon, text, menu_items) is applied. If not found, `fallback_status` is used (if configured), otherwise a generic "Unknown!" error state.
4. **Menu actions** (`handle_menu_item`): Menu item clicks run the associated shell command, then force a refresh. If `debounce_refresh_on_command > 0`, the refresh is delayed by that many seconds (with an ATTENTION indicator state as visual feedback).

### Key Models (pydantic)

- **`MenuItem`**: label + events dict (GTK signal name → shell command string).
- **`ConfigEntry`**: icon, optional text/alt_text, list of `MenuItem`.
- **`Config`**: indicator_id, cmd, status_key (default "status"), refresh interval (seconds), debounce_refresh_on_command (seconds), statuses dict (`str → ConfigEntry`), optional fallback_status.

### State

A `@dataclass` `State` holds the parsed `Config`, the `appindicator.Indicator` instance, and the current GLib timer ID. It's passed through GTK callbacks as user data — there is no global mutable state.

### GTK/GLib details

- Requires `Gtk` 3.0 and `AppIndicator3` 0.1.
- Uses `GLib.timeout_add` for periodic refresh and debounced updates.
- Timer IDs are tracked in `State.timer` so they can be cancelled (`GLib.source_remove`) before debouncing or quitting.
- `Gtk.main()` is the blocking event loop; `Gtk.main_quit()` stops it.
- debounce visual feedback uses `appindicator.IndicatorStatus.ATTENTION` (only shown when debounce ≥ 100ms).
