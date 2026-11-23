"""Constants for ha-automation-backtest."""

DOMAIN = "automation_backtest"

SERVICE_BACKTEST = "run"
SERVICE_COMPARE = "compare"

ATTR_AUTOMATION = "automation"
ATTR_CONFIG = "config"
ATTR_CONFIG_B = "config_b"
ATTR_START = "start"
ATTR_END = "end"
ATTR_DAYS = "days"
ATTR_INCLUDE_RUNS = "include_runs"
ATTR_MAX_RUNS = "max_runs"
ATTR_SKIP_CONDITIONS = "skip_conditions"

DEFAULT_DAYS = 7
DEFAULT_MAX_RUNS = 200
MAX_DAYS = 90

PANEL_URL_PATH = "automation-backtest"
PANEL_COMPONENT = "automation-backtest-panel"
STATIC_URL = "/automation_backtest_static"
PANEL_MAX_RUNS = 1500
