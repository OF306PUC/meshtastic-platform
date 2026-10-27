"""Which radio is on the port, and may this registry entry be applied to it?

A badly provisioned node does not fail loudly: it transmits, the gateway hears
it, the data looks fine. So before writing anything, provisioning settles
three things and STOPS on any doubt rather than improvising:

* identity — the device's node_id against the registry entry. A placeholder
  (null) entry is being commissioned; a different real id means either another
  device is on the port or the registry is wrong. Never overwrite either way.
* platform — MCU family and hardware model against the entry. An ESP32 where
  the registry says nrf52840 is a bench LILYGO plugged in instead of a field
  node, and field power would go onto a desk.
* firmware — against meta.firmware_target. Mixed firmware means mixed receive
  sensitivity (the 0x8B5 patch); flashing is a separate, documented procedure.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass

from meshtastic_platform.registry import hardware as hw
from meshtastic_platform.registry.model import Node, Registry


@dataclass(frozen=True)
class DeviceIdentity:
    node_id: str | None
    node_num: int | None
    hw_model: str | None
    has_wifi: bool | None
    firmware: str | None          # full string, e.g. "2.7.26.54e0d8d"
    mac: str | None

    @property
    def firmware_version(self) -> str | None:
        """X.Y.Z without the commit hash."""
        if not self.firmware:
            return None
        return ".".join(self.firmware.split(".")[:3])


def mac_from_nodeinfo(user: dict) -> str | None:
    raw = user.get("macaddr")
    if not raw:
        return None
    try:
        b = base64.b64decode(raw)
    except Exception:
        return None
    return ":".join(f"{x:02X}" for x in b) if len(b) == 6 else None


def read_identity(iface) -> DeviceIdentity:
    """Extract identity from an open meshtastic SerialInterface."""
    info = iface.getMyNodeInfo() or {}
    user = info.get("user", {}) or {}
    meta = getattr(iface, "metadata", None)
    firmware = getattr(meta, "firmware_version", None) or None
    has_wifi = getattr(meta, "hasWifi", None) if meta is not None else None
    return DeviceIdentity(
        node_id=user.get("id"),
        node_num=info.get("num"),
        hw_model=user.get("hwModel"),
        has_wifi=has_wifi,
        firmware=firmware,
        mac=mac_from_nodeinfo(user),
    )


def preflight(dev: DeviceIdentity, reg: Registry, node: Node,
              others: list[Registry] = ()) -> tuple[list[str], list[str]]:
    """(blocking problems, notes). Provisioning proceeds only with no problems."""
    problems, notes = [], []

    # identity
    if node.node_id is None:
        owner = reg.by_node_id(dev.node_id) if dev.node_id else None
        if owner is not None:
            problems.append(f"device {dev.node_id} is already registered as {owner.ref} in "
                            f"{reg.name}; refusing to provision it as {node.ref}")
        else:
            notes.append(f"commissioning {node.ref}: record node_id {dev.node_id!r}"
                         + (f" and mac {dev.mac!r}" if dev.mac else "")
                         + f" in {reg.path or reg.name}")
    elif dev.node_id != node.node_id:
        problems.append(f"device on the port is {dev.node_id}, but {node.ref} is "
                        f"{node.node_id} in {reg.name}: another device, or a wrong registry. "
                        f"Not overwriting either.")
    for other in others:
        if other.name == reg.name or not dev.node_id:
            continue
        theirs = other.by_node_id(dev.node_id)
        if theirs is not None and theirs.ref != node.ref:
            problems.append(f"device {dev.node_id} is {theirs.ref} in deployment {other.name} "
                            f"({other.meta.kind}); refusing to apply {reg.name}'s {node.ref} "
                            f"({reg.meta.kind}) to it")

    # platform
    if node.mcu is not None and dev.has_wifi is not None:
        expected_wifi = hw.MCUS[node.mcu]["has_wifi"]
        if dev.has_wifi != expected_wifi:
            problems.append(f"{node.ref} is {node.mcu} in the registry, but the device "
                            f"{'has' if dev.has_wifi else 'lacks'} WiFi "
                            f"({'esp32' if dev.has_wifi else 'nrf52840'}): wrong device on the port")
    spec = node.hardware_spec
    if spec is not None and dev.hw_model and dev.hw_model != spec.hw_model:
        problems.append(f"{node.ref} is {spec.name} ({spec.hw_model}) in the registry, but "
                        f"the device reports {dev.hw_model}")
    if spec is None and dev.hw_model:
        guess = [h.name for h in hw.CATALOGUE.values() if h.hw_model == dev.hw_model]
        if len(guess) == 1:
            hint = f": record hardware {guess[0]!r}"
        elif guess:
            hint = f": record one of {guess} (the transceiver tells them apart)"
        else:
            hint = " (not in the hardware catalogue)"
        notes.append(f"device reports {dev.hw_model}{hint}")

    # firmware
    target = reg.meta.firmware_target
    if target and dev.firmware_version and dev.firmware_version != target:
        problems.append(f"device runs firmware {dev.firmware} but the deployment targets "
                        f"{target}: flash first (docs/flashing.md) — mixed firmware is mixed "
                        f"receive sensitivity")
    elif dev.firmware_version and node.firmware is None:
        notes.append(f"record measured firmware {dev.firmware_version!r} for {node.ref}")
    return problems, notes
