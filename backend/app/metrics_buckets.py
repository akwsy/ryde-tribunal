"""Adaptive dashboard chart buckets, configured in backend/config/dashboard_metrics.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable


_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "dashboard_metrics.json"


def load_metrics_bucket_selector(path: Path | None = None) -> Callable[[int], str]:
    """Load validated inclusive-range cutoffs and return a day-count selector."""
    config_path = path or _CONFIG_PATH
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
        buckets = config["time_series_buckets"]
        daily_max = int(buckets["daily_max_days"])
        weekly_max = int(buckets["weekly_max_days"])
        monthly_max = int(buckets["monthly_max_days"])
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise RuntimeError(f"invalid dashboard metrics configuration: {config_path}") from exc

    if not (0 < daily_max < weekly_max < monthly_max):
        raise RuntimeError("dashboard bucket cutoffs must be positive and strictly increasing")

    def select(inclusive_days: int) -> str:
        if inclusive_days <= daily_max:
            return "day"
        if inclusive_days <= weekly_max:
            return "week"
        if inclusive_days <= monthly_max:
            return "month"
        return "year"

    return select
