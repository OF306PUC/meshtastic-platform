"""Frequency slots, radiated-power caps and the transmit power they imply.

`tx_power_dbm` is a DERIVED value, not a preference. Where the law caps RADIATED
power (EIRP), the conducted power a node may use depends on its antenna gain,
and the cap depends on which band the channel slot falls in. Provisioning
computes it here and the inspector verifies it against the same function.

The caps themselves are not in the code: each deployment declares the ones that
apply where it operates (`radio.eirp_caps` in its YAML).

Firmware trap, traced in the source: with tx_power unset (0) the node writes the
REGION's power limit into its config but transmits only what the chip can.
Reading the config back returns the region number; the real figure is the
"Final Tx power: N dBm" console line at boot.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

from meshtastic_platform.radio import presets as _presets


@dataclass(frozen=True)
class Band:
    """A frequency range with a cap on radiated power (EIRP)."""
    low_mhz: float
    high_mhz: float
    eirp_dbm: float
    label: str = ""

    def contains(self, low_mhz: float, high_mhz: float) -> bool:
        return self.low_mhz <= low_mhz and high_mhz <= self.high_mhz

    def describe(self) -> str:
        name = f"{self.label} " if self.label else ""
        return f"{name}{self.low_mhz:g}–{self.high_mhz:g} MHz, {self.eirp_dbm:g} dBm EIRP"


@dataclass(frozen=True)
class Region:
    name: str
    freq_start_mhz: float
    freq_end_mhz: float
    spacing_mhz: float
    power_limit_dbm: int     # firmware RDEF powerLimit: what an UNSET tx_power becomes


# Meshtastic regions known to the catalogue. Adding one means copying its RDEF
# line from the firmware (RadioInterface.cpp), not guessing.
REGIONS: dict[str, Region] = {
    "ANZ": Region("ANZ", 915.0, 928.0, 0.0, 30),
}


@dataclass(frozen=True)
class Chip:
    name: str
    min_dbm: int
    max_dbm: int
    invalid: frozenset[int] = frozenset()     # inside the range, but refused by the driver

    def valid(self, dbm: int) -> bool:
        return self.min_dbm <= dbm <= self.max_dbm and dbm not in self.invalid


CHIPS: dict[str, Chip] = {
    # SX126X_MAX_POWER = 22; -9 dBm is the lowest the SX1262 PA allows.
    "sx1262": Chip("sx1262", -9, 22),
    # Meshtastic caps the SX127x at RF95_MAX_POWER = 20 (RF95Interface).
    # RadioLib's PA_BOOST output takes 2..17 dBm or exactly 20: 18 and 19 are
    # refused (the node records a critical INVALID_RADIO_SETTING error), and
    # below 2 RadioLib switches to the RFO output instead, a different RF path
    # that does not reach the antenna on every board. 2 dBm is therefore the
    # floor used here.
    "sx1276": Chip("sx1276", 2, 20, frozenset({18, 19})),
}


@dataclass(frozen=True)
class Slot:
    """Where a channel actually sits on air."""
    region: str
    preset: str
    channel_num: int          # 1-based, as in lora.channel_num
    source: str               # "explicit" | "hash"
    n_slots: int
    center_mhz: float
    low_mhz: float
    high_mhz: float

    def describe(self) -> str:
        how = "explicit" if self.source == "explicit" else "djb2 hash of the primary channel name"
        return (f"slot {self.channel_num}/{self.n_slots} ({how}) = {self.center_mhz:.3f} MHz, "
                f"occupying {self.low_mhz:.3f}–{self.high_mhz:.3f} MHz")


def get_region(name: str) -> Region:
    try:
        return REGIONS[name]
    except KeyError:
        raise ValueError(f"region {name!r} is not in the catalogue (have: {sorted(REGIONS)}); "
                         f"add it from the firmware's RDEF table") from None


def get_chip(name: str) -> Chip:
    try:
        return CHIPS[name]
    except KeyError:
        raise ValueError(f"radio chip {name!r} is not in the catalogue (have: {sorted(CHIPS)})") from None


def djb2(text: str) -> int:
    """The firmware's channel-name hash (uint32 arithmetic)."""
    h = 5381
    for c in text.encode("utf-8"):
        h = ((h << 5) + h + c) & 0xFFFFFFFF
    return h


