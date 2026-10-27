"""One reception, as the channel study records it.

decode() is pure and does not know the clock, so a reception is the decoded
packet PLUS what only the receiver knows: when it arrived, in which session,
whether it repeats a packet already heard, and on which radio it was heard.

The registry facts of BOTH ends travel with every record (transmitter as tx_*,
receiving radio as rx_*). Without them the antenna and sensor analyses have to
be rebuilt by joining on timestamps, which fails silently every time someone
swaps an antenna and does not update the YAML; a link with different antennas
at each end depends on both.
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from typing import Any

from meshtastic_platform.decode import DecodedPacket
from meshtastic_platform.registry.model import Node

COMMON = [
    "received_at", "time_local", "run_id", "deployment", "ref", "node_id", "kind",
    "portnum", "packet_id", "duplicate", "own", "hops", "hop_start", "hop_limit",
    "relay_node", "rssi", "snr", "channel", "rx_time", "payload_len",
]
TX = ["tx_function", "tx_hardware", "tx_mcu", "tx_firmware", "tx_antenna_type", "tx_antenna_gain_dbi",
      "tx_power_dbm", "tx_sensors", "tx_antenna_height_m"]
RX = ["rx_ref", "rx_hardware", "rx_mcu", "rx_firmware", "rx_antenna_type",
      "rx_antenna_gain_dbi", "rx_antenna_height_m"]
PAYLOAD = {
    "device": ["battery_level", "voltage", "channel_utilization", "air_util_tx",
               "uptime_seconds", "device_ts"],
    "environment": ["temperature", "relative_humidity", "device_ts"],
    "position": ["latitude", "longitude", "altitude", "precision_bits", "device_ts"],
    "text": ["text"],
    "private": [],              # an application's own payload: only its size is recorded
}
# Kinds recorded as per-(node, kind) tables. Everything else is in the JSONL
# sink and in the decode counters, never silently gone.
TABLE_KINDS = tuple(PAYLOAD)


def columns(kind: str) -> list[str]:
    """The stable header for one kind: the same columns whatever a packet carried."""
    return COMMON + TX + RX + PAYLOAD[kind]


@dataclass(frozen=True)
class Reception:
    decoded: DecodedPacket
    received_at: float          # wall clock, unix seconds (injected)
    run_id: str
    deployment: str
    ref: str                    # registry ref, or the node id for unknown senders
    duplicate: bool = False     # same (sender, packet id) already heard this session
    own: bool = False           # the receiving radio's own packet (e.g. its GPS track)
    rx_node: Node | None = None
    capture_content: bool = False

    @property
    def kind(self) -> str:
        return self.decoded.kind

    def record(self) -> dict[str, Any]:
        d = self.decoded
        rec: dict[str, Any] = {
            "received_at": round(self.received_at, 3),
            "time_local": _dt.datetime.fromtimestamp(self.received_at).isoformat(timespec="seconds"),
            "run_id": self.run_id,
            "deployment": self.deployment,
            "ref": self.ref,
            "node_id": d.from_id,
            "kind": d.kind,
            "portnum": d.portnum,
            "packet_id": d.packet_id,
            "duplicate": int(self.duplicate),
            "own": int(self.own),
            "hops": d.hops_taken,
            "hop_start": d.hop_start,
            "hop_limit": d.hop_limit,
            "relay_node": d.relay_node,
            "rssi": d.rx_rssi,
            "snr": d.rx_snr,
            "channel": d.channel,
            "rx_time": d.rx_time,
            "payload_len": d.payload_len,
        }
        tx = d.node.record_fields("tx_") if isinstance(d.node, Node) else {}
        for key in TX:
            rec[key] = tx.get(key)
        rx = self.rx_node.record_fields("rx_") if self.rx_node is not None else {}
        for key in RX:
            rec[key] = rx.get(key)
        rec.update(self._payload())
        return rec

    def _payload(self) -> dict[str, Any]:
        d = self.decoded
        out: dict[str, Any] = {}
        if d.device is not None:
            m = d.device
            out.update(battery_level=m.battery_level, voltage=m.voltage,
                       channel_utilization=m.channel_utilization, air_util_tx=m.air_util_tx,
                       uptime_seconds=m.uptime_seconds, device_ts=m.device_ts)
        if d.environment is not None:
            m = d.environment
            out.update(temperature=m.temperature, relative_humidity=m.relative_humidity,
                       device_ts=m.device_ts)
        if d.position is not None:
            p = d.position
            out.update(latitude=p.latitude, longitude=p.longitude, altitude=p.altitude,
                       precision_bits=p.precision_bits, device_ts=p.device_ts)
        if d.kind == "text" and d.text is not None:
            # Message bodies are opt-in: they may be real people's traffic.
            out["text"] = d.text.text if self.capture_content else None
        return out
