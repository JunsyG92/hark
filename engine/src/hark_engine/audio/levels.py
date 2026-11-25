"""Audio level measurement. Only a number leaves this module: no sample is stored."""

from __future__ import annotations

import math
from typing import Any

SILENCE_DB = -120.0


def rms_dbfs(samples: Any) -> float:
    """RMS level in dBFS of float samples in [-1, 1]. Silence maps to -120."""
    import numpy as np

    arr = np.asarray(samples, dtype=np.float64)
    if arr.size == 0:
        return SILENCE_DB
    rms = float(np.sqrt(np.mean(np.square(arr))))
    if rms <= 1e-6:
        return SILENCE_DB
    return max(SILENCE_DB, 20.0 * math.log10(rms))
