"""Command Status Indicator — CLI entry point.

Dispatches to the appropriate platform frontend (Linux GTK or macOS rumps).
"""

import argparse
import logging
import signal
import subprocess
import sys
from pathlib import Path

from .config import load_config

IS_MACOS = sys.platform == "darwin"

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Auto-load: spawn one indicator process per YAML config
# ---------------------------------------------------------------------------


def _run_autoload():
    """Spawn one indicator process per YAML config in
    ~/.config/command-status-indicator/.
    """
    config_dir = Path.home() / ".config" / "command-status-indicator"
    if not config_dir.is_dir():
        logger.error("Config directory does not exist: %s", config_dir)
        return

    configs = sorted(config_dir.glob("*.yaml")) + sorted(config_dir.glob("*.yml"))
    if not configs:
        logger.error("No YAML config files found in %s", config_dir)
        return

    logger.info("Auto-loading %d indicator(s) from %s", len(configs), config_dir)

    children = []
    for config_path in configs:
        try:
            load_config(str(config_path))
        except Exception as exc:
            logger.error("Skipping %s: %s", config_path, exc)
            continue

        logger.info("Starting indicator from %s", config_path)
        # Re-run the same executable with a single -c argument.
        cmd = [sys.argv[0], "-c", str(config_path)]
        proc = subprocess.Popen(cmd)
        children.append(proc)

    if not children:
        logger.error("No valid configs to load")
        return

    def _terminate_children(signum, _frame):
        logger.info("Received signal %d, terminating all indicators", signum)
        for proc in children:
            proc.terminate()
        # Give them a moment, then force-kill stragglers.
        import time

        time.sleep(1)
        for proc in children:
            if proc.poll() is None:
                proc.kill()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _terminate_children)
    signal.signal(signal.SIGINT, _terminate_children)

    # Wait until all children have exited.
    for proc in children:
        proc.wait()


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main():
    """Main function to set up the indicator(s)."""
    parser = argparse.ArgumentParser(description="Command Status Indicator")
    parser.add_argument(
        "-c",
        "--config",
        help="Configuration file. If omitted, all *.yaml/*.yml files "
        "in ~/.config/command-status-indicator/ are loaded automatically.",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging"
    )
    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Auto-load when no config is given (both platforms)
    if not args.config:
        _run_autoload()
        return

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

    if IS_MACOS:
        from .frontend_osx import create_rumps_app

        app = create_rumps_app(config, log_level)
        app.run()
    else:
        from .frontend_linux import run_gtk_indicator

        run_gtk_indicator(config)


if __name__ == "__main__":
    main()
