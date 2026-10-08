"""Configuration and constants for the water system domain."""

WAREHOUSE = "watersystem"
DISPLAY_NAME = "Water System"

DEFAULT_CATEGORIES = [
    "Fittings", "Valves", "Meters", "Flanges", "Fasteners", "Sealants", "Pipes",
]

DEFAULT_MATERIALS = [
    "CAST IRON", "DUCTILE IRON", "CAST IRON / DUCTILE IRON", "BRASS",
    "GALVANIZED IRON (G.I.)", "STAINLESS STEEL", "PVC", "PE (POLYETHYLENE)",
    "PPR", "ABS",
]

DEFAULT_SIZES = [
    '1/4"', '3/8"', '1/2"', '3/4"', '1"',
    '1 1/4"', '1 1/2"', '2"', '2 1/2"', '3"',
    '4"', '6"', '8"', '10"',
]

DEFAULT_UNITS = ["pcs", "set", "box", "roll", "m", "kg"]

GDRIVE_SECRET_SECTION = "google_drive"
GDRIVE_SECRET_KEY = "folder_id"