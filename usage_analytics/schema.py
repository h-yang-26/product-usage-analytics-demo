"""Event contract shared by the generator, validation, metrics, and UI.

All values here describe a fictional B2B web application. Nothing is derived
from real product telemetry.
"""

SYNTHETIC_LABEL = "Synthetic demonstration; not actual company analytics"

# Column order of the event CSV. Every field is required.
REQUIRED_FIELDS = (
    "event_id",
    "timestamp_utc",
    "user_id",
    "session_id",
    "module",
    "event_type",
)

# Fields compared when the same event_id appears more than once.
PAYLOAD_FIELDS = tuple(f for f in REQUIRED_FIELDS if f != "event_id")

# Only one textual timestamp form is accepted: second precision, explicit "Z".
TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

MODULES = ("catalog", "orders", "support", "reports")
EVENT_TYPES = ("page_view", "search", "detail_view", "export")

# Default ordered session funnel.
FUNNEL_STEPS = ("page_view", "search", "detail_view")
