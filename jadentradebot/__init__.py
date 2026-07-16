"""jadentradebot — a trading & stock identifier built on the DTR vs ATR indicator.

Faithful Python port of the thinkorswim "Custom ATR Plot" ThinkScript by 7of9
(shared on usethinkscript.com), extended into a multi-ticker scanner, CLI, and
web dashboard.
"""

from jadentradebot.indicator import DtrVsAtrResult, Status, dtr_vs_atr
from jadentradebot.scanner import ScanRow, scan

__version__ = "1.0.0"

__all__ = [
    "DtrVsAtrResult",
    "Status",
    "dtr_vs_atr",
    "ScanRow",
    "scan",
    "__version__",
]
