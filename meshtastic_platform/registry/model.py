"""The node registry as data: one Registry per deployment file.

Everything downstream reads node and radio facts from here — cadences for the
gap estimator, antenna and power for the link analysis, roles and channels for
provisioning. A fact in two places is a measurement that lies, so derived
values (effective cadences, expected tx_power, the radio profile) are computed
by methods on these classes and nowhere else.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Any

from meshtastic_platform.radio import profile as radio_profile
from meshtastic_platform.radio import regulatory
from meshtastic_platform.registry import hardware as hw

# Deployment kinds decide which invariants apply and how tx_power is derived.
#   field       real sites; tx_power derived from the declared EIRP caps;
#               surveyed positions required before a node counts as deployed
#   bench       a lab mesh; tx_power at the chip MINIMUM, positions irrelevant;
#               cadences may be scaled to force congestion
#   historical  a past deployment, kept so old data can be re-read; recorded
#               as it was, including what was never set
KINDS = ("field", "bench", "historical")
# node:     emits measured flows.
# pbx:      a radio driven over UART by a PBX — a BLE processor that multiplexes
#           several phones onto the mesh through this one radio. It carries its
#           users' traffic as well as its own telemetry. Only its membership in
#           the mesh is configured here; the link to the PBX (serial module,
#           Bluetooth) belongs to the PBX project.
# gateway / receiver: listen-only sinks.
FUNCTIONS = ("node", "pbx", "gateway", "receiver")
STATUSES = ("planned", "deployed", "fault", "retired")
# Meshtastic Config.DeviceConfig.Role names.
ROLES = ("CLIENT", "CLIENT_MUTE", "CLIENT_HIDDEN", "CLIENT_BASE", "ROUTER",
         "ROUTER_LATE", "REPEATER", "TRACKER", "SENSOR", "TAK", "TAK_TRACKER",
         "LOST_AND_FOUND")
# Which flow each sensor type produces.
SENSOR_TYPES = {"SHT4X": "environment"}


@dataclass(frozen=True)
class Antenna:
    type: str                                # free text, e.g. "rubber", "fiberglass"
    gain_dbi: float
    band_mhz: tuple[float, float] | None = None
    model: str | None = None
    connector_loss_db: float | None = None   # measured; None = not measured yet


@dataclass(frozen=True)
class Sensor:
    type: str
    i2c_addr: str | None = None
    port: str | None = None


@dataclass(frozen=True)
class Pbx:
    """The PBX attached to a pbx radio: a record, never written to the radio."""
    mcu: str                     # the PBX processor (hardware.PBX_MCUS)
    firmware: str | None = None  # PBX firmware version, recorded once known


@dataclass(frozen=True)
class Position:
    lat: float
    lon: float
    alt_m: float | None = None
    alt_source: str | None = None


@dataclass(frozen=True)
class Site:
    name: str | None = None
    asset_code: str | None = None
    # A RECORD the analysis reads; NEVER written to the radio. Keeping it apart
    # from the GPS-reported position is what lets their difference be read as
    # GPS error. `surveyed` is measured on site; `planned` is a desk position
    # and must not be mistaken for one.
    surveyed: Position | None = None
    planned: Position | None = None
    antenna_height_m: float | None = None
    planned_antenna_height_m: float | None = None
    mount: str | None = None


@dataclass(frozen=True)
class Node:
    ref: str
    function: str
    status: str
    role: str
    hop_limit: int
    intervals: dict[str, int]                 # NOMINAL cadences, seconds
    sensors: tuple[Sensor, ...]
    label: str | None = None
    node_id: str | None = None
    mac: str | None = None
    hardware: str | None = None
    mcu: str | None = None
    firmware: str | None = None
    antenna: Antenna | None = None
    tx_power_dbm: int | None = None
    site: Site | None = None
    pbx: Pbx | None = None                    # function "pbx" only
    notes: str | None = None

    @property
    def name(self) -> str:
        """The name downstream consumers publish this node under."""
        return self.label or self.ref

    @property
    def hardware_spec(self) -> hw.Hardware | None:
        return hw.CATALOGUE.get(self.hardware) if self.hardware else None

    @property
    def chip(self) -> regulatory.Chip:
        spec = self.hardware_spec
        return regulatory.get_chip(spec.chip if spec else hw.DEFAULT_CHIP)

    @property
    def sensor_flows(self) -> set[str]:
        return {SENSOR_TYPES[s.type] for s in self.sensors if s.type in SENSOR_TYPES}

    def record_fields(self, prefix: str = "tx_") -> dict[str, Any]:
        """The node facts that must travel with every reception record.

        Without them, analyses grouped by antenna or sensor have to be rebuilt
        by joining on timestamps, which fails silently every time someone swaps
        an antenna and does not update the YAML.
        """
        a = self.antenna
        return {
            f"{prefix}ref": self.ref,
            f"{prefix}function": self.function,
            f"{prefix}hardware": self.hardware,
            f"{prefix}mcu": self.mcu,
            f"{prefix}firmware": self.firmware,
            f"{prefix}antenna_type": a.type if a else None,
            f"{prefix}antenna_gain_dbi": a.gain_dbi if a else None,
            f"{prefix}power_dbm": self.tx_power_dbm,
            f"{prefix}sensors": "+".join(s.type for s in self.sensors),
            f"{prefix}antenna_height_m": self.site.antenna_height_m if self.site else None,
        }


@dataclass(frozen=True)
class Meta:
    deployment: str
    kind: str
    firmware_target: str | None = None
    cadence_scale: int = 1
    description: str | None = None


@dataclass(frozen=True)
class Registry:
    meta: Meta
    radio_spec: radio_profile.RadioSpec
    nodes: tuple[Node, ...]
    path: Path | None = None
    sha256: str | None = None

    @property
    def name(self) -> str:
        return self.meta.deployment

    @cached_property
    def radio(self) -> radio_profile.RadioProfile:
        """The deployment's radio profile. Raises ValueError if `radio:` is invalid."""
        return radio_profile.build_profile(self.radio_spec)

    def by_ref(self, ref: str) -> Node:
        for n in self.nodes:
            if n.ref == ref:
                return n
        raise KeyError(f"node {ref!r} is not in deployment {self.name!r} "
                       f"(have: {[n.ref for n in self.nodes]})")

    def by_node_id(self, node_id: str) -> Node | None:
        for n in self.nodes:
            if n.node_id == node_id:
                return n
        return None

    def known_nodes(self) -> dict[str, Node]:
        """{node_id: Node} for every node whose id has been recorded."""
        return {n.node_id: n for n in self.nodes if n.node_id}

    def intervals(self, node: Node) -> dict[str, int]:
        """EFFECTIVE cadences: nominal ones divided by meta.cadence_scale.

        The single place the scaling is applied, so the value written to the
        radio and the value an estimator measures against cannot drift apart.
        """
        s = self.meta.cadence_scale
        return {k: v // s for k, v in node.intervals.items()}

    def expected_tx_power(self, node: Node) -> int | None:
        """tx_power this deployment's policy requires of a node, or None.

        field: derived from the antenna gain and the declared EIRP cap.
        bench: the chip minimum, whatever the antenna.
        historical: nothing is required; the record is what it was.
        """
        if self.meta.kind == "bench":
            return node.chip.min_dbm
        if self.meta.kind == "field" and node.antenna is not None:
            return regulatory.derive_tx_power(node.antenna.gain_dbi,
                                              self.radio.eirp_cap_dbm, node.chip)
        return None
