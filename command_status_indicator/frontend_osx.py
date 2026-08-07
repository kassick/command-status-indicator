"""macOS / rumps frontend for the command-status-indicator."""

from dataclasses import dataclass
import logging
import subprocess
from typing import Optional

import rumps
from PyObjCTools import AppHelper

from command_status_indicator.config import (
    Config,
    ConfigEntry,
    _build_env,
    get_icon_path,
    render_template,
    run_cmd,
)

logger = logging.getLogger(__name__)

@dataclass
class State:
    config: Config
    app: "rumps.App"
    refresh_timer: Optional["rumps.Timer"] = None
    last_json_data: dict | None = None
    debouncing: bool = False


# ---------------------------------------------------------------------------
# Menu helpers
# ---------------------------------------------------------------------------

def _quit_rumps(sender):
    """Quit the rumps app."""
    rumps.quit_application()


def _rebuild_rumps_menu(
    state: State,
    app: "rumps.App",
    entry: Optional[ConfigEntry],
    json_data: Optional[dict] = None,
):
    """Rebuild the rumps menu from the entry."""
    menu_items = []

    context = json_data or state.last_json_data or {}

    if entry:
        for item in entry.menu_items:
            rendered_label = render_template(item.label, context)
            # For now, rumps menus support only the 'activate' event
            # Get the first command from events (typically 'activate')
            cmd = list(item.events.values())[0] if item.events else None
            if cmd:
                menu_items.append(
                    rumps.MenuItem(
                        rendered_label,
                        callback=lambda _, cmd=cmd: _handle_menu_click(state, app, cmd),
                    )
                )

    # Add separator and Quit
    if menu_items:
        menu_items.append(None)  # Separator in rumps
    menu_items.append(rumps.MenuItem("Quit", callback=_quit_rumps))

    # Clear the existing menu before rebuilding to avoid duplicate items.
    app.menu.clear()
    app.menu = menu_items


# ---------------------------------------------------------------------------
# Indicator update logic
# ---------------------------------------------------------------------------

def _apply_fallback_status(state: State, app: "rumps.App", json_data: dict):
    """Apply fallback status configuration."""
    fb = state.config.fallback_status
    icon = fb.icon
    text = render_template(fb.text, json_data) if fb.text else ""

    app.icon = get_icon_path(icon)
    app.title = text.strip()
    _rebuild_rumps_menu(state, app, fb, json_data)


def update_indicator_rumps(state: State, app: "rumps.App"):
    """Updates the rumps indicator based on the command output."""
    import datetime as _dt

    logger.debug("Updating Indicator fn at %s", _dt.datetime.now())
    json_data = run_cmd(state.config.cmd, state.config.extra_paths)
    logger.debug("Status command result: %s", json_data)

    state.last_json_data = json_data

    # Handle command failure
    if json_data is None:
        app.icon = get_icon_path("dialog-error-symbolic")
        app.title = "Cmd Err!"
        _rebuild_rumps_menu(state, app, None)
        return

    status = json_data.get(state.config.status_key)

    logger.debug("Status returned %s", status)
    # Handle missing status key
    if status is None:
        logger.warning(
            "No status key '%s' in command output", state.config.status_key
        )
        if state.config.fallback_status:
            _apply_fallback_status(state, app, json_data)
        else:
            app.icon = get_icon_path("dialog-error-symbolic")
            app.title = "Unknown!"
            _rebuild_rumps_menu(state, app, None)
        return

    # Handle unknown status
    if (entry := state.config.statuses.get(status)) is None:
        logger.warning(f"No configuration for status '{status}'")
        if state.config.fallback_status:
            _apply_fallback_status(state, app, json_data)
        else:
            app.icon = get_icon_path("dialog-error-symbolic")
            app.title = "Unknown!"
            _rebuild_rumps_menu(state, app, None)
        return

    # Apply the configured status entry
    icon = entry.icon
    text = render_template(entry.text, json_data) if entry.text else ""

    app.icon = get_icon_path(icon)
    app.title = text.strip()
    _rebuild_rumps_menu(state, app, entry, json_data)


# ---------------------------------------------------------------------------
# Menu click handling & debounce
# ---------------------------------------------------------------------------

def _handle_menu_click(state: State, app: "rumps.App", cmd: str):
    """Handle a menu item click."""
    # Show ellipsis icon for visual feedback (rumps has no ATTENTION status)
    app.icon = get_icon_path("content-loading-symbolic")

    # Run the action command
    env = _build_env(state.config.extra_paths)
    result = subprocess.run(cmd, shell=True, env=env)
    if result.returncode != 0:
        logger.error("Error executing menu item command")
        return

    # Stop the current periodic refresh timer
    if state.refresh_timer:
        state.refresh_timer.stop()
        state.refresh_timer = None

    if state.config.debounce_refresh_on_command > 0:
        debounce_s = state.config.debounce_refresh_on_command
        logger.debug("Debouncing update for %d s due to command", debounce_s)

        # Ignore clicks during debounce period
        if state.debouncing:
            logger.debug("Already debouncing, ignoring click")
            return
        state.debouncing = True

        # Schedule the debounce-done callback on the main run loop
        # after the delay. Safe for NSMenu modifications.
        AppHelper.callLater(debounce_s, _debounce_done, state, app)
    else:
        logger.debug("Forcing update of indicator due to command")
        update_indicator_rumps(state, app)
        # Start the periodic refresh timer again
        state.refresh_timer = rumps.Timer(
            callback=lambda t: _scheduled_refresh(state, app),
            interval=state.config.refresh,
        )
        state.refresh_timer.start()


def _scheduled_refresh(state: State, app: "rumps.App"):
    """Called when the periodic refresh timer expires. Updates the indicator.
    The rumps.Timer repeats automatically — no need to recreate it."""
    update_indicator_rumps(state, app)


def _debounce_done(state: State, app: "rumps.App"):
    """Called on the main thread after the debounce delay expires.
    Updates the indicator and restarts the periodic refresh timer."""
    state.debouncing = False

    update_indicator_rumps(state, app)
    logger.debug(
        "Debounce done, resuming periodic refresh every %ds", state.config.refresh
    )
    # Start the periodic refresh timer again
    state.refresh_timer = rumps.Timer(
        callback=lambda t: _scheduled_refresh(state, app),
        interval=state.config.refresh,
    )
    state.refresh_timer.start()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def create_rumps_app(config: Config, log_level: int = logging.INFO) -> "rumps.App":
    """Create a rumps.App with the given configuration."""
    logger.setLevel(log_level)
    app = rumps.App(
        config.indicator_id,
        icon=get_icon_path("image-loading-symbolic"),
        quit_button=None,  # We'll add quit manually
    )

    state = State(config=config, app=app)
    app.state = state  # Store state on the app instance

    # Set up the periodic refresh timer using rumps.Timer, which runs on the
    # main Cocoa run loop and is safe for modifying AppKit objects (menus).
    # We create new timer instances (instead of stopping/restarting) when
    # debouncing — this is safe when done from main-thread callbacks.
    logger.info(f"Refreshing state every {config.refresh}s")
    state.refresh_timer = rumps.Timer(
        callback=lambda t: _scheduled_refresh(state, app),
        interval=config.refresh,
    )
    state.refresh_timer.start()

    # Initial update (also builds the initial menu via _rebuild_rumps_menu)
    logger.info("Initial Command Status Update")
    update_indicator_rumps(state, app)

    logger.info("Startup complete")

    return app
