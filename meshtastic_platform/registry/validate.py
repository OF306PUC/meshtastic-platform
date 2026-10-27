"""Registry invariants. The validator matters more than the registry.

A registry without a validator drifts, and every drift here is silent: the
radio keeps transmitting, a receiver keeps hearing it, and the data looks
fine. What breaks is the measurement or the compliance with a power cap, weeks
later.

| #   | Invariant                                                      |
|-----|----------------------------------------------------------------|
| R   | the `radio:` block resolves: region, preset, slot, channels    |
| V1  | node_id unique and shaped '!' + 8 hex; refs/labels unique      |
| V2  | tx_power within the chip's valid settings and the declared     |
|     | EIRP cap, and equal to what the deployment's policy derives    |
| V3  | intervals declare exactly the kinds the node emits             |
| V3b | no environment sensor <=> no 'environment' cadence             |
| V4  | antenna declared, and its band covers the channel              |
| V5  | firmware identical across nodes (receive sensitivity!)         |
| V6  | field: surveyed position present before a node is deployed     |
| V7  | live deployments set channel_num explicitly                    |
| V8  | mcu consistent with hardware                                   |
| I5  | gateway / receiver nodes are CLIENT_MUTE                       |
| C1  | cadence scaling only on the bench, and exact                   |

Errors make a registry unusable; warnings are things still to record or to
look at, and are always printed so nothing is discarded quietly.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from meshtastic_platform.radio import regulatory
from meshtastic_platform.registry import hardware as hw
from meshtastic_platform.registry.model import (
    FUNCTIONS, KINDS, ROLES, SENSOR_TYPES, STATUSES, Node, Registry,
)

NODE_ID_RE = re.compile(r"^![0-9a-f]{8}$")
MAC_RE = re.compile(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
REBROADCAST_MODES = ("ALL", "ALL_SKIP_DECODING", "LOCAL_ONLY", "KNOWN_ONLY", "NONE",
                     "CORE_PORTNUMS_ONLY")
# Firmware limits on channels (ChannelSettings.name is max_size 12, NUL included).
MAX_CHANNEL_INDEX = 7
MAX_CHANNEL_NAME_BYTES = 11


@dataclass(frozen=True)
class Finding:
    level: str        # "error" | "warning"
    code: str
    where: str        # node ref, "meta" or "radio"
    message: str

    def __str__(self) -> str:
        return f"[{self.level.upper():7}] {self.code:<3} {self.where}: {self.message}"


class _Collector:
    def __init__(self):
        self.findings: list[Finding] = []

    def error(self, code, where, msg):
        self.findings.append(Finding("error", code, where, msg))

    def warn(self, code, where, msg):
        self.findings.append(Finding("warning", code, where, msg))


def validate(reg: Registry) -> list[Finding]:
    c = _Collector()
    m = reg.meta
    spec = reg.radio_spec
    live = m.kind in ("field", "bench")

    # ── meta ──────────────────────────────────────────────────────────────────
    if m.kind not in KINDS:
        c.error("M", "meta", f"kind {m.kind!r} not in {KINDS}")
    if reg.path is not None and reg.path.stem != m.deployment:
        c.error("M", "meta", f"deployment {m.deployment!r} does not match the file name "
                             f"{reg.path.name!r}: sessions record the name, so it must be "
                             f"the one --deployment resolves")
    if live:
        if not m.firmware_target:
            c.error("V5", "meta", "firmware_target is required (flashing reads it)")
        elif not VERSION_RE.match(m.firmware_target):
            c.error("V5", "meta", f"firmware_target {m.firmware_target!r} is not X.Y.Z")
    if m.cadence_scale < 1:
        c.error("C1", "meta", f"cadence_scale must be >= 1, got {m.cadence_scale}")
    elif m.cadence_scale != 1 and m.kind != "bench":
        c.error("C1", "meta", "cadence_scale != 1 is only allowed on the bench — "
                              "deliberately saturating a field network is what the bench is for")

    # ── radio ─────────────────────────────────────────────────────────────────
    profile = None
    try:
        profile = reg.radio
    except ValueError as exc:
        c.error("R", "radio", str(exc))
    indexes = [ch.index for ch in spec.channels]
    if len(set(indexes)) != len(indexes):
        c.error("R", "radio", f"duplicate channel index in {indexes}")
    if spec.channels and spec.channels[0].index != 0:
        c.error("R", "radio", "the first channel is the primary and must have index 0")
    if sorted(indexes) != list(range(len(indexes))):
        c.error("R", "radio", f"channel indexes {indexes} must be 0..{len(indexes) - 1} with no "
                              f"gaps: clients misbehave on non-contiguous channels")
    for ch in spec.channels:
        if not 0 <= ch.index <= MAX_CHANNEL_INDEX:
            c.error("R", "radio", f"channel {ch.name!r}: index {ch.index} outside 0..{MAX_CHANNEL_INDEX}")
        if not 0 < len(ch.name.encode()) <= MAX_CHANNEL_NAME_BYTES:
            c.error("R", "radio", f"channel name {ch.name!r} must be 1..{MAX_CHANNEL_NAME_BYTES} "
                                  f"bytes: the firmware truncates a longer one, so radios set "
                                  f"from this file would not match the file")
    if spec.rebroadcast_mode not in REBROADCAST_MODES:
        c.error("R", "radio", f"rebroadcast_mode {spec.rebroadcast_mode!r} not in {REBROADCAST_MODES}")
    if not 0 <= spec.position_precision <= 32:
        c.error("R", "radio", f"position_precision {spec.position_precision} outside 0..32")
    if live and not spec.channel_num:
        note = ""
        if profile is not None:
            note = f" — without it the firmware hashes the channel name to {profile.slot.describe()}"
        c.error("V7", "radio", "channel_num must be explicit for a live deployment" + note)
    if m.kind == "field" and spec.eirp_caps is None:
        c.error("V2", "radio", "eirp_caps must be declared for a field deployment "
                               "(the radiated-power caps where it operates; [] if none apply)")

    # ── per node ──────────────────────────────────────────────────────────────
    seen: dict[str, dict[str, str]] = {"ref": {}, "name": {}, "node_id": {}}
    for n in reg.nodes:
        _node(c, reg, n, profile, seen)

    # ── V5: homogeneous firmware ──────────────────────────────────────────────
    recorded = {n.ref: n.firmware for n in reg.nodes if n.firmware and n.status != "retired"}
    versions = set(recorded.values())
    if len(versions) > 1:
        c.error("V5", "meta", f"mixed firmware {sorted(versions)} ({recorded}): nodes on "
                              f"different versions have different receive sensitivity, "
                              f"a confounder that reads as a propagation effect")
    if m.firmware_target and versions and versions != {m.firmware_target}:
        c.warn("V5", "meta", f"recorded firmware {sorted(versions)} differs from "
                             f"firmware_target {m.firmware_target}")

    mcus = {n.mcu for n in reg.nodes if n.mcu and n.status != "retired"}
    if len(mcus) > 1:
        c.warn("V8", "meta", f"mixed MCU families {sorted(mcus)}: recorded per node and "
                             f"propagated to every reception record — never compare them "
                             f"without grouping by mcu")
    return c.findings


def _node(c: _Collector, reg: Registry, n: Node, profile, seen) -> None:
    m = reg.meta
    r = n.ref
    live = m.kind in ("field", "bench")

    # V1 — identity
    for key, value in (("ref", n.ref), ("name", n.name), ("node_id", n.node_id)):
        if value is None:
            continue
        if value in seen[key]:
            c.error("V1", r, f"{key} {value!r} also used by {seen[key][value]}")
        seen[key][value] = r
    if n.node_id is not None and not NODE_ID_RE.match(n.node_id):
        c.error("V1", r, f"node_id {n.node_id!r} is not '!' + 8 lowercase hex "
                         f"(use null until it is discovered, not a placeholder)")
    if n.mac is not None:
        if not MAC_RE.match(n.mac):
            c.error("V1", r, f"mac {n.mac!r} is not XX:XX:XX:XX:XX:XX")
        elif n.node_id and NODE_ID_RE.match(n.node_id):
            low = "!" + "".join(n.mac.split(":")[2:]).lower()
            if low != n.node_id:
                c.warn("V1", r, f"node_id {n.node_id} is not the low 4 bytes of mac {n.mac} "
                                f"({low}); record the MAC the inspector reports")

    if n.function not in FUNCTIONS:
        c.error("M", r, f"function {n.function!r} not in {FUNCTIONS}")
    if n.status not in STATUSES:
        c.error("M", r, f"status {n.status!r} not in {STATUSES}")
    if n.role not in ROLES:
        c.error("M", r, f"role {n.role!r} is not a Meshtastic device role")
    if not 0 <= n.hop_limit <= 7:
        c.error("M", r, f"hop_limit {n.hop_limit} outside 0..7")

    # X — the PBX record: on pbx radios, and only there
    if n.function == "pbx":
        if n.pbx is None:
            c.error("X", r, "a pbx radio needs its `pbx` block: which PBX drives it")
        elif n.pbx.mcu not in hw.PBX_MCUS:
            c.error("X", r, f"pbx.mcu {n.pbx.mcu!r} not in {hw.PBX_MCUS} "
                            f"(add the part to registry/hardware.py)")
    elif n.pbx is not None:
        c.error("X", r, f"a {n.function} has no PBX: remove the `pbx` block, or make "
                        f"the function pbx")

    # I5 — listen-only sinks
    if n.function in ("gateway", "receiver") and n.role != "CLIENT_MUTE":
        c.error("I5", r, f"a {n.function} must be CLIENT_MUTE (role is {n.role}): "
                         f"if it relays, it contaminates its own measurement")

    # V8 — hardware / mcu
    spec = None
    if n.hardware is not None:
        try:
            spec = hw.get(n.hardware)
        except ValueError as exc:
            c.error("V8", r, str(exc))
    if n.mcu is not None and n.mcu not in hw.MCUS:
        c.error("V8", r, f"mcu {n.mcu!r} not in {sorted(hw.MCUS)}")
    if spec is not None and n.mcu is not None and spec.mcu != n.mcu:
        c.error("V8", r, f"mcu {n.mcu} contradicts hardware {n.hardware} ({spec.mcu})")

    # V3 / V3b — flows declared exactly
    for s in n.sensors:
        if s.type not in SENSOR_TYPES:
            c.error("V3", r, f"sensor type {s.type!r} unknown (have: {sorted(SENSOR_TYPES)})")
    emits_env = "environment" in n.sensor_flows
    declares_env = "environment" in n.intervals
    if declares_env and not emits_env:
        c.error("V3b", r, "declares an 'environment' cadence but carries no environment "
                          "sensor: a delivery estimator would count 100 % loss against a "
                          "cadence the node never had")
    if emits_env and not declares_env:
        c.error("V3b", r, "carries an environment sensor but declares no 'environment' "
                          "cadence: that flow would go unmeasured")

    # C1 — exact cadence scaling
    if m.cadence_scale > 1:
        for kind, secs in n.intervals.items():
            if secs % m.cadence_scale:
                c.error("C1", r, f"{kind} cadence {secs} s is not divisible by "
                                 f"cadence_scale {m.cadence_scale}")

    # V4 — antenna
    a = n.antenna
    if a is None:
        if live and n.status != "retired":
            c.error("V4", r, "antenna is required (its gain decides tx_power)")
    else:
        if not 0 <= a.gain_dbi <= 15:
            c.error("V4", r, f"antenna gain {a.gain_dbi} dBi is implausible (0..15)")
        if a.band_mhz is not None and profile is not None:
            if not (a.band_mhz[0] <= profile.slot.low_mhz and profile.slot.high_mhz <= a.band_mhz[1]):
                c.warn("V4", r, f"antenna band {a.band_mhz[0]:g}–{a.band_mhz[1]:g} MHz does not "
                                f"cover the channel ({profile.slot.low_mhz:.3f}–"
                                f"{profile.slot.high_mhz:.3f} MHz): its gain there is unknown")

    # V2 — transmit power
    if profile is not None and a is not None:
        if n.hardware is None and n.status != "planned":
            c.warn("V2", r, f"hardware not recorded: tx_power checked assuming the "
                            f"{hw.DEFAULT_CHIP} range")
        if n.tx_power_dbm is None:
            if live and n.status != "retired":
                c.error("V2", r, "tx_power_dbm is required: an unset tx_power reads back "
                                 "as the region limit and transmits the chip ceiling")
        else:
            eirp = regulatory.eirp_dbm(n.tx_power_dbm, a.gain_dbi)
            cap = profile.eirp_cap_dbm
            if cap is not None and eirp > cap:
                level = c.warn if m.kind == "historical" else c.error
                level("V2", r, f"EIRP {eirp:g} dBm ({n.tx_power_dbm} dBm + {a.gain_dbi:g} dBi) "
                               f"exceeds the cap ({profile.band.describe()})")
            chip = n.chip
            if not chip.valid(n.tx_power_dbm):
                excl = f" except {sorted(chip.invalid)}" if chip.invalid else ""
                c.error("V2", r, f"tx_power {n.tx_power_dbm} dBm is not a valid {chip.name} "
                                 f"setting ({chip.min_dbm}..{chip.max_dbm}{excl})")
            try:
                expected = reg.expected_tx_power(n)
            except ValueError as exc:
                c.error("V2", r, str(exc))
                expected = None
            if expected is not None and n.tx_power_dbm != expected:
                if m.kind == "bench":
                    why = "a bench runs at the chip minimum: radios on a desk at field power " \
                          "saturate each other"
                elif cap is None:
                    why = f"no EIRP cap declared: the {chip.name} maximum"
                else:
                    why = f"derived from {a.gain_dbi:g} dBi under {profile.band.describe()}"
                c.error("V2", r, f"tx_power_dbm is {n.tx_power_dbm}, policy requires "
                                 f"{expected} ({why})")

    # V6 — position before deployment
    surveyed = n.site.surveyed if n.site else None
    if m.kind == "field" and n.status == "deployed" and surveyed is None:
        c.error("V6", r, "deployed without a surveyed position: no position, no link analysis")

    # Commissioning completeness. A historical record keeps what was never
    # written down as a visible gap, not as a reason to refuse the file.
    if n.status == "deployed":
        level = c.warn if m.kind == "historical" else c.error
        for key in ("node_id", "hardware", "mcu", "firmware"):
            if getattr(n, key) is None:
                level({"node_id": "V1", "firmware": "V5"}.get(key, "V8"),
                      r, f"deployed but {key} is not recorded")
        if n.pbx is not None and n.pbx.firmware is None:
            level("X", r, "deployed but pbx.firmware is not recorded")
    elif n.status == "planned":
        todo = [k for k in ("node_id", "hardware", "mcu", "firmware") if getattr(n, k) is None]
        if n.function == "pbx" and n.pbx is not None and n.pbx.firmware is None:
            todo.append("pbx.firmware")
        if m.kind == "field" and n.function in ("node", "pbx", "gateway"):
            if surveyed is None:
                todo.append("site.surveyed")
            if n.site is None or n.site.antenna_height_m is None:
                todo.append("site.antenna_height_m")
        if todo:
            c.warn("P", r, f"planned; still to record: {', '.join(todo)}")
    if (m.kind == "field" and n.status == "deployed" and n.function in ("node", "pbx", "gateway")
            and (n.site is None or n.site.antenna_height_m is None)):
        c.warn("V6", r, "deployed without antenna_height_m: the link model needs it")


def errors(findings: list[Finding]) -> list[Finding]:
    return [f for f in findings if f.level == "error"]


def shared_channels(registries: list[Registry]) -> list[str]:
    """Live deployments on the same channels, preset AND slot hear each other.

    Expected between alternatives (a field mesh and the bench that rehearses
    it); a problem between two that are on air at the same time and place.
    """
    out = []
    live = [r for r in registries if r.meta.kind in ("field", "bench")]
    for i, a in enumerate(live):
        for b in live[i + 1:]:
            try:
                same = (a.radio.modem_preset, a.radio.slot.channel_num, a.radio.channels) == \
                       (b.radio.modem_preset, b.radio.slot.channel_num, b.radio.channels)
            except ValueError:
                continue
            if same:
                out.append(f"{a.name} and {b.name} share channels, {a.radio.modem_preset} and "
                           f"slot {a.radio.slot.channel_num} ({a.radio.slot.center_mhz:.3f} MHz): "
                           f"they hear each other — never on air at once within range")
    return out


def comparable(a: Registry, b: Registry) -> list[str]:
    """Reasons two deployments' data must not be pooled."""
    reasons = []
    try:
        if a.radio.modem_preset != b.radio.modem_preset:
            reasons.append(f"preset {a.radio.modem_preset} vs {b.radio.modem_preset}")
    except ValueError:
        reasons.append("an invalid radio profile")
    if a.meta.kind != b.meta.kind:
        reasons.append(f"kind {a.meta.kind} vs {b.meta.kind} (bench RSSI does not transfer)")
    fa = {n.firmware for n in a.nodes if n.firmware}
    fb = {n.firmware for n in b.nodes if n.firmware}
    if fa and fb and fa != fb:
        reasons.append(f"firmware {sorted(fa)} vs {sorted(fb)}")
    ma = {n.mcu for n in a.nodes if n.mcu}
    mb = {n.mcu for n in b.nodes if n.mcu}
    if ma and mb and ma != mb:
        reasons.append(f"mcu {sorted(ma)} vs {sorted(mb)}")
    return reasons
