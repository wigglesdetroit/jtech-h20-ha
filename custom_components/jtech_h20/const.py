"""Constants for the J-Tech HDMI Matrix (8x8 H20) integration."""

from datetime import timedelta

DOMAIN = "jtech_h20"
MANUFACTURER = "J-Tech Digital"
MODEL = "JTECH-8X8-H20 (JTD-279)"
SCAN_INTERVAL = timedelta(seconds=5)

# Options: input_1..input_8 and output_1..output_8 names (blank = hide),
# tv_1..tv_8 = what the TV on that output supports ("4K" / "1080p").
CONF_INPUT = "input_{}"
CONF_OUTPUT = "output_{}"
CONF_TV = "tv_{}"
TV_TYPES = ["4K", "1080p"]
