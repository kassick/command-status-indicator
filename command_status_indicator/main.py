import argparse
from dataclasses import dataclass
import datetime as _dt_module
from functools import cached_property
import json
import logging
import subprocess
from typing import Optional, TypeAlias
import humanize
from jinja2.sandbox import SandboxedEnvironment
from pydantic import BaseModel
import yaml
import gi

logger = logging.getLogger(__name__)
gi.require_version("Gtk", "3.0")
gi.require_version("AppIndicator3", "0.1")
from gi.repository import GLib, Gtk, AppIndicator3 as appindicator  # type: ignore  # noqa: E402

_jinja_env = SandboxedEnvironment()
_jinja_env.globals["datetime"] = _dt_module
_jinja_env.globals["humanize"] = humanize
_jinja_env.globals["str"] = str


def render_template(template: str, context: dict) -> str:
    """Render a Jinja2 template string against the given context dict.

    Context keys are available as top-level variables in the template.
    Returns the raw template string on any render error (safe fallback).
    """
    try:
        return _jinja_env.from_string(template).render(**context)
    except Exception:
        logger.exception("Template render error for '%s'", template)
        return template


class MenuItem(BaseModel):
    label: str
    events: dict[str, str]  # signal -> cmd


class ConfigEntry(BaseModel):
    icon: str
    text: Optional[str] = None
    alt_text: Optional[str] = None
    menu_items: list[MenuItem]


CmdStatus: TypeAlias = str


class Config(BaseModel):
    indicator_id: str
    cmd: str
    status_key: str = "status"
    label_guide: Optional[str] = None
    refresh: int = 30
    debounce_refresh_on_command: int = 0
    statuses: dict[CmdStatus, ConfigEntry]
    fallback_status: ConfigEntry | None = None

    def refresh_interval_ms(self) -> int:
        """Convert refresh interval to milliseconds."""
        return self.refresh * 1000

    def debounce_refresh_on_command_ms(self) -> int:
        """Convert debounce interval to milliseconds."""
        return self.debounce_refresh_on_command * 1000

    @cached_property
    def computed_label_guide(self) -> str:
        if self.label_guide:
            return self.label_guide

        longest_text = max(
            (status.text or "" for status in self.statuses.values()),
            key=lambda t: len(t),
        )
        return longest_text


@dataclass
class State:
    config: Config
    indicator: appindicator.Indicator
    timer: int | None = None
    last_json_data: dict | None = None


def load_config(config_file: str) -> Config:
    """Load configuration from a YAML file."""
    with open(config_file, "r") as f:
        config_data = yaml.safe_load(f)
    return Config.model_validate(config_data)


def run_cmd(cmd: str) -> dict | None:
    """Runs a shell command and returns its JSON output as a dict.

    Returns None if the command fails or the output is not valid JSON.
    """
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error(f"Command {cmd} returned {result.returncode}:")
        logger.error(result.stdout)
        logger.error(result.stderr)
        return None

    stdout = result.stdout.strip()
    try:
        data = json.loads(stdout)
    except ValueError as err:
        logger.error(f"Error decoding JSON output: {err}")
        return None

    if not isinstance(data, dict):
        logger.error(f"Command output is not a JSON object: {type(data).__name__}")
        return None

    return data


def add_quit_menu_item(menu: Gtk.Menu):
    """Adds a Quit menu item to the given menu."""
    quit_menu_item = Gtk.MenuItem.new_with_label("Quit")
    quit_menu_item.connect("activate", quit_app)
    menu.append(quit_menu_item)

    return menu


