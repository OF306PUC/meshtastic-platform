"""Registry entry -> the exact Meshtastic CLI steps that configure it. Pure.

Every value written to a radio comes from the deployment file: the node's role,
hop limit, cadences, sensors and antenna, and the deployment's `radio:` block
(region, preset, slot, channels, precision, rebroadcast). Nothing is chosen
here, so nothing can drift from what the receiver measures against. Together
these are the radio's MEMBERSHIP in the mesh; a pbx radio gets its membership
here and its link to the PBX from the PBX project.

What provisioning deliberately never does:
* write a position. The surveyed position is a record the analysis reads;
  writing it as fixed_position would make the node report the survey instead
  of its GPS fix and destroy the one comparison worth having (survey minus
  GPS-reported = GPS error).
* leave tx_power unset. Unset reads back as the region limit and transmits the
  chip ceiling. It is DERIVED from the antenna gain and the declared cap, by the
  same function the validator uses.
* leave smart position broadcast on. It adds movement-triggered packets on top
  of the periodic timer and breaks the cadence the gap estimator relies on.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from meshtastic_platform.registry.model import Node, Registry

# Local GPS fix interval, keyed by function because that is what says whether
# the radio moves. A fix costs no airtime, so this is a device setting, not a
# broadcast cadence (those live only in the deployment file): how often the
# radio puts a position ON AIR is its `position` flow, and this is only how
# fresh the fix behind it is.
#
# A field node, a pbx radio and a gateway are bolted to something: one fix an
# hour is more than they need, and the GPS sleeps the rest of the hour. Not
# maxint — which the firmware reads as "once at boot" — because a node powered
# on under a roof during installation would then never fix again, and would
# report nothing for weeks without a word. A receiver is the one that moves:
# 30 s, which is also the resolution of the track receiver.py samples over USB.
#
# Firmware defaults, for scale (meshtastic.org/docs/configuration/radio/position):
# gps_update_interval 0 = every 2 min, position_broadcast_secs 0 = 15 min,
# position_broadcast_smart_enabled = true. All three are written explicitly here.
GPS_UPDATE_INTERVAL_S = {"node": 3600, "pbx": 3600, "receiver": 30, "gateway": 3600}

REDACTED = "<psk>"


def _b(value: bool) -> str:
    return str(bool(value)).lower()


@dataclass(frozen=True)
class Step:
    label: str
    argv: list[str]
    # argv positions holding secrets: shown as <psk>, never echoed.
    secret: frozenset[int] = field(default_factory=frozenset)

    def display(self) -> str:
        return " ".join(REDACTED if i in self.secret else a for i, a in enumerate(self.argv))


def base_cmd(port: str | None) -> list[str]:
    return ["meshtastic"] + (["--port", port] if port else [])


def lora_settings(reg: Registry, node: Node) -> list[tuple[str, str]]:
    p = reg.radio
    tx = reg.expected_tx_power(node)
    if tx is None:
        raise ValueError(f"{node.ref}: no tx_power can be derived "
                         f"(deployment kind {reg.meta.kind!r}, antenna {node.antenna})")
    settings = [
        ("lora.region", p.region),
        ("lora.modem_preset", p.modem_preset),
        ("lora.channel_num", str(p.channel_num_setting)),
        ("lora.hop_limit", str(node.hop_limit)),
        ("lora.tx_power", str(tx)),
    ]
    # SX126x-only: an SX127x stores it and ignores it, so it is not written
    # there — a setting that does nothing should not look like it does.
    if node.chip.name == "sx1262":
        settings.append(("lora.sx126x_rx_boosted_gain", _b(p.rx_boosted_gain)))
    return settings


def telemetry_settings(reg: Registry, node: Node) -> list[tuple[str, str]]:
    iv = reg.intervals(node)
    out = [
        ("telemetry.device_telemetry_enabled", _b("device" in iv)),
        ("telemetry.environment_measurement_enabled", _b("environment" in node.sensor_flows)),
    ]
    if "device" in iv:
        out.append(("telemetry.device_update_interval", str(iv["device"])))
    if "environment" in iv:
        out.append(("telemetry.environment_update_interval", str(iv["environment"])))
    return out


def position_settings(reg: Registry, node: Node) -> list[tuple[str, str]]:
    """GPS and position broadcasting. Every value written, none left to default.

    `fixed_position` is written false on EVERY radio, GPS or no GPS. It is not a
    position being written — it is the opposite: it is what keeps the radio
    reporting its own fix. The Meshtastic CLI turns it on implicitly whenever
    someone sets a latitude and longitude (`--remove-position` is what unsets
    it), so a radio reused from another project can arrive with it on and then
    report stored coordinates forever while its GPS runs. The inspector checks
    it (I3); writing it here is what makes the check pass by construction.

    The firmware's own defaults are all wrong for a channel study: smart
    broadcast on (movement-triggered packets, no cadence to measure against),
    a 15-minute position broadcast nobody declared, and a fix every 2 minutes.
    All three are overwritten. The settings go out in ONE `--set` command,
    which is also what the Meshtastic docs advise for position fields.
    """
    iv = reg.intervals(node)
    fixed = ("position.fixed_position", "false")
    smart = ("position.position_broadcast_smart_enabled",
             _b(reg.radio.position_broadcast_smart_enabled))
    if "position" not in iv:
        # No declared position flow: GPS off, or the node would broadcast at the
        # firmware default cadence — a flow no estimator expects.
        return [("position.gps_mode", "DISABLED"), smart, fixed]
    return [
        ("position.gps_mode", "ENABLED"),
        ("position.gps_update_interval", str(GPS_UPDATE_INTERVAL_S.get(node.function, 3600))),
        smart,
        fixed,
        ("position.position_broadcast_secs", str(iv["position"])),
    ]


def serial_settings(node: Node) -> list[tuple[str, str]]:
    """The serial module: off, except on a pbx radio, where it is not touched.

    A pbx radio's serial module and Bluetooth are the link its PBX drives it
    through; they belong to the PBX project, which configures and checks them.
    On every other radio the serial module is written off, so a radio reused
    from a PBX does not keep driving pins nothing listens to.
    """
    return [] if node.function == "pbx" else [("serial.enabled", "false")]


def bluetooth_settings(node: Node) -> list[tuple[str, str]]:
    """Bluetooth: on, except on a pbx radio, where it is not touched.

    BLE is how a phone or a laptop reaches a radio, so it is written on rather
    than assumed: a radio reused from a PBX arrives with Bluetooth off, because
    there the nRF52840 serves the BLE side instead. On a pbx radio it stays the
    PBX project's to configure, like the serial module above.
    """
    return [] if node.function == "pbx" else [("bluetooth.enabled", "true")]


def _sets(cmd: list[str], settings: list[tuple[str, str]]) -> list[str]:
    argv = list(cmd)
    for key, value in settings:
        argv += ["--set", key, value]
    return argv


def channel_steps(reg: Registry, cmd: list[str], psks: dict[int, str]) -> list[Step]:
    """Every channel written at its own index: name, key, precision.

    `--ch-set ... --ch-index i` writes slot i and enables it (PRIMARY at 0,
    SECONDARY elsewhere), whatever the radio held there before, so re-running
    it converges. `--ch-add` is not used: it takes the first FREE slot, so on a
    radio that still carries another mesh's channel it would land on the wrong
    index and leave the old one in place.
    """
    prec = str(reg.radio.position_precision)
    steps = []
    for ch in reg.radio.channels:
        argv = cmd + ["--ch-set", "name", ch.name, "--ch-set", "psk"]
        secret = {len(argv)}
        argv += [psks[ch.index], "--ch-set", "module_settings.position_precision", prec,
                 "--ch-index", str(ch.index)]
        steps.append(Step(f"channel {ch.index} ({ch.name})", argv, frozenset(secret)))
    return steps


def node_steps(reg: Registry, node: Node, port: str | None,
               psks: dict[int, str]) -> list[Step]:
    """Provisioning plan for a node, a pbx radio, a gateway radio or a receiver."""
    cmd = base_cmd(port)
    p = reg.radio
    return [
        Step("LoRa (region/preset/slot/hop_limit/tx_power)", _sets(cmd, lora_settings(reg, node))),
        # Role, then rebroadcast mode — verified afterwards, because it has been
        # seen silently not to persist when set together with device.role.
        Step("device role + rebroadcast_mode", _sets(cmd, [
            ("device.role", node.role), ("device.rebroadcast_mode", p.rebroadcast_mode)])),
        *channel_steps(reg, cmd, psks),
        Step("telemetry", _sets(cmd, telemetry_settings(reg, node))),
        Step("GPS / position", _sets(cmd, position_settings(reg, node))),
        *([Step("serial", _sets(cmd, serial))] if (serial := serial_settings(node)) else []),
        *([Step("bluetooth", _sets(cmd, bt))] if (bt := bluetooth_settings(node)) else []),
        Step("reboot", cmd + ["--reboot"]),
    ]
