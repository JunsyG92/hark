"""Model profiles so the tool fits the machine (CPU laptop → GPU workstation)."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

from ..models import ModelProfileId


@dataclass(frozen=True)
class Profile:
    id: ModelProfileId
    label: str
    description: str
    whisper_model: str
    download_mb: int
    min_ram_gb: int
    gpu_recommended: bool


PROFILES: dict[ModelProfileId, Profile] = {
    ModelProfileId.LIGHT: Profile(
        ModelProfileId.LIGHT,
        "Léger",
        "Petit PC / peu de mémoire. Rapide, précision correcte en français et en anglais clairs.",
        "base",
        150,
        4,
        False,
    ),
    ModelProfileId.BALANCED: Profile(
        ModelProfileId.BALANCED,
        "Équilibré",
        "Recommandé pour un portable récent sans carte graphique : bon compromis vitesse/qualité.",
        "small",
        490,
        8,
        False,
    ),
    ModelProfileId.ACCURATE: Profile(
        ModelProfileId.ACCURATE,
        "Précis",
        "Meilleure qualité (noms propres, accents). Lent sans carte graphique NVIDIA.",
        "medium",
        1530,
        16,
        True,
    ),
    ModelProfileId.BEST: Profile(
        ModelProfileId.BEST,
        "Très précis",
        "Qualité maximale (large-v3-turbo). Pour une carte graphique NVIDIA avec ≥ 6 Go de VRAM.",
        "large-v3-turbo",
        1620,
        16,
        True,
    ),
}


def total_ram_gb() -> float | None:
    """Physical memory in GB (None if unknown). No third-party dependency."""
    try:
        if sys.platform == "win32":
            import ctypes

            class _Mem(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            mem = _Mem()
            mem.dwLength = ctypes.sizeof(_Mem)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem))
            return float(mem.ullTotalPhys) / 1024**3
        pages = os.sysconf("SC_PHYS_PAGES")
        size = os.sysconf("SC_PAGE_SIZE")
        return float(pages * size) / 1024**3
    except (OSError, ValueError, AttributeError):
        return None


def has_cuda() -> bool:
    try:
        import ctranslate2

        return int(ctranslate2.get_cuda_device_count()) > 0
    except Exception:
        return False


def recommend(ram_gb: float | None, gpu: bool) -> ModelProfileId:
    if gpu:
        return ModelProfileId.ACCURATE
    if ram_gb is not None and ram_gb < 8:
        return ModelProfileId.LIGHT
    return ModelProfileId.BALANCED
