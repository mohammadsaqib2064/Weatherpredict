"""Shared colour and type tokens."""
from __future__ import annotations

# --- colour ------------------------------------------------------------------
OCEAN_950 = "#062536"
OCEAN_900 = "#0B3D5C"
OCEAN_800 = "#0F4F73"
OCEAN_700 = "#17628F"
GLACIER_400 = "#7EB6D4"
GLACIER_300 = "#A8D0E6"
GLACIER_100 = "#E7F2F8"  # secondary surface
SAND_50 = "#F7F5F1"  # warm off-white ground (never pure white)
SAND_100 = "#EFEBE3"
INK_900 = "#14212B"
INK_700 = "#3A4A57"
INK_500 = "#6B7C89"
CORAL_600 = "#D96B4C"
CORAL_400 = "#E9A17C"
OK_600 = "#2F6F5E"
WARN_600 = "#C48A2A"
SURFACE = "#FFFFFF"
LINE = "rgba(11, 61, 92, 0.12)"

SEVERITY_COLORS = {
    "high": CORAL_600,
    "medium": WARN_600,
    "low": OCEAN_700,
    "info": INK_500,
}

STATUS_COLORS = {
    "success": OK_600,
    "completed": OK_600,
    "failed": CORAL_600,
    "running": WARN_600,
    "pending": WARN_600,
    "validating": WARN_600,
    "importing": WARN_600,
}

# --- type --------------------------------------------------------------------
FONT_DISPLAY = '"Source Sans", sans-serif'
FONT_BODY = '"Source Sans", sans-serif'

TYPE_SCALE = (12, 14, 16, 20, 24, 32, 40, 56)

# --- charts ------------------------------------------------------------------
DIVERGING_SCALE = [
    [0.00, OCEAN_900],
    [0.20, OCEAN_700],
    [0.40, GLACIER_400],
    [0.50, SAND_50],
    [0.60, CORAL_400],
    [0.80, CORAL_600],
    [1.00, "#A63F26"],
]

# Sequential cool ramp for magnitudes that have no "normal" midpoint.
COOL_SCALE = [
    [0.00, GLACIER_100],
    [0.35, GLACIER_400],
    [0.70, OCEAN_700],
    [1.00, OCEAN_950],
]

CATEGORICAL = [OCEAN_900, GLACIER_400, OK_600, INK_500, OCEAN_700, GLACIER_300]
