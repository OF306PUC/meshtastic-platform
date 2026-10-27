"""Modem presets and the LoRa arithmetic that depends only on them.

Moved here from the analysis scripts so every consumer — provisioning, the
validator, the channel-study receiver and the figures — reads one table.

The preset is a per-DEPLOYMENT choice (it lives in the registry's `meta`), so
this module is the catalogue, not the selection.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Preset:
    name: str
    sf: int
    bw_hz: float
    cr_denom: int          # coding rate 4/cr_denom

    @property
    def bw_khz(self) -> float:
        return self.bw_hz / 1e3


# (spreading factor, bandwidth, coding-rate denominator), as in the firmware's
# modem-preset table. Verify against the firmware before trusting a new entry:
# presets have shifted between Meshtastic versions.
PRESETS: dict[str, Preset] = {p.name: p for p in (
    Preset("SHORT_TURBO",   7,  500e3, 5),
    Preset("SHORT_FAST",    7,  250e3, 5),
    Preset("SHORT_SLOW",    8,  250e3, 5),
    Preset("MEDIUM_FAST",   9,  250e3, 5),
    Preset("MEDIUM_SLOW",  10,  250e3, 5),
    Preset("LONG_TURBO",   11,  500e3, 8),
    Preset("LONG_FAST",    11,  250e3, 5),
    Preset("LONG_MODERATE", 11, 125e3, 8),
    Preset("LONG_SLOW",    12,  125e3, 8),
)}

# Families in speed order, fastest/lowest-airtime first. The figures encode
# family as hue and position-in-family as line style, so the order is part of
# the visual contract (see channel_study.analysis.plotstyle).
FAMILIES: dict[str, list[str]] = {
    "Short": ["SHORT_TURBO", "SHORT_FAST", "SHORT_SLOW"],
    "Medium": ["MEDIUM_FAST", "MEDIUM_SLOW"],
    "Long": ["LONG_TURBO", "LONG_FAST", "LONG_MODERATE", "LONG_SLOW"],
}

# Semtech's demodulator floor per spreading factor, in dB.
SNR_LIMIT = {7: -7.5, 8: -10.0, 9: -12.5, 10: -15.0, 11: -17.5, 12: -20.0}

# Typical SX126x receiver noise figure. It only sets the reference lines drawn
# on figures (noise floor, sensitivity); calibrations against Meshtastic's
# published link budgets land between about 4.5 and 6.5 dB depending on the
# transmit power assumed.
NOISE_FIGURE_DB = 6.0

# Meshtastic over-the-air overhead on top of the protobuf payload.
MESHTASTIC_HEADER_BYTES = 16      # MESHTASTIC_HEADER_LENGTH
MESHTASTIC_PKC_OVERHEAD = 12      # MESHTASTIC_PKC_OVERHEAD (direct messages)
MESHTASTIC_PREAMBLE_SYMBOLS = 16


def get(name: str) -> Preset:
    try:
        return PRESETS[name]
    except KeyError:
        raise ValueError(f"unknown modem preset {name!r} (have: {sorted(PRESETS)})") from None


def time_on_air_ms(payload_bytes: int, sf: int, bw_hz: float,
                   cr_denom: int, preamble: int = MESHTASTIC_PREAMBLE_SYMBOLS,
                   crc: int = 1, implicit_header: int = 0) -> float:
    """LoRa time-on-air, per the SX126x datasheet.

    `payload_bytes` is bytes ON AIR (header included). Low-Data-Rate Optimize is
    switched on exactly when the symbol period exceeds 16 ms, which is what the
    radio itself does; forgetting it makes SF11/SF12 at BW125 come out ~10 %
    short.
    """
    t_sym = (2 ** sf) / bw_hz
    de = 1 if t_sym > 0.016 else 0
    cr = cr_denom - 4
    numerator = 8 * payload_bytes - 4 * sf + 28 + 16 * crc - 20 * implicit_header
    denominator = 4 * (sf - 2 * de)
    n_payload = 8 + max(math.ceil(numerator / denominator) * (cr + 4), 0)
    return ((preamble + 4.25) * t_sym + n_payload * t_sym) * 1000


def preset_time_on_air_ms(preset: str | Preset, payload_bytes: int) -> float:
    p = preset if isinstance(preset, Preset) else get(preset)
    return time_on_air_ms(payload_bytes, p.sf, p.bw_hz, p.cr_denom)


def noise_floor_dbm(bw_hz: float) -> float:
    """Thermal noise in the occupied bandwidth, plus the receiver noise figure."""
    return -174 + 10 * math.log10(bw_hz) + NOISE_FIGURE_DB


def sensitivity_dbm(sf: int, bw_hz: float) -> float:
    """Weakest decodable signal: the noise floor plus the demodulator's SNR floor."""
    return noise_floor_dbm(bw_hz) + SNR_LIMIT[sf]


def snr_floor_db(preset: str | Preset) -> float:
    p = preset if isinstance(preset, Preset) else get(preset)
    return SNR_LIMIT[p.sf]
