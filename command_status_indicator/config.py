import datetime as _dt_module
from functools import cached_property
import json
import logging
import os
import subprocess
import sys
from typing import Optional, TypeAlias
from pathlib import Path

import humanize
from jinja2.sandbox import SandboxedEnvironment
from pydantic import BaseModel
import yaml
from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# ---------------------------------------------------------------------------
# Jinja2 template rendering
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Configuration models
# ---------------------------------------------------------------------------

class MenuItem(BaseModel):
    label: str
    events: dict[str, str]  # signal -> cmd


class ConfigEntry(BaseModel):
    icon: Optional[str] = None
    text: Optional[str] = None
    alt_text: Optional[str] = None
    menu_items: list[MenuItem] = []


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
    extra_paths: list[str] = []

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


# ---------------------------------------------------------------------------
# Icon resolution utilities
# ---------------------------------------------------------------------------

def get_resource_dir() -> Path:
    """Return the directory containing bundled resources.

    Works both in normal Python runs and in PyInstaller-frozen apps.
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "command_status_indicator"
    return Path(__file__).parent


def get_cache_dir() -> Path:
    """Get or create the cache directory for icons."""
    cache_dir = Path.home() / ".cache" / "command-status-indicator" / "icons"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def generate_default_icon(icon_name: str, size: int = 64) -> Image.Image:
    """Generate a simple default icon (black square with white text)."""
    img = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    # Draw a simple black square with a small border
    draw.rectangle([4, 4, size - 4, size - 4], outline="black", width=2)
    return img


def get_icon_path(icon_name: str) -> str:
    """Resolve a GTK icon name or image path to an image file path.
    Falls back to a generated default icon if nothing is found."""
    # 1. Try absolute path
    if Path(icon_name).is_absolute() and Path(icon_name).exists():
        return icon_name

    # 2. Try bundled icons in package directory
    bundled_icon_path = get_resource_dir() / "icons" / f"{icon_name}.png"
    if bundled_icon_path.exists():
        return str(bundled_icon_path)

    # 3. Try cache directory
    cache_dir = get_cache_dir()
    cached_icon_path = cache_dir / f"{icon_name}.png"
    if cached_icon_path.exists():
        return str(cached_icon_path)

    # 4. Generate and cache a default icon
    logger.warning(f"Icon '{icon_name}' not found, generating default")
    default_icon = generate_default_icon(icon_name)
    default_icon.save(str(cached_icon_path))
    return str(cached_icon_path)


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def load_config(config_file: str) -> Config:
    """Load configuration from a YAML file."""
    with open(config_file, "r") as f:
        config_data = yaml.safe_load(f)
    return Config.model_validate(config_data)


# ---------------------------------------------------------------------------
# Command execution
# ---------------------------------------------------------------------------

def _build_env(extra_paths: list[str] | None = None) -> dict[str, str]:
    """Build an environment dict with extra paths prepended to PATH."""
    env = os.environ.copy()
    if extra_paths:
        extra = ":".join(extra_paths)
        env["PATH"] = f"{extra}:{env.get('PATH', '')}"
    return env


def run_cmd(cmd: str, extra_paths: list[str] | None = None) -> dict | None:
    """Runs a shell command and returns its JSON output as a dict.

    Returns None if the command fails or the output is not valid JSON.
    """
    env = _build_env(extra_paths)
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, env=env)
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
