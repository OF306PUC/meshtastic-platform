"""A deployment's radio configuration, resolved and checked.

Every radio setting of a mesh — region, preset, slot, channels and the
environment variables holding their keys, rebroadcast mode, position
precision, the radiated-power caps where it operates — is declared in the
deployment file (`radio:` block). This module turns that declaration into a
RadioProfile that provisioning writes and the inspector compares against. It
holds no setting of its own beyond rules the measurements depend on.

A receiver on a different channel, preset, slot or key hears nothing — no
error, just no packets — which is why all of them come from one declaration.

Channel keys (PSKs) are secrets: the deployment names the environment variable,
the value lives in `.env` (repository root or current directory), never in git.
They are loaded only when something writes or compares a key, and loudly.
"""
from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from pathlib import Path

from meshtastic_platform.radio import presets, regulatory

_REPO_ROOT = Path(__file__).resolve().parents[2]  # <root>/meshtastic_platform/radio/profile.py


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (no external dependency). Won't override existing env vars."""
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip())


_load_dotenv(_REPO_ROOT / ".env")
_load_dotenv(Path.cwd() / ".env")

# Smart position broadcast defaults to TRUE in firmware and adds
# movement-triggered packets on top of the periodic timer, which breaks the
# fixed-cadence hypothesis the gap and delivery estimators rest on. Always off.
POSITION_BROADCAST_SMART_ENABLED = False


@dataclass(frozen=True)
class Channel:
    index: int
    name: str
    psk_env: str               # environment variable holding the base64 key


@dataclass(frozen=True)
class RadioSpec:
    """The `radio:` block of a deployment, as declared."""
    region: str
    modem_preset: str
    channel_num: int | None
    channels: tuple[Channel, ...]
    rebroadcast_mode: str
    position_precision: int
    rx_boosted_gain: bool
    eirp_caps: tuple[regulatory.Band, ...]


@dataclass(frozen=True)
class RadioProfile:
    spec: RadioSpec
    slot: regulatory.Slot
    band: regulatory.Band | None      # the declared cap the slot falls under, if any

    # Convenience views of the declaration.
    @property
    def region(self) -> str:
        return self.spec.region

    @property
    def modem_preset(self) -> str:
        return self.spec.modem_preset

    @property
    def channels(self) -> tuple[Channel, ...]:
        return self.spec.channels

    @property
    def primary_channel(self) -> Channel:
        return self.spec.channels[0]

    @property
    def rebroadcast_mode(self) -> str:
        return self.spec.rebroadcast_mode

    @property
    def position_precision(self) -> int:
        return self.spec.position_precision

    @property
    def rx_boosted_gain(self) -> bool:
        return self.spec.rx_boosted_gain

    @property
    def position_broadcast_smart_enabled(self) -> bool:
        return POSITION_BROADCAST_SMART_ENABLED

    @property
    def channel_num_setting(self) -> int:
        """Value for lora.channel_num: the slot if explicit, 0 (= hash) otherwise."""
        return self.slot.channel_num if self.slot.source == "explicit" else 0

    @property
    def eirp_cap_dbm(self) -> float | None:
        return self.band.eirp_dbm if self.band else None

    @property
    def preset(self) -> presets.Preset:
        return presets.get(self.modem_preset)

    @property
    def snr_floor_db(self) -> float:
        return presets.snr_floor_db(self.modem_preset)

    def describe(self) -> str:
        cap = f"; cap {self.band.describe()}" if self.band else "; no EIRP cap declared"
        return f"{self.region} {self.modem_preset}, {self.slot.describe()}{cap}"


def build_profile(spec: RadioSpec) -> RadioProfile:
    """Resolve a declaration. Raises ValueError if it is invalid."""
    if not spec.channels:
        raise ValueError("radio.channels is empty: a mesh needs at least its primary channel")
    slot = regulatory.resolve_slot(spec.region, spec.modem_preset, spec.channel_num,
                                   spec.channels[0].name)
    return RadioProfile(spec=spec, slot=slot, band=regulatory.eirp_cap(slot, spec.eirp_caps))


# Key lengths the firmware accepts: 1 byte (one of its well-known keys),
# 16 (AES-128) or 32 (AES-256).
PSK_LENGTHS = (1, 16, 32)


def channel_psks(profile: RadioProfile) -> dict[int, str]:
    """{channel index: base64 PSK} from the environment.

    Raises, naming the variables (never the values), if any is missing or is
    not a key — the .env.example placeholder included.
    """
    values = {ch.index: os.environ.get(ch.psk_env) for ch in profile.channels}
    missing = [ch.psk_env for ch in profile.channels if not values[ch.index]]
    if missing:
        raise RuntimeError(
            f"Channel PSK(s) not set: {', '.join(missing)}. Copy .env.example to .env "
            f"and set them (base64; the same on every radio of the mesh).")
    invalid = []
    for ch in profile.channels:
        try:
            ok = len(decode_psk(values[ch.index])) in PSK_LENGTHS
        except ValueError:
            ok = False
        if not ok:
            invalid.append(ch.psk_env)
    if invalid:
        raise RuntimeError(
            f"Channel PSK(s) not valid: {', '.join(invalid)}. Expected base64:<key> of "
            f"{'/'.join(map(str, PSK_LENGTHS))} bytes, e.g. from `openssl rand -base64 32`.")
    return values


def decode_psk(psk_b64: str) -> bytes:
    """Decode a channel PSK as stored in .env: 'base64:<key>' or bare base64.
    Raises ValueError (binascii.Error) on anything that is not strict base64."""
    if psk_b64.startswith("base64:"):
        psk_b64 = psk_b64[len("base64:"):]
    return base64.b64decode(psk_b64, validate=True)