def n_slots(region: Region, bw_khz: float) -> int:
    bw_mhz = bw_khz / 1000
    return int(math.floor((region.freq_end_mhz - region.freq_start_mhz + region.spacing_mhz)
                          / (region.spacing_mhz + bw_mhz)))


def resolve_slot(region_name: str, preset_name: str, channel_num: int | None,
                 primary_channel_name: str) -> Slot:
    """Frequency of a channel, exactly as the firmware computes it.

        index = channel_num - 1            if channel_num is set
              = djb2(primary name) % n     otherwise
        f     = freq_start + bw/2 + index * bw
    """
    region = get_region(region_name)
    preset = _presets.get(preset_name)
    n = n_slots(region, preset.bw_khz)
    if channel_num:
        if not 1 <= channel_num <= n:
            raise ValueError(f"channel_num {channel_num} outside 1..{n} for {preset_name} "
                             f"(BW {preset.bw_khz:g} kHz) in {region_name}")
        index, source = channel_num - 1, "explicit"
    else:
        index, source = djb2(primary_channel_name) % n, "hash"
    bw_mhz = preset.bw_khz / 1000
    center = region.freq_start_mhz + bw_mhz / 2 + index * bw_mhz
    return Slot(region_name, preset_name, index + 1, source, n,
                round(center, 6), round(center - bw_mhz / 2, 6), round(center + bw_mhz / 2, 6))


def eirp_cap(slot: Slot, caps: Sequence[Band]) -> Band | None:
    """The most permissive declared band containing the WHOLE occupied channel.

    A channel straddling a band edge is not in that band. None when the
    deployment declares no caps at all; an error when it declares some and the
    channel fits none of them.
    """
    if not caps:
        return None
    fits = [b for b in caps if b.contains(slot.low_mhz, slot.high_mhz)]
    if not fits:
        raise ValueError(f"{slot.describe()} is outside every declared EIRP band")
    return max(fits, key=lambda b: b.eirp_dbm)


def derive_tx_power(gain_dbi: float, cap_dbm: float | None, chip: Chip) -> int:
    """Highest valid conducted power that keeps EIRP under the cap.

        tx_power = highest valid setting <= min(floor(cap - gain), chip.max)

    Without a cap, the chip's maximum. Connector loss is deliberately NOT
    credited: it lowers EIRP, so ignoring it keeps the result on the safe side
    whether or not it has been measured.
    """
    allowed = chip.max_dbm if cap_dbm is None else math.floor(cap_dbm - gain_dbi + 1e-9)
    tx = min(allowed, chip.max_dbm)
    while tx >= chip.min_dbm and not chip.valid(tx):
        tx -= 1                                  # e.g. SX1276: 19 -> 17
    if tx < chip.min_dbm:
        raise ValueError(f"a {gain_dbi} dBi antenna exceeds the {cap_dbm} dBm cap even at the "
                         f"{chip.name} minimum ({chip.min_dbm} dBm)")
    return tx


def eirp_dbm(tx_power_dbm: float, gain_dbi: float) -> float:
    return tx_power_dbm + gain_dbi


def effective_tx_power(configured_dbm: int, region: Region, chip: Chip) -> int:
    """What the radio really transmits for a configured lora.tx_power.

    0 means unset: the firmware substitutes the region limit, then clamps to the
    chip.
    """
    power = configured_dbm if configured_dbm else region.power_limit_dbm
    if power > region.power_limit_dbm:
        power = region.power_limit_dbm
    return max(chip.min_dbm, min(power, chip.max_dbm))
