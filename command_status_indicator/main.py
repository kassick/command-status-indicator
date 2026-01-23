import argparse
from dataclasses import dataclass
from datetime import datetime
from functools import cached_property
import json
import logging
import subprocess
from typing import Optional, TypeAlias
from pydantic import BaseModel
import yaml
import gi

logger = logging.getLogger(__name__)
gi.require_version("Gtk", "3.0")
gi.require_version("AppIndicator3", "0.1")
from gi.repository import GLib, Gtk, AppIndicator3 as appindicator  # type: ignore  # noqa: E402


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


def load_config(config_file: str) -> Config:
    """Load configuration from a YAML file."""
    with open(config_file, "r") as f:
        config_data = yaml.safe_load(f)
    return Config.model_validate(config_data)


def run_cmd(cmd: str, status_key: str) -> CmdStatus | None:
    """Runs a shell command and returns its output as a string."""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error(f"Command {cmd} returned {result.returncode}:")
        logger.error(result.stdout)
        logger.error(result.stderr)

        return None

    stdout = result.stdout.strip()
    try:
        result_dict = json.loads(stdout)
        return result_dict.get(status_key)
    except ValueError as err:
        logger.error(f"Error decoding JSON output: {err}")
        return None


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
):
    """Resets the indicator to a default state."""
    menu = Gtk.Menu()
    if fallback and state.config.fallback_status:
        state.indicator.set_icon_full(
            state.config.fallback_status.icon,
            state.config.fallback_status.alt_text or "No Status",
        )
        display_label = state.config.fallback_status.text or label
        state.indicator.set_label(display_label, state.config.computed_label_guide)
        for item in state.config.fallback_status.menu_items:
            menu_item = Gtk.MenuItem.new_with_label(item.label)
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
            working_label = state.indicator.get_label() + "..."
            state.indicator.set_label(working_label, state.config.computed_label_guide)
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
    logger.debug("Updating Indicator fn at %s", datetime.now())
    status = run_cmd(state.config.cmd, state.config.status_key)
    logger.debug("Status returned %s", status)
    if status is None:
        reset_indicator(state, label="Cmd Err!", icon_name="dialog-error-symbolic")
        return True

    if (entry := state.config.statuses.get(status)) is None:
        logger.warning(f"No configuration for status '{status}'")
        reset_indicator(
            state, label="Unknown!", icon_name="dialog-error-symbolic", fallback=True
        )
        return True

    icon = entry.icon
    alt_text = entry.alt_text or ""
    text = entry.text

    state.indicator.set_icon_full(icon, alt_text)
    if text:
        state.indicator.set_label(text, state.config.computed_label_guide)
    else:
        state.indicator.set_label("", state.config.computed_label_guide)

    menu = Gtk.Menu()
    for item in entry.menu_items:
        menu_item = Gtk.MenuItem.new_with_label(item.label)
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
