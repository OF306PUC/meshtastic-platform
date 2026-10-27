"""Hardware catalogue: what each `hardware` value in a registry means.

`mcu` is recorded per node AND derivable from `hardware`; invariant V8 checks
they agree. The redundancy is the point: comparing an ESP32 against an nRF52
node without recording which is which reintroduces the mixed-firmware problem —
a systematic hardware difference (layout, front end, RF-switch handling) that
reads as a propagation effect.

`hw_model` is the Meshtastic HardwareModel enum name the device reports, which
is how the inspector confirms the registry entry describes the radio on the
port. `has_wifi` is the fallback: DeviceMetadata.hasWifi tells ESP32 from nRF52
even when the model name is unexpected.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Hardware:
    name: str
    mcu: str
    chip: str          # LoRa transceiver; decides the tx_power range
    hw_model: str      # Meshtastic HardwareModel enum name
    flashing: str      # how the Web Flasher handles it: "webserial" | "uf2"


# MCU families. ESP32-S3 boards are recorded as "esp32": the confounder that
# matters is the family (radio front end and firmware variant), and `hardware`
# names the exact board.
MCUS = {"nrf52840": {"has_wifi": False}, "esp32": {"has_wifi": True}}

CATALOGUE: dict[str, Hardware] = {h.name: h for h in (
    Hardware("sensecap_solar_node_p1_pro", "nrf52840", "sx1262", "SEEED_SOLAR_NODE", "uf2"),
    # The T-Beam ships with an SX1276 or an SX1262, and the chip decides the
    # tx_power range: one entry per variant, both reporting TBEAM.
    Hardware("lilygo_tbeam_sx1276", "esp32", "sx1276", "TBEAM", "webserial"),
    Hardware("lilygo_tbeam_sx1262", "esp32", "sx1262", "TBEAM", "webserial"),
)}

# Processors a PBX runs on (a pbx node's `pbx.mcu`): the nRF52840 of the
# current prototype (nRF52840 DK) and the nRF54L15 of the board being designed.
PBX_MCUS = ("nrf52840", "nrf54l15")

# Used only when a node's `hardware` is not recorded yet; the validator warns
# whenever it relies on this, so the assumption is visible rather than silent.
DEFAULT_CHIP = "sx1262"


def get(name: str) -> Hardware:
    try:
        return CATALOGUE[name]
    except KeyError:
        raise ValueError(f"hardware {name!r} is not in the catalogue "
                         f"(have: {sorted(CATALOGUE)})") from None
