"""Meshtastic node & mesh inspector — the deployment's smoke test.

    python configure.py inspect -d <deployment> [--port P] [--node <ref>] [--no-mesh]

Connects to a node over serial and reports, in one pass:

  1. Local node     identity, hardware, firmware, MAC (to record), telemetry,
                    position (with the quantization detector).
  2. Device config  every setting provisioning touches, read back from the node.
  3. Radio          region / preset / slot / rebroadcast / channels / PSKs /
                    position_precision vs the deployment's radio block, and
                    no channel the deployment does not declare. PSKs are
                    compared, never printed.
  4. Registry       the local node vs its registry entry: role, hop_limit,
                    tx_power (derived) and EIRP vs the declared cap, cadences
                    (the PDR estimator's denominators), sensors vs environment
                    telemetry, GPS vs declared position flow, smart position
                    and fixed_position off, firmware, hardware model.
  5. Mesh           every node this device has heard, cross-checked against
                    the registry.

Exit code is 1 when any drift is found, 2 when the inspection could not run,
0 when the node is healthy — it must exit NON-ZERO on drift, because it is the
smoke test the deployment is accepted on. The checks are pure functions over
a Snapshot, so they are tested without a radio.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from meshtastic_platform.provision.identity import DeviceIdentity, mac_from_nodeinfo
from meshtastic_platform.provision.plan import GPS_UPDATE_INTERVAL_S, serial_settings
from meshtastic_platform.radio import profile as radio_profile
from meshtastic_platform.radio import regulatory
from meshtastic_platform.registry import hardware as hw
from meshtastic_platform.registry.model import Node, Registry

NA = "n/a"   # a field this firmware/library version does not have

# (section, field, is_enum) read from localConfig / moduleConfig.
LOCAL_FIELDS = [
    ("device", "role", True), ("device", "rebroadcast_mode", True),
    ("lora", "region", True), ("lora", "modem_preset", True), ("lora", "use_preset", False),
    ("lora", "channel_num", False), ("lora", "hop_limit", False), ("lora", "tx_power", False),
    ("lora", "sx126x_rx_boosted_gain", False), ("lora", "override_frequency", False),
    ("bluetooth", "enabled", False),
    ("position", "gps_mode", True), ("position", "gps_update_interval", False),
    ("position", "position_broadcast_secs", False),
    ("position", "position_broadcast_smart_enabled", False), ("position", "fixed_position", False),
]
MODULE_FIELDS = [
    ("telemetry", "device_telemetry_enabled", False),
    ("telemetry", "device_update_interval", False),
    ("telemetry", "environment_measurement_enabled", False),
    ("telemetry", "environment_update_interval", False),
    ("serial", "enabled", False), ("serial", "mode", True), ("serial", "txd", False),
    ("serial", "rxd", False), ("serial", "baud", True), ("serial", "timeout", False),
]


# ── Small helpers ─────────────────────────────────────────────────────────────

def enum_name(msg, name: str) -> str:
    """Symbolic name of a protobuf enum field via reflection (survives library moves)."""
    try:
        value = getattr(msg, name)
        enum_type = msg.DESCRIPTOR.fields_by_name[name].enum_type
        return enum_type.values_by_number[value].name
    except Exception:
        return str(getattr(msg, name, "?"))


def read_field(msg, name: str):
    """A protobuf field, or 'n/a' if this firmware/library version lacks it."""
    try:
        return getattr(msg, name)
    except Exception:
        return NA


def human_age(last_heard, now: float | None = None) -> str:
    """Render a lastHeard epoch (seconds) as a compact age like '3m ago'."""
    if not last_heard:
        return "never"
    delta = max(0, int(now if now is not None else time.time()) - int(last_heard))
    if delta < 60:
        return f"{delta}s ago"
    if delta < 3600:
        return f"{delta // 60}m ago"
    if delta < 86400:
        return f"{delta // 3600}h ago"
    return f"{delta // 86400}d ago"


def trailing_zero_bits(deg: float) -> int:
    """Count the zero low bits of a coordinate in Meshtastic's int32 encoding.

    Positions travel as int32 in units of 1e-7 degrees, and position_precision
    keeps only the top N bits — so a precision-reduced coordinate is an exact
    multiple of 2**(32-N) and the mask is visible in the value itself. A
    full-precision GPS reading has effectively random low bits.
    """
    units = round(abs(deg) * 1e7)
    if units == 0:                       # 0.0 is "no fix", not "quantized"
        return 0
    return (units & -units).bit_length() - 1


def quantization(lat, lon) -> tuple[int, float] | None:
    """(effective precision, grid km) if both coordinates sit on a >= 2**8 grid.

    8 shared zero low bits happen by chance once in ~65k; that is a mask.
    """
    if lat is None or lon is None:
        return None
    tz = min(trailing_zero_bits(lat), trailing_zero_bits(lon))
    if tz < 8:
        return None
    return 32 - tz, (1 << tz) * 1e-7 * 111.32


def fmt(value, unit: str = "") -> str:
    return "?" if value is None else f"{value}{unit}"


# ── Snapshot: everything read from the radio, once ────────────────────────────

@dataclass
class Snapshot:
    identity: DeviceIdentity
    long_name: str | None = None
    metrics: dict = field(default_factory=dict)
    position: dict = field(default_factory=dict)
    snr: float | None = None
    config: dict[str, Any] = field(default_factory=dict)          # "lora.region" -> "ANZ"
    channels: list[dict] = field(default_factory=list)             # idx, name, psk, precision
    mesh: dict[str, dict] = field(default_factory=dict)            # iface.nodes

    def get(self, key: str):
        return self.config.get(key, NA)


def snapshot(iface) -> Snapshot:
    info = iface.getMyNodeInfo() or {}
    user = info.get("user", {}) or {}
    meta = getattr(iface, "metadata", None)
    ident = DeviceIdentity(
        node_id=user.get("id"), node_num=info.get("num"), hw_model=user.get("hwModel"),
        has_wifi=getattr(meta, "hasWifi", None) if meta is not None else None,
        firmware=(getattr(meta, "firmware_version", None) or None) if meta is not None else None,
        mac=mac_from_nodeinfo(user),
    )
    snap = Snapshot(identity=ident, long_name=user.get("longName"),
                    metrics=info.get("deviceMetrics", {}) or {},
                    position=info.get("position", {}) or {}, snr=info.get("snr"),
                    mesh=dict(getattr(iface, "nodes", None) or {}))
    for source, fields_ in (("localConfig", LOCAL_FIELDS), ("moduleConfig", MODULE_FIELDS)):
        try:
            root = getattr(iface.localNode, source)
        except Exception:
            continue
        for section, name, is_enum in fields_:
            msg = read_field(root, section)
            if msg == NA:
                snap.config[f"{section}.{name}"] = NA
            else:
                snap.config[f"{section}.{name}"] = enum_name(msg, name) if is_enum else read_field(msg, name)
    try:
        for idx, ch in enumerate(iface.localNode.channels or []):
            s = ch.settings
            snap.channels.append({"idx": idx, "name": s.name, "psk": bytes(s.psk),
                                  "precision": s.module_settings.position_precision,
                                  "enabled": int(ch.role) != 0})     # 0 = Channel.Role.DISABLED
    except Exception:
        pass
    return snap


# ── Checks (pure) ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Check:
    section: str
    label: str
    expected: Any
    actual: Any
    ok: bool
    note: str = ""
    secret: bool = False      # compare, never print the values

    def line(self) -> str:
        mark = "OK " if self.ok else "MISMATCH"
        if self.secret:
            body = "matches .env" if self.ok else "differs from .env"
        else:
            body = f"expected={self.expected} actual={self.actual}"
        return f"  [{mark}] {self.label}: {body}" + (f"  — {self.note}" if self.note and not self.ok else "")


def _eq(section, label, expected, actual, note="") -> Check | None:
    """A Check, or None when the radio does not have the field (version drift)."""
    if actual == NA:
        return None
    return Check(section, label, expected, actual, expected == actual, note)


def check_radio(s: Snapshot, reg: Registry, psks: dict[int, str] | None) -> list[Check]:
    p = reg.radio
    out = [
        _eq("radio", "region", p.region, s.get("lora.region")),
        _eq("radio", "modem_preset", p.modem_preset, s.get("lora.modem_preset")),
        _eq("radio", "channel_num", p.channel_num_setting, s.get("lora.channel_num"),
            f"the slot sets the frequency, and the frequency sets the power cap ({p.slot.describe()})"),
        _eq("radio", "rebroadcast_mode", p.rebroadcast_mode, s.get("device.rebroadcast_mode")),
    ]
    by_idx = {c["idx"]: c for c in s.channels if c["enabled"]}
    for channel in p.channels:
        idx, name = channel.index, channel.name
        ch = by_idx.get(idx)
        if ch is None:
            out.append(Check("radio", f"channel {idx}", name, "missing", False))
            continue
        out.append(_eq("radio", f"channel {idx} name", name, ch["name"]))
        if psks is not None:
            try:
                ok = ch["psk"] == radio_profile.decode_psk(psks[idx])
            except Exception:
                ok = False
            out.append(Check("radio", f"channel {idx} PSK", None, None, ok, secret=True))
        # Per-channel and applied by the SENDER: `--info` omits it while it holds
        # the firmware default, so reading it back is the only way to confirm.
        out.append(_eq("radio", f"channel {idx} position_precision", p.position_precision,
                       ch["precision"]))
    declared = {ch.index for ch in p.channels}
    for idx, ch in sorted(by_idx.items()):
        if idx not in declared:
            out.append(Check("radio", f"channel {idx}", "none", ch["name"], False,
                             f"not in the deployment (left by an earlier configuration?): "
                             f"meshtastic --ch-index {idx} --ch-del"))
    return [c for c in out if c is not None]


def check_local(s: Snapshot, reg: Registry, node: Node | None, *, ref: str | None = None) -> list[Check]:
    dev = s.identity
    if node is None:
        target = None
        if ref is not None:
            try:
                target = reg.by_ref(ref)
            except KeyError:
                target = None
        if target is not None and target.node_id is None:
            note = f"{ref} has no node_id yet: record {dev.node_id!r} in {reg.path or reg.name}"
        else:
            note = f"not in deployment {reg.name}: wrong device, or the registry is incomplete"
        return [Check("registry", "local node in registry", "registered", dev.node_id, False, note)]

    out: list[Check | None] = []
    iv = reg.intervals(node)
    p = reg.radio
    r = node.ref

    out.append(_eq("registry", f"{r} role", node.role, s.get("device.role")))
    out.append(_eq("registry", f"{r} hop_limit", node.hop_limit, s.get("lora.hop_limit")))

    # Transmit power: derived, and EIRP under the cap.
    configured = s.get("lora.tx_power")
    expected_tx = reg.expected_tx_power(node)
    if configured != NA and expected_tx is not None:
        unset = configured in (0, regulatory.get_region(p.region).power_limit_dbm)
        out.append(_eq("registry", f"{r} lora.tx_power", expected_tx, configured,
                       "unset: the firmware wrote its region default and transmits the chip "
                       "ceiling" if unset else "provision it: tx_power is derived, not chosen"))
    if configured != NA and node.antenna is not None:
        effective = regulatory.effective_tx_power(configured, regulatory.get_region(p.region), node.chip)
        eirp = regulatory.eirp_dbm(effective, node.antenna.gain_dbi)
        # The slot the radio is ACTUALLY on decides the cap, not the planned one.
        try:
            actual_slot = regulatory.resolve_slot(p.region, p.modem_preset,
                                                  s.get("lora.channel_num") or None,
                                                  p.primary_channel.name)
            band = regulatory.eirp_cap(actual_slot, p.spec.eirp_caps or ())
        except (ValueError, TypeError):
            band = p.band
        if band is not None:
            out.append(Check("registry", f"{r} EIRP vs cap ({band.describe()})",
                             f"<= {band.eirp_dbm:g} dBm", f"{eirp:g} dBm", eirp <= band.eirp_dbm,
                             f"{effective} dBm effective + {node.antenna.gain_dbi:g} dBi: over "
                             f"the legal cap — fix tx_power before this node transmits again"))

    # Cadences: the PDR estimator's denominators (I2).
    for kind, key in (("device", "telemetry.device_update_interval"),
                      ("environment", "telemetry.environment_update_interval"),
                      ("position", "position.position_broadcast_secs")):
        if kind in iv:
            out.append(_eq("registry", f"{r} {key}", iv[kind], s.get(key),
                           "the estimator measures against the registry value: losses "
                           "would be phantom or hidden"))
    out.append(_eq("registry", f"{r} telemetry.device_telemetry_enabled", "device" in iv,
                   s.get("telemetry.device_telemetry_enabled")))
    out.append(_eq("registry", f"{r} telemetry.environment_measurement_enabled",
                   "environment" in node.sensor_flows, s.get("telemetry.environment_measurement_enabled"),
                   "sensors and the environment flow must agree (V3)"))
    gps = s.get("position.gps_mode")
    if gps != NA:
        want = "ENABLED" if "position" in iv else "DISABLED"
        out.append(Check("registry", f"{r} position.gps_mode", want, gps, gps == want,
                         "GPS on without a declared position cadence broadcasts a flow no "
                         "estimator expects" if want == "DISABLED" else ""))
    if "position" in iv and node.function in GPS_UPDATE_INTERVAL_S:
        out.append(_eq("registry", f"{r} position.gps_update_interval",
                       GPS_UPDATE_INTERVAL_S[node.function], s.get("position.gps_update_interval")))
    out.append(_eq("registry", f"{r} position_broadcast_smart_enabled", False,
                   s.get("position.position_broadcast_smart_enabled"),
                   "movement-triggered packets break the cadence hypothesis (I4)"))
    out.append(_eq("registry", f"{r} position.fixed_position", False, s.get("position.fixed_position"),
                   "the node reports a fixed position instead of its GPS fix (I3)"))
    if node.chip.name == "sx1262":
        out.append(_eq("registry", f"{r} lora.sx126x_rx_boosted_gain", p.rx_boosted_gain,
                       s.get("lora.sx126x_rx_boosted_gain")))

    # No serial module, except on a pbx radio: its link is the PBX project's.
    for key, want in serial_settings(node):
        out.append(_eq("registry", f"{r} {key}", want == "true", s.get(key),
                       "a serial module left on from an earlier configuration"))

    # Firmware (V5) and platform (V8).
    version = dev.firmware_version
    if version:
        if node.firmware is not None:
            out.append(Check("registry", f"{r} firmware vs registry", node.firmware, version,
                             node.firmware == version, "update the registry with the MEASURED version"))
        else:
            out.append(Check("registry", f"{r} firmware recorded", version, None, False,
                             f"record firmware {version!r}"))
        if reg.meta.firmware_target:
            out.append(Check("registry", f"{r} firmware vs target", reg.meta.firmware_target, version,
                             version == reg.meta.firmware_target, "flash (docs/flashing.md)"))
    spec = node.hardware_spec
    if spec is not None and dev.hw_model:
        out.append(Check("registry", f"{r} hardware model", spec.hw_model, dev.hw_model,
                         spec.hw_model == dev.hw_model))
    if node.mcu is not None and dev.has_wifi is not None:
        want_wifi = hw.MCUS[node.mcu]["has_wifi"]
        out.append(Check("registry", f"{r} mcu family", node.mcu,
                         "esp32" if dev.has_wifi else "nrf52840", dev.has_wifi == want_wifi))
    return [c for c in out if c is not None]


def check_mesh(s: Snapshot, reg: Registry) -> tuple[list[Check], list[tuple]]:
    """(issues, table rows) for the mesh node database."""
    me = s.identity.node_id
    known = reg.known_nodes()
    out, rows = [], []
    for nid, node in sorted(s.mesh.items(), key=lambda kv: (kv[1].get("hopsAway", 99), kv[0])):
        user = node.get("user", {}) or {}
        entry = known.get(nid)
        label = entry.ref if entry else ("self" if nid == me else "-")
        role = user.get("role", "CLIENT")     # omitted from NodeInfo when it is the default
        rows.append((label, nid, role, node.get("hopsAway"),
                     (node.get("deviceMetrics", {}) or {}).get("batteryLevel"),
                     node.get("snr"), node.get("lastHeard")))
        if entry is not None and role != entry.role:
            out.append(Check("mesh", f"{entry.ref} ({nid}) role", entry.role, role, False))
        # Remote positions arrived over the air, so they have been through the
        # SENDER's precision mask: this is the reading that exposes a node still
        # on a reduced position_precision.
        pos = node.get("position", {}) or {}
        q = quantization(pos.get("latitude"), pos.get("longitude"))
        if nid != me and q is not None:
            out.append(Check("mesh", f"{label} ({nid}) position precision",
                             reg.radio.position_precision, q[0], False,
                             f"coordinates quantized to ~{q[1]:.2f} km — reprovision that node"))
    for nid, entry in known.items():
        if nid not in s.mesh and nid != me and entry.status == "deployed":
            out.append(Check("mesh", f"expected node {entry.ref} ({nid})", "present", "absent",
                             False, "offline, out of range, or never heard"))
    for nid in s.mesh:
        if nid not in known and nid != me:
            out.append(Check("mesh", f"node {nid}", "in registry", "unknown", False,
                             f"not in deployment {reg.name}"))
    return out, rows


# ── Printing ──────────────────────────────────────────────────────────────────

def print_local(s: Snapshot, node: Node | None, precision: int) -> list[Check]:
    d = s.identity
    m = s.metrics
    print("=== Local node ===")
    print(f"  Registry ref : {node.ref if node else '(not in registry)'}")
    print(f"  Node ID      : {d.node_id}   (num={d.node_num})")
    print(f"  MAC          : {d.mac or '?'}")
    print(f"  Long name    : {s.long_name or '?'}")
    print(f"  Hardware     : {d.hw_model or '?'}   (WiFi: {d.has_wifi})")
    print(f"  Firmware     : {d.firmware or '?'}")
    print("  Telemetry:")
    print(f"    Battery      : {fmt(m.get('batteryLevel'), '%')}")
    v = m.get("voltage")
    print(f"    Voltage      : {fmt(round(v, 2) if v is not None else None, ' V')}")
    cu, au = m.get("channelUtilization"), m.get("airUtilTx")
    print(f"    Channel util : {fmt(round(cu, 1) if cu is not None else None, '%')}")
    print(f"    Air util TX  : {fmt(round(au, 1) if au is not None else None, '%')}")
    up = m.get("uptimeSeconds")
    print(f"    Uptime       : {fmt(up // 3600 if up else up, 'h' if up else '')}")
    print(f"    SNR (last rx): {fmt(s.snr, ' dB')}")
    issues = []
    lat, lon = s.position.get("latitude"), s.position.get("longitude")
    if lat is not None and lon is not None:
        print(f"    Position     : {lat:.7f}, {lon:.7f} (alt {fmt(s.position.get('altitude'), ' m')})")
        q = quantization(lat, lon)
        if q is not None:
            # This is the node's OWN position, pre-mask: a clean reading here is
            # NOT proof the setting works. The over-the-air evidence is in the
            # remote entries of the mesh section.
            issues.append(Check("local", "own position precision", precision,
                                q[0], False, f"quantized to ~{q[1]:.2f} km"))
    else:
        print("    Position     : (no fix)")
    print()
    return issues


def print_config(s: Snapshot) -> None:
    print("=== Device configuration (as read from the node) ===")
    for key, value in s.config.items():
        print(f"  {key:<44}: {value}")
    print()


def print_checks(title: str, checks: list[Check]) -> None:
    print(f"=== {title} ===")
    for c in checks:
        print(c.line())
    print()


def print_mesh(rows: list[tuple], now: float | None = None) -> None:
    print("=== Mesh node database ===")
    header = f"  {'ref':<6} {'id':<11} {'role':<12} {'hops':>4} {'batt':>5} {'snr':>7} {'last heard':>12}"
    print(header)
    print("  " + "-" * (len(header) - 2))
    for label, nid, role, hops, batt, snr, heard in rows:
        print(f"  {label:<6} {nid:<11} {role:<12} {fmt(hops):>4} {fmt(batt, '%'):>5} "
              f"{fmt(snr, 'dB'):>7} {human_age(heard, now):>12}")
    print()


# ── Entry point ───────────────────────────────────────────────────────────────

def resolve_port(explicit_port):
    """The serial port to use; refuses to guess between several devices."""
    if explicit_port:
        return explicit_port
    try:
        from meshtastic.util import findPorts
        ports = findPorts()
    except Exception as exc:
        print(f"ERROR: could not auto-detect a port ({exc}). Pass --port explicitly.")
        return None
    if not ports:
        print("ERROR: no Meshtastic device found. Plug one in or pass --port.")
        return None
    if len(ports) > 1:
        print("Multiple Meshtastic devices found; pass --port to choose one:")
        for p in ports:
            print(f"  {p}")
        return None
    print(f"Auto-detected port: {ports[0]}")
    return ports[0]


def inspect(reg: Registry, port: str | None, *, ref: str | None = None,
            mesh: bool = True) -> int:
    port = resolve_port(port)
    if port is None:
        return 2
    import meshtastic.serial_interface
    try:
        iface = meshtastic.serial_interface.SerialInterface(port)
    except Exception as exc:
        print(f"ERROR: could not open {port}: {exc}")
        return 2
    try:
        snap = snapshot(iface)
    finally:
        iface.close()
    try:
        psks = radio_profile.channel_psks(reg.radio)
    except RuntimeError as exc:
        print(f"WARNING: {exc} PSKs are not being checked.")
        psks = None
    return report(snap, reg, psks, ref=ref, mesh=mesh)


def report(snap: Snapshot, reg: Registry, psks, *, ref=None, mesh=True) -> int:
    print(f"Deployment: {reg.name} ({reg.path}) — {reg.radio.describe()}\n")
    node = reg.by_node_id(snap.identity.node_id) if snap.identity.node_id else None
    issues = print_local(snap, node, reg.radio.position_precision)
    print_config(snap)
    radio = check_radio(snap, reg, psks)
    print_checks("Radio (vs the deployment's radio block)", radio)
    local = check_local(snap, reg, node, ref=ref)
    print_checks("Registry (local node vs its entry)", local)
    print("  Note: lora.tx_power is what the radio was TOLD. The real figure is the\n"
          "  'Final Tx power: N dBm' line on its console at boot.\n")
    mesh_issues = []
    if mesh:
        mesh_issues, rows = check_mesh(snap, reg)
        print_mesh(rows)
    issues += [c for c in radio + local + mesh_issues if not c.ok]
    if issues:
        print("=== Issues found ===")
        for c in issues:
            body = "" if c.secret else f" (expected {c.expected}, got {c.actual})"
            print(f"  ! {c.section}: {c.label}{body}" + (f" — {c.note}" if c.note else ""))
        print(f"\n{len(issues)} issue(s) detected.")
        return 1
    print("=== Node healthy: no drift or mismatch detected. ===")
    return 0

