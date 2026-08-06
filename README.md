# Command Status Indicator

A lightweight system tray indicator that displays status from shell commands and provides interactive menu items. Perfect for monitoring application states, system services, or custom status information in the system tray.

This was inspired by Waybar custom widget, but with menus.

## Features

- Runs custom shell commands at configurable intervals
- Displays dynamic status icons and labels in the system tray
- Responds to JSON output from commands
- Customizable menu items with associated commands
- Debouncing on menu item clicks to prevent rapid refreshes
- Fallback status display for unknown states
- Verbose logging for debugging

## Configuration

Configuration is done via YAML files. Create a YAML file with the following structure:

### Example Configuration

```yaml
indicator_id: my-status-indicator
cmd: my-status-command
status_key: status
refresh: 30
debounce_refresh_on_command: 3

statuses:
  status1:
    icon: some-icon
    menu_items:
      - label: Action for Status 1
        events:
          activate: "some-command-for-status1"

  status2:
    icon: other-icon
    text: Other Status
    menu_items: []
```

A more detailed example configuration is provided in [](./example_config.yaml).

### Configuration Fields

- **indicator_id**: Unique identifier for the indicator (required)
- **cmd**: Shell command to execute (required). Must return JSON containing a status value
- **status_key**: JSON key containing the status value (default: `status`)
- **label_guide**: Optional width guide for label alignment
- **refresh**: Refresh interval in seconds (default: 30)
- **debounce_refresh_on_command**: Debounce interval in seconds (default: 0)
- **statuses**: Dictionary mapping status values to configuration (required) -- see [Status Fields](#status-fields).
- **fallback_status**: Optional fallback configuration for unknown statuses. It contains a single [Status Field](#status-fields)

#### Status Fields

- **icon**: Icon name (from icon theme, e.g., `network-vpn-symbolic`)
- **text**: Optional label text to display in the tray
- **alt_text**: Accessibility text (description)
- **menu_items**: List of menu items with commands to execute -- see [Menu Item Fields](#menu-item-fields).

#### Menu Item Fields

- **label**: Text displayed in the menu
- **events**: Dictionary mapping GTK signals to shell commands (typically `activate` for button clicks)

## Running

### macOS

Install the macOS dependencies (rumps) and run:

```bash
uv sync --extra osx
uv run command-status-indicator -c /path/to/config.yaml
```

For debug output, add the `-v` or `--verbose` flag:

```bash
uv run command-status-indicator -c /path/to/config.yaml -v
```

### Linux

Install the Linux dependencies (PyGObject) and run:

```bash
uv sync --extra linux
uv run command-status-indicator -c /path/to/config.yaml
```

For debug output, add the `-v` or `--verbose` flag:

```bash
uv run command-status-indicator -c /path/to/config.yaml -v
```

## Building a macOS App

To build a standalone `.app` bundle for macOS:

```bash
uv sync --extra osx --extra dev
uv run pyinstaller pyinstaller_rumps.spec --clean
```

The resulting app will be at `dist/Command Status Indicator.app`.

Note: If you encounter issues with the icon format, PyInstaller may require an `.icns` file. You can convert the generated `app-icon.png` to `.icns` format using:

```bash
# Install iconutil first (included with Xcode)
cd command_status_indicator/icons
# Convert PNG to ICNS (requires Image2Icon or similar conversion tool)
```

Alternatively, omit the icon from the spec file if conversion is not available.

## Autostart with XDG

To automatically start the indicator when your desktop environment starts, create an `.desktop` file in `~/.config/autostart/`:

### Example Autostart File

Create `~/.config/autostart/command-status-indicator.desktop`:

```ini
[Desktop Entry]
Type=Application
Name=Status for My Command
Comment=Display command status in system tray
Exec=command-status-indicator -c ~/.config/command-status-indicator/my-status.yaml
StartupNotify=false
Terminal=false
Categories=Utility;System;

# Only show in GNOME and compatible DEs
OnlyShowIn=GNOME;X-Cinnamon;Unity;

# Hide from menu (runs in background)
NoDisplay=true
```

Then place your configuration file at `~/.config/command-status-indicator/my-status.yaml`:

The indicator will automatically start on next login.

## Example Use Cases

- **VPN Status**: Display VPN connection status with connect/disconnect actions
- **Service Monitor**: Monitor custom service status with restart/start/stop actions
- **System Status**: Display battery, disk space, or temperature with refresh options
- **Application Status**: Show application state with common actions

## Command Output Format

Your command must output valid JSON containing the status key:

```bash
# Example command output
{
  "status": "connected",
  "details": "additional info"
}
```

The indicator extracts the value from the key specified in `status_key` (default: `status`).

## Debugging

Enable verbose logging to see what the indicator is doing:

```bash
command-status-indicator -c config.yaml -v
```

This will show:
- Command execution details
- Status changes
- Menu item clicks
- Refresh timing
- Errors and warnings
