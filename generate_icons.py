#!/usr/bin/env python3
"""Generate default icons for the command status indicator."""

from PIL import Image, ImageDraw
from pathlib import Path

ICONS_DIR = Path(__file__).parent / "command_status_indicator" / "icons"
ICONS_DIR.mkdir(parents=True, exist_ok=True)

# Icon size for symbolic icons (macOS menu bar compatibility)
ICON_SIZE = 64
APP_ICON_SIZE = 256


def draw_checkbox_checked(size: int) -> Image.Image:
    """Draw a checked checkbox icon."""
    img = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    border = size // 8
    draw.rectangle([border, border, size - border, size - border], outline="black", width=2)
    # Draw checkmark
    check_start_x = size // 4
    check_start_y = size // 2
    check_mid_x = size // 2.5
    check_mid_y = size * 0.65
    check_end_x = size * 0.75
    check_end_y = size // 3
    draw.line([(check_start_x, check_start_y), (check_mid_x, check_mid_y)], fill="black", width=2)
    draw.line([(check_mid_x, check_mid_y), (check_end_x, check_end_y)], fill="black", width=2)
    return img


def draw_checkbox_mixed(size: int) -> Image.Image:
    """Draw a mixed/indeterminate checkbox icon."""
    img = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    border = size // 8
    draw.rectangle([border, border, size - border, size - border], outline="black", width=2)
    # Draw horizontal line
    y = size // 2
    draw.line([(size // 4, y), (size * 0.75, y)], fill="black", width=2)
    return img


def draw_checkbox_unchecked(size: int) -> Image.Image:
    """Draw an unchecked checkbox icon."""
    img = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    border = size // 8
    draw.rectangle([border, border, size - border, size - border], outline="black", width=2)
    return img


def draw_vpn_connected(size: int) -> Image.Image:
    """Draw a VPN connected icon (shield with checkmark)."""
    img = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    # Draw shield
    shield_x1 = size // 4
    shield_y1 = size // 4
    shield_x2 = size * 0.75
    shield_y2 = size * 0.85
    draw.polygon(
        [(shield_x1, shield_y1), (shield_x2, shield_y1), (shield_x2, shield_y2), (size // 2, shield_y2 + size // 8), (shield_x1, shield_y2)],
        outline="black",
    )
    # Draw checkmark inside shield
    check_start_x = size * 0.35
    check_start_y = size * 0.55
    check_mid_x = size * 0.45
    check_mid_y = size * 0.65
    check_end_x = size * 0.65
    check_end_y = size * 0.4
    draw.line([(check_start_x, check_start_y), (check_mid_x, check_mid_y)], fill="black", width=2)
    draw.line([(check_mid_x, check_mid_y), (check_end_x, check_end_y)], fill="black", width=2)
    return img


def draw_vpn_disconnected(size: int) -> Image.Image:
    """Draw a VPN disconnected icon (shield with X)."""
    img = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    # Draw shield
    shield_x1 = size // 4
    shield_y1 = size // 4
    shield_x2 = size * 0.75
    shield_y2 = size * 0.85
    draw.polygon(
        [(shield_x1, shield_y1), (shield_x2, shield_y1), (shield_x2, shield_y2), (size // 2, shield_y2 + size // 8), (shield_x1, shield_y2)],
        outline="black",
    )
    # Draw X inside shield
    x_margin = size // 5
    draw.line([(size // 3, size // 3), (size * 0.67, size * 0.67)], fill="black", width=2)
    draw.line([(size * 0.67, size // 3), (size // 3, size * 0.67)], fill="black", width=2)
    return img


def draw_error(size: int) -> Image.Image:
    """Draw an error icon (circle with X)."""
    img = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    margin = size // 6
    # Draw circle
    draw.ellipse([margin, margin, size - margin, size - margin], outline="black", width=2)
    # Draw X
    inner_margin = size // 4
    draw.line([(inner_margin, inner_margin), (size - inner_margin, size - inner_margin)], fill="black", width=2)
    draw.line([(size - inner_margin, inner_margin), (inner_margin, size - inner_margin)], fill="black", width=2)
    return img


def draw_missing(size: int) -> Image.Image:
    """Draw a missing icon (question mark)."""
    img = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    # Draw border
    border = size // 8
    draw.rectangle([border, border, size - border, size - border], outline="black", width=2)
    # Draw simple question mark shape
    # This is simplified; a real implementation would be more complex
    draw.text((size * 0.35, size * 0.25), "?", fill="black")
    return img


def draw_loading(size: int) -> Image.Image:
    """Draw a loading icon (spinning circle/arc)."""
    img = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    margin = size // 6
    # Draw arc (we'll use an approximate rotating lines pattern)
    draw.arc([margin, margin, size - margin, size - margin], 0, 180, fill="black", width=2)
    return img


def draw_app_icon(size: int) -> Image.Image:
    """Draw the application icon (256x256)."""
    img = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    # Draw a simple application icon: a rectangle with a status dot
    rect_margin = size // 6
    draw.rectangle([rect_margin, rect_margin, size - rect_margin, size - rect_margin], outline="black", width=3, fill="white")
    # Draw a status indicator dot in the corner
    dot_margin = size // 8
    dot_size = size // 10
    draw.ellipse(
        [size - dot_margin - dot_size, dot_margin, size - dot_margin, dot_margin + dot_size],
        fill="green",
    )
    return img


# Icon definitions
icons = {
    "checkbox-checked-symbolic": (ICON_SIZE, draw_checkbox_checked),
    "checkbox-mixed-symbolic": (ICON_SIZE, draw_checkbox_mixed),
    "checkbox-symbolic": (ICON_SIZE, draw_checkbox_unchecked),
    "network-vpn-symbolic": (ICON_SIZE, draw_vpn_connected),
    "network-vpn-disconnected-symbolic": (ICON_SIZE, draw_vpn_disconnected),
    "dialog-error-symbolic": (ICON_SIZE, draw_error),
    "image-missing-symbolic": (ICON_SIZE, draw_missing),
    "image-loading-symbolic": (ICON_SIZE, draw_loading),
    "app-icon": (APP_ICON_SIZE, draw_app_icon),
}

print(f"Generating icons in {ICONS_DIR}...")
for icon_name, (size, draw_func) in icons.items():
    icon_path = ICONS_DIR / f"{icon_name}.png"
    img = draw_func(size)
    img.save(str(icon_path))
    print(f"  Generated {icon_name}.png ({size}x{size})")

print("Done!")
