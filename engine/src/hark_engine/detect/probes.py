"""'Is another app using the microphone?' — the signal that separates a call from a video."""

from __future__ import annotations

import subprocess  # noqa: S404 - fixed argv, no shell
import sys
from dataclasses import dataclass
from typing import Protocol

# Apps that read the mic without being a call (or that are Hark itself).
IGNORED_APPS = {
    "hark",
    "soundcard",
    "pavucontrol",
    "pulseaudio volume control",
    "python",
    "python3",
}


@dataclass(frozen=True)
class MicStatus:
    in_use: bool
    apps: tuple[str, ...] = ()


class MicProbe(Protocol):
    name: str
    last_error: str | None

    def read(self) -> MicStatus | None:
        """None when the OS does not expose this information."""
        ...


class NullProbe:
    name = "unsupported"
    last_error: str | None = "not supported on this system"

    def read(self) -> MicStatus | None:
        return None


# ---- Linux (PulseAudio / PipeWire via pactl) ---------------------------------------
def parse_pactl_sources(short_output: str) -> dict[str, str]:
    """`pactl list short sources` -> {index: name}."""
    out: dict[str, str] = {}
    for line in short_output.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            out[parts[0].strip()] = parts[1].strip()
    return out


def parse_source_outputs(long_output: str, sources: dict[str, str]) -> MicStatus:
    """Parse `pactl list source-outputs`, keeping streams that read a real microphone."""
    apps: list[str] = []
    blocks = [b for b in long_output.split("Source Output #") if b.strip()]
    for block in blocks:
        source_idx = ""
        name = ""
        for raw in block.splitlines():
            line = raw.strip()
            if line.startswith("Source:"):
                source_idx = line.split(":", 1)[1].strip().split()[0]
            elif (
                line.startswith("application.name =")
                or line.startswith("application.process.binary =")
                and not name
            ):
                name = line.split("=", 1)[1].strip().strip('"')
        source_name = sources.get(source_idx, "")
        if source_name.endswith(".monitor"):
            continue  # reading an output (loopback / recorder of system audio), not a mic
        if name.lower() in IGNORED_APPS:
            continue
        apps.append(name or "application inconnue")
    return MicStatus(in_use=bool(apps), apps=tuple(dict.fromkeys(apps)))


class PactlProbe:
    name = "pactl"
    last_error: str | None = None

    def _run(self, *args: str) -> str:
        return subprocess.run(  # noqa: S603
            ["pactl", *args],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=3,
            check=True,
            env={"LC_ALL": "C", "PATH": "/usr/bin:/bin:/usr/local/bin"},
        ).stdout

    def read(self) -> MicStatus | None:
        try:
            sources = parse_pactl_sources(self._run("list", "short", "sources"))
            status = parse_source_outputs(self._run("list", "source-outputs"), sources)
        except FileNotFoundError:
            self.last_error = "pactl not found (install pulseaudio-utils)"
            return None
        except subprocess.CalledProcessError as exc:
            self.last_error = f"pactl failed: {(exc.stderr or '').strip()[:150] or exc.returncode}"
            return None
        except (OSError, subprocess.SubprocessError) as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"[:200]
            return None
        self.last_error = None
        return status


# ---- Windows (CapabilityAccessManager consent store) -----------------------------
CONSENT_KEY = (
    r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone"
)


def app_label_from_registry_name(key_name: str) -> str:
    """`C:#Users#x#...#Zoom.exe` or `MSTeams_8wekyb3d8bbwe` -> readable name."""
    base = key_name.split("#")[-1] if "#" in key_name else key_name
    return base.removesuffix(".exe").split("_")[0] or key_name


class WindowsRegistryProbe:
    """Windows records when each app starts/stops using the microphone (privacy indicator)."""

    name = "windows-consent-store"
    last_error: str | None = None

    def read(self) -> MicStatus | None:
        try:
            import winreg
        except ImportError:  # pragma: no cover
            self.last_error = "winreg unavailable"
            return None
        apps: list[str] = []
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CONSENT_KEY) as root:
                self._scan(winreg, root, apps)
                try:
                    with winreg.OpenKey(root, "NonPackaged") as non_packaged:
                        self._scan(winreg, non_packaged, apps)
                except OSError:
                    pass
        except OSError as exc:
            self.last_error = f"registry unavailable: {exc}"[:200]
            return None
        self.last_error = None
        apps = [a for a in apps if a.lower() not in IGNORED_APPS]
        return MicStatus(in_use=bool(apps), apps=tuple(dict.fromkeys(apps)))

    @staticmethod
    def _scan(winreg: object, parent: object, apps: list[str]) -> None:
        index = 0
        while True:
            try:
                sub = winreg.EnumKey(parent, index)  # type: ignore[attr-defined]
            except OSError:
                return
            index += 1
            if sub == "NonPackaged":
                continue
            try:
                with winreg.OpenKey(parent, sub) as key:  # type: ignore[attr-defined]
                    start, _ = winreg.QueryValueEx(key, "LastUsedTimeStart")  # type: ignore[attr-defined]
                    stop, _ = winreg.QueryValueEx(key, "LastUsedTimeStop")  # type: ignore[attr-defined]
            except OSError:
                continue
            if start and not stop:  # started, not stopped yet
                apps.append(app_label_from_registry_name(sub))


def default_probe(platform: str | None = None) -> MicProbe:
    plat = platform or sys.platform
    if plat.startswith("linux"):
        return PactlProbe()
    if plat == "win32":
        return WindowsRegistryProbe()
    return NullProbe()  # macOS: later version
