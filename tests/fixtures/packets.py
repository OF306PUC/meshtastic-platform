"""Synthetic MeshPacket dicts, shaped like what the meshtastic library delivers."""

KNOWN_NODE_ID = "!0b64122b"
KNOWN_NODE_NUM = 0x0B64122B
KNOWN_NODE_LABEL = "node-1"
GATEWAY_ID = "!aabbccdd"
GATEWAY_NUM = 0xAABBCCDD

_pkt_id_counter = 0


def next_pkt_id():
    global _pkt_id_counter
    _pkt_id_counter += 1
    return _pkt_id_counter


def _envelope(pkt_id, rssi, snr, hop_limit, hop_start):
    return {
        "fromId": KNOWN_NODE_ID,
        "from": KNOWN_NODE_NUM,
        "id": pkt_id if pkt_id is not None else next_pkt_id(),
        "rxRssi": rssi,
        "rxSnr": snr,
        "hopLimit": hop_limit,
        "hopStart": hop_start,
    }


def private_packet(payload: bytes, pkt_id=None):
    """PRIVATE_APP: an application's own payload, opaque to the platform."""
    pkt = _envelope(pkt_id, -95, 3.5, 2, 3)
    pkt["decoded"] = {"portnum": "PRIVATE_APP", "payload": payload}
    return pkt


def text_packet(payload: bytes, pkt_id=None):
    pkt = private_packet(payload, pkt_id)
    pkt["decoded"]["portnum"] = "TEXT_MESSAGE_APP"
    return pkt


def env_packet(temp=22.5, humidity=55.0, include_humidity=True, pkt_id=None):
    metrics = {"temperature": temp}
    if include_humidity:
        metrics["relativeHumidity"] = humidity
    pkt = _envelope(pkt_id, -85, 7.5, 3, 5)
    pkt["decoded"] = {
        "portnum": "TELEMETRY_APP",
        "telemetry": {"time": 1700000000, "environmentMetrics": metrics},
    }
    return pkt


def device_packet(pkt_id=None):
    pkt = _envelope(pkt_id, -90, 5.0, 2, 4)
    pkt["decoded"] = {
        "portnum": "TELEMETRY_APP",
        "telemetry": {
            "time": 1700000001,
            "deviceMetrics": {
                "batteryLevel": 85,
                "voltage": 3.95,
                "channelUtilization": 0.12,
                "airUtilTx": 0.05,
                "uptimeSeconds": 3600,
            },
        },
    }
    return pkt


def position_packet(include_altitude=True, pkt_id=None):
    pos = {"latitude": -33.4489, "longitude": -70.6693, "time": 1700000002}
    if include_altitude:
        pos["altitude"] = 567
    pkt = _envelope(pkt_id, -80, 9.0, 1, 3)
    pkt["decoded"] = {"portnum": "POSITION_APP", "position": pos}
    return pkt