def reset_indicator(
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
        state.indicator.set_icon_full(fb.icon, alt_text)
        display_label = render_template(fb.text, context) if fb.text else label
        state.indicator.set_label(display_label, state.config.computed_label_guide)
        for item in fb.menu_items:
            rendered_label = render_template(item.label, context)
            menu_item = Gtk.MenuItem.new_with_label(rendered_label)
            for signal, cmd in item.events.items():
                menu_item.connect(signal, handle_menu_item, cmd, state)
            menu.append(menu_item)
    else:
        state.indicator.set_icon_full(icon_name, "No status")
        state.indicator.set_label(label, state.config.computed_label_guide)

    menu = add_quit_menu_item(menu)
    menu.show_all()
    state.indicator.set_menu(menu)

    return menu


def debounced_update_and_reschedule(state: State) -> bool:
    """Updates the indicator and schedules the next regular update."""
    update_indicator(state)
    state.timer = GLib.timeout_add(
        state.config.refresh_interval_ms(), update_indicator, state
    )
    return False


def handle_menu_item(item, cmd, state: State):
    """Runs the action associated with a menu item and re-runs the state command"""

    # The action command can do whatever, so we do not care about its output
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
        logger.error("Error executing menu item command")
        return

    # Reset the timer and schedule update
    if state.timer is not None:
        GLib.source_remove(state.timer)

    if state.config.debounce_refresh_on_command > 0:
        debounce_ms = state.config.debounce_refresh_on_command_ms()
        logger.debug("Debouncing update for %d ms due to command", debounce_ms)
        # Show ellipsis feedback if debounce is >= 100ms
        if debounce_ms >= 100:
            state.indicator.set_status(appindicator.IndicatorStatus.ATTENTION)
        state.timer = GLib.timeout_add(
            debounce_ms, debounced_update_and_reschedule, state
        )
    else:
        logger.debug("Forcing update of indicator due to command")
        update_indicator(state)
        state.timer = GLib.timeout_add(
            state.config.refresh_interval_ms(), update_indicator, state
        )


def update_indicator(state: State) -> bool:
    """Updates the indicator based on the command output."""
    logger.debug("Updating Indicator fn at %s", _dt_module.datetime.now())
    json_data = run_cmd(state.config.cmd)
    logger.debug("Status command result: %s", json_data)

    if json_data is None:
        reset_indicator(state, label="Cmd Err!", icon_name="dialog-error-symbolic")
        return True

    state.last_json_data = json_data
    status = json_data.get(state.config.status_key)

    logger.debug("Status returned %s", status)
    if status is None:
        logger.warning("No status key '%s' in command output", state.config.status_key)
        reset_indicator(
            state,
            label="Unknown!",
            icon_name="dialog-error-symbolic",
            fallback=True,
            json_data=json_data,
        )
        return True

    if (entry := state.config.statuses.get(status)) is None:
        logger.warning(f"No configuration for status '{status}'")
        reset_indicator(
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
    state.indicator.set_icon_full(icon, alt_text.strip())
    state.indicator.set_label(text.strip(), state.config.computed_label_guide)

    menu = Gtk.Menu()
    for item in entry.menu_items:
        rendered_label = render_template(item.label, json_data)
        menu_item = Gtk.MenuItem.new_with_label(rendered_label)
        for signal, cmd in item.events.items():
            menu_item.connect(signal, handle_menu_item, cmd, state)
        menu.append(menu_item)

    menu = add_quit_menu_item(menu)
    menu.show_all()

    state.indicator.set_menu(menu)

    return True


def quit_app(widget, *args, **kwargs):
    """Callback function to quit the application."""
    Gtk.main_quit()


def main():
    """Main function to set up the indicator."""
    parser = argparse.ArgumentParser(description="Command Status Indicator")
    parser.add_argument("-c", "--config", required=True, help="Configuration file")
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging"
    )
    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    try:
        config = load_config(args.config)
    except FileNotFoundError:
        logger.error(f"Configuration file '{args.config}' not found")
        return
    except Exception as e:
        logger.error(f"Error loading configuration: {e}")
        return

    logger.info(f"Showing indicator {config.indicator_id} for command {config.cmd}")
    logger.info(f"Mapped States: {', '.join(config.statuses.keys())}")

    indicator = appindicator.Indicator.new(
        config.indicator_id,
        "image-loading-symbolic",
        appindicator.IndicatorCategory.SYSTEM_SERVICES,
    )

    state = State(config=config, indicator=indicator)

    indicator.set_status(appindicator.IndicatorStatus.ACTIVE)
    update_indicator(state)

    # Add a timer to call update_indicator every refresh seconds
    state.timer = GLib.timeout_add(
        config.refresh_interval_ms(), update_indicator, state
    )

    Gtk.main()


if __name__ == "__main__":
    main()
