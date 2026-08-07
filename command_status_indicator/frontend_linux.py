"""Linux GTK / AppIndicator3 frontend for the command-status-indicator."""

from dataclasses import dataclass
import logging
import subprocess

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("AppIndicator3", "0.1")
from gi.repository import GLib, Gtk, AppIndicator3 as appindicator  # type: ignore  # noqa: E402

from command_status_indicator.config import (
    Config,
    _build_env,
    get_icon_path,
    render_template,
    run_cmd,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


@dataclass
class State:
    config: Config
    indicator: appindicator.Indicator
    timer: int | None = None
    last_json_data: dict | None = None


# ---------------------------------------------------------------------------
# Menu helpers
# ---------------------------------------------------------------------------

def _add_quit_menu_item(menu: Gtk.Menu):
    """Adds a Quit menu item to the given menu."""
    quit_menu_item = Gtk.MenuItem.new_with_label("Quit")
    quit_menu_item.connect("activate", _quit_app)
    menu.append(quit_menu_item)
    return menu


def _quit_app(widget, *args, **kwargs):
    """Callback function to quit the application."""
    Gtk.main_quit()


# ---------------------------------------------------------------------------
# Indicator update logic
# ---------------------------------------------------------------------------

def _reset_indicator(
    state: State,
    icon_name="image-missing-symbolic",
    label="...",
    fallback=False,
    json_data: dict | None = None,
):
    """Resets the indicator to a default state."""
    context = json_data or state.last_json_data or {}

    menu = Gtk.Menu()
    if fallback and state.config.fallback_status:
        fb = state.config.fallback_status
        alt_text = render_template(fb.alt_text, context) if fb.alt_text else "No Status"
        if fb.icon:
            state.indicator.set_icon_full(fb.icon, alt_text)
        display_label = render_template(fb.text, context) if fb.text else label
        state.indicator.set_label(display_label, state.config.computed_label_guide)
        for item in fb.menu_items:
            rendered_label = render_template(item.label, context)
            menu_item = Gtk.MenuItem.new_with_label(rendered_label)
            for signal, cmd in item.events.items():
                menu_item.connect(signal, _handle_menu_item, cmd, state)
            menu.append(menu_item)
    else:
        state.indicator.set_icon_full(icon_name, "No status")
        state.indicator.set_label(label, state.config.computed_label_guide)

    menu = _add_quit_menu_item(menu)
    menu.show_all()
    state.indicator.set_menu(menu)

    return menu


def _debounced_update_and_reschedule(state: State) -> bool:
    """Updates the indicator and schedules the next regular update."""
    _update_indicator(state)
    state.timer = GLib.timeout_add(
        state.config.refresh_interval_ms(), _update_indicator, state
    )
    return False


def _handle_menu_item(item, cmd, state: State):
    """Runs the action associated with a menu item and re-runs the state command"""

    # The action command can do whatever, so we do not care about its output
    env = _build_env(state.config.extra_paths)
    result = subprocess.run(cmd, shell=True, env=env)
    if result.returncode != 0:
        logger.error("Error executing menu item command")
        return

    # Reset the timer and schedule update
    if state.timer is not None:
        GLib.source_remove(state.timer)

    if state.config.debounce_refresh_on_command > 0:
        debounce_ms = state.config.debounce_refresh_on_command_ms()
        logger.debug("Debouncing update for %d ms due to command", debounce_ms)
        # Show attention feedback if debounce is >= 100ms
        if debounce_ms >= 100:
            state.indicator.set_status(appindicator.IndicatorStatus.ATTENTION)
        state.timer = GLib.timeout_add(
            debounce_ms, _debounced_update_and_reschedule, state
        )
    else:
        logger.debug("Forcing update of indicator due to command")
        _update_indicator(state)
        state.timer = GLib.timeout_add(
            state.config.refresh_interval_ms(), _update_indicator, state
        )


def _update_indicator(state: State) -> bool:
    """Updates the indicator based on the command output."""
    import datetime as _dt

    logger.debug("Updating Indicator fn at %s", _dt.datetime.now())
    json_data = run_cmd(state.config.cmd, state.config.extra_paths)
    logger.debug("Status command result: %s", json_data)

    if json_data is None:
        _reset_indicator(state, label="Cmd Err!", icon_name="dialog-error-symbolic")
        return True

    state.last_json_data = json_data
    status = json_data.get(state.config.status_key)

    logger.debug("Status returned %s", status)
    if status is None:
        logger.warning("No status key '%s' in command output", state.config.status_key)
        _reset_indicator(
            state,
            label="Unknown!",
            icon_name="dialog-error-symbolic",
            fallback=True,
            json_data=json_data,
        )
        return True

    if (entry := state.config.statuses.get(status)) is None:
        logger.warning(f"No configuration for status '{status}'")
        _reset_indicator(
            state,
            label="Unknown!",
            icon_name="dialog-error-symbolic",
            fallback=True,
            json_data=json_data,
        )
        return True

    icon = entry.icon
    alt_text = render_template(entry.alt_text, json_data) if entry.alt_text else ""
    text = render_template(entry.text, json_data) if entry.text else ""

    state.indicator.set_status(appindicator.IndicatorStatus.ACTIVE)
    if icon:
        state.indicator.set_icon_full(icon, alt_text.strip())
    state.indicator.set_label(text.strip(), state.config.computed_label_guide)

    menu = Gtk.Menu()
    for item in entry.menu_items:
        rendered_label = render_template(item.label, json_data)
        menu_item = Gtk.MenuItem.new_with_label(rendered_label)
        for signal, cmd in item.events.items():
            menu_item.connect(signal, _handle_menu_item, cmd, state)
        menu.append(menu_item)

    menu = _add_quit_menu_item(menu)
    menu.show_all()

    state.indicator.set_menu(menu)

    return True


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_gtk_indicator(config: Config):
    """Run the GTK/AppIndicator version on Linux."""
    indicator = appindicator.Indicator.new(
        config.indicator_id,
        get_icon_path("image-loading-symbolic"),
        appindicator.IndicatorCategory.SYSTEM_SERVICES,
    )

    state = State(config=config, indicator=indicator)

    indicator.set_status(appindicator.IndicatorStatus.ACTIVE)
    _update_indicator(state)

    # Add a timer to call _update_indicator every refresh seconds
    state.timer = GLib.timeout_add(
        config.refresh_interval_ms(), _update_indicator, state
    )

    Gtk.main()
