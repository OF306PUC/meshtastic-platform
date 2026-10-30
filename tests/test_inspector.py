"""The inspector: it must exit NON-ZERO on drift (I7) — it is the deployment's smoke test.

The checks are pure functions over a Snapshot, so every drift is built by hand
from a healthy snapshot and shown to be caught.
"""
import contextlib
import io
import unittest

from meshtastic_platform.provision import inspector as insp
from meshtastic_platform.provision.identity import DeviceIdentity
from meshtastic_platform.radio.profile import decode_psk
from meshtastic_platform.registry import parse
from tests.test_registry import field_registry, pbx_radio

PSKS = {0: "base64:AQIDBA==", 1: "base64:BQYHCA=="}


def registry():
    data = field_registry()
    data["nodes"][0].update(node_id="!0b64122b", firmware="2.7.26")    # N1: fiber + SHT4X
    data["nodes"][1].update(node_id="!7c70da02", status="deployed", firmware="2.7.26",
                            site={"surveyed": {"lat": -27.16785, "lon": -109.4189}})
    return parse(data)


def healthy(**config):
    cfg = {
        "device.role": "CLIENT", "device.rebroadcast_mode": "LOCAL_ONLY",
        "lora.region": "ANZ", "lora.modem_preset": "MEDIUM_FAST", "lora.use_preset": True,
        "lora.channel_num": 45, "lora.hop_limit": 1, "lora.tx_power": 22,
        "lora.sx126x_rx_boosted_gain": True, "lora.override_frequency": 0.0,
        "bluetooth.enabled": True, "serial.enabled": False,
        "position.gps_mode": "ENABLED", "position.gps_update_interval": 3600,
        "position.position_broadcast_secs": 600,
        "position.position_broadcast_smart_enabled": False, "position.fixed_position": False,
        "telemetry.device_telemetry_enabled": True, "telemetry.device_update_interval": 120,
        "telemetry.environment_measurement_enabled": True,
        "telemetry.environment_update_interval": 120,
    }
    cfg.update(config)
    return insp.Snapshot(
        identity=DeviceIdentity("!0b64122b", 0x0B64122B, "SEEED_SOLAR_NODE", False,
                                "2.7.26.54e0d8d", "AA:BB:0B:64:12:2B"),
        config=cfg,
        channels=[{"idx": 0, "name": "chPrimary", "psk": decode_psk(PSKS[0]), "precision": 32,
                   "enabled": True},
                  {"idx": 1, "name": "chSecondary", "psk": decode_psk(PSKS[1]), "precision": 32,
                   "enabled": True},
                  *({"idx": i, "name": "", "psk": b"", "precision": 0, "enabled": False}
                    for i in range(2, 8))],
        mesh={"!0b64122b": {"user": {"role": "CLIENT"}},
              "!7c70da02": {"user": {"role": "CLIENT"}, "position": {"latitude": -27.1678528,
                                                                      "longitude": -109.4189}}},
    )


def run(snap, reg=None, psks=PSKS):
    reg = reg or registry()
    with contextlib.redirect_stdout(io.StringIO()) as out:
        code = insp.report(snap, reg, psks)
    return code, out.getvalue()


def issues(snap, reg=None):
    reg = reg or registry()
    node = reg.by_node_id(snap.identity.node_id)
    found = insp.check_radio(snap, reg, PSKS) + insp.check_local(snap, reg, node)
    found += insp.check_mesh(snap, reg)[0]
    return [c.label for c in found if not c.ok]


class TestHealthy(unittest.TestCase):
    def test_healthy_node_exits_zero(self):
        code, out = run(healthy())
        self.assertEqual(code, 0, out)
        self.assertIn("Node healthy", out)

    def test_psks_are_compared_never_printed(self):
        _, out = run(healthy())
        self.assertNotIn("AQIDBA", out)
        self.assertIn("matches .env", out)


class TestDrift(unittest.TestCase):
    def assertCaught(self, snap, fragment, reg=None):
        found = issues(snap, reg)
        self.assertTrue(any(fragment in label for label in found), found)
        self.assertEqual(run(snap, reg)[0], 1)

    def test_unset_tx_power(self):
        """Unset reads back 30: drift against the derived 22."""
        self.assertCaught(healthy(**{"lora.tx_power": 30}), "lora.tx_power")

    def test_eirp_over_the_cap_is_a_failure(self):
        """The inspector fails if the radiated power exceeds the cap.

        A fiberglass node actually sitting on slot 17 (919.125 MHz, the 27 dBm
        band) with tx_power unset transmits 22 dBm: 27.8 dBm EIRP. The cap is
        judged on the slot the radio IS on, not the planned one.
        """
        snap = healthy(**{"lora.tx_power": 0, "lora.channel_num": 17})
        found = issues(snap)
        self.assertTrue(any(f.startswith("N1 EIRP vs cap (rule A") for f in found), found)
        self.assertIn("channel_num", found)

    def test_eirp_within_cap_passes_on_the_planned_slot(self):
        snap = healthy()
        node = registry().by_node_id("!0b64122b")
        eirp = [c for c in insp.check_local(snap, registry(), node) if "EIRP" in c.label]
        self.assertTrue(eirp and eirp[0].ok)

    def test_cadence_drift(self):
        """I2: the radio's interval must be the one the estimators measure against."""
        self.assertCaught(healthy(**{"telemetry.device_update_interval": 0}),
                          "device_update_interval")
        self.assertCaught(healthy(**{"position.position_broadcast_secs": 900}),
                          "position_broadcast_secs")

    def test_smart_position_on(self):
        self.assertCaught(healthy(**{"position.position_broadcast_smart_enabled": True}),
                          "position_broadcast_smart_enabled")

    def test_fixed_position_set(self):
        self.assertCaught(healthy(**{"position.fixed_position": True}), "fixed_position")

    def test_environment_telemetry_on_a_sensorless_node(self):
        reg = registry()
        snap = healthy(**{"telemetry.environment_measurement_enabled": True})
        snap.identity = DeviceIdentity("!7c70da02", 1, "SEEED_SOLAR_NODE", False, "2.7.26.x", None)
        self.assertCaught(snap, "environment_measurement_enabled", reg)

    def test_gps_without_a_position_cadence(self):
        data = field_registry()
        data["nodes"][3]["node_id"] = "!aabbccdd"     # GW: no position flow
        reg = parse(data)
        snap = healthy(**{"device.role": "CLIENT_MUTE", "position.gps_mode": "ENABLED",
                          "lora.tx_power": 20, "telemetry.device_telemetry_enabled": False,
                          "telemetry.environment_measurement_enabled": False})
        snap.identity = DeviceIdentity("!aabbccdd", 1, "TBEAM", True, "2.7.26.x", None)
        self.assertCaught(snap, "gps_mode", reg)

    def test_preset_slot_and_channel_drift(self):
        self.assertCaught(healthy(**{"lora.modem_preset": "LONG_FAST"}), "modem_preset")
        snap = healthy()
        snap.channels[1]["precision"] = 14
        self.assertCaught(snap, "channel 1 position_precision")
        snap = healthy()
        snap.channels[0]["psk"] = b"\x00"
        self.assertCaught(snap, "channel 0 PSK")

    def test_channels_left_by_another_configuration(self):
        snap = healthy()
        snap.channels[2].update(name="oldMesh", enabled=True)
        self.assertCaught(snap, "channel 2")
        snap = healthy()
        snap.channels[1]["enabled"] = False
        self.assertCaught(snap, "channel 1")

    def test_a_serial_module_left_on(self):
        self.assertCaught(healthy(**{"serial.enabled": True}), "serial.enabled")

    def test_bluetooth_switched_off(self):
        """A radio reused from a PBX comes back with BLE off: no phone reaches it."""
        self.assertCaught(healthy(**{"bluetooth.enabled": False}), "bluetooth.enabled")

    def test_a_pbx_radio_is_checked_for_membership_not_for_its_link(self):
        data = field_registry()
        data["nodes"].append(pbx_radio("P1", node_id="!1234abcd", firmware="2.7.26"))
        reg = parse(data)

        def snap(**over):
            s = healthy(**{"lora.hop_limit": 2, "lora.tx_power": 20,
                           "telemetry.environment_measurement_enabled": False,
                           "bluetooth.enabled": False, "serial.enabled": True,
                           "serial.mode": "PROTO", **over})
            s.identity = DeviceIdentity("!1234abcd", 0x1234ABCD, "TBEAM", True,
                                        "2.7.26.54e0d8d", None)
            return s
        self.assertEqual([i for i in issues(snap(), reg) if "P1" in i], [])
        self.assertCaught(snap(**{"lora.hop_limit": 1}), "P1 hop_limit", reg)

    def test_firmware_and_hardware(self):
        snap = healthy()
        snap.identity = DeviceIdentity("!0b64122b", 1, "TBEAM", True, "2.7.19.bb3d6d5", None)
        found = issues(snap)
        for fragment in ("firmware vs registry", "firmware vs target", "hardware model", "mcu family"):
            self.assertTrue(any(fragment in f for f in found), (fragment, found))

    def test_node_not_in_the_registry(self):
        snap = healthy()
        snap.identity = DeviceIdentity("!99999999", 1, "SEEED_SOLAR_NODE", False, "2.7.26.x", None)
        snap.mesh = {}
        self.assertCaught(snap, "local node in registry")


class TestMesh(unittest.TestCase):
    def test_unknown_and_absent_and_quantized(self):
        snap = healthy()
        snap.mesh.pop("!7c70da02")                                  # deployed N2 not heard
        snap.mesh["!deadbeef"] = {"user": {}}                       # foreign node
        found, _ = insp.check_mesh(snap, registry())
        labels = [c.label for c in found]
        self.assertIn("expected node N2 (!7c70da02)", labels)
        self.assertIn("node !deadbeef", labels)
        snap = healthy()
        snap.mesh["!7c70da02"]["position"] = {"latitude": -33.4757888, "longitude": -70.5953792}
        found, _ = insp.check_mesh(snap, registry())
        self.assertTrue(any("position precision" in c.label for c in found))

    def test_planned_nodes_are_not_expected_yet(self):
        """A planned node with a recorded id that is not on air yet is not drift."""
        data = field_registry()
        data["nodes"][0].update(node_id="!0b64122b", firmware="2.7.26")
        data["nodes"][2]["node_id"] = "!32fe0d4e"               # N3: planned, not heard
        snap = healthy()
        snap.mesh = {"!0b64122b": {"user": {"role": "CLIENT"}}}
        found, _ = insp.check_mesh(snap, parse(data))
        self.assertEqual(found, [])


class TestTrailingZeroBits(unittest.TestCase):
    """The detector must fire on what was really observed."""
    OBSERVED_LAT = -33.4757888
    OBSERVED_LON = -70.5953792

    def test_detects_the_real_quantized_coordinates(self):
        self.assertEqual(insp.trailing_zero_bits(self.OBSERVED_LAT), 18)
        self.assertEqual(insp.trailing_zero_bits(self.OBSERVED_LON), 18)
        self.assertEqual(insp.quantization(self.OBSERVED_LAT, self.OBSERVED_LON)[0], 14)

    def test_surveyed_positions_are_not_flagged(self):
        for lat, lon in [(-33.4969028, -70.6101277778), (-33.4971361, -70.6075444443),
                         (-33.5002389, -70.6119222222), (-33.4999417, -70.614008333),
                         (-27.1683611, -109.438025), (-27.1550944, -109.4360778)]:
            self.assertIsNone(insp.quantization(lat, lon), (lat, lon))

    def test_no_fix_is_not_quantization(self):
        self.assertEqual(insp.trailing_zero_bits(0.0), 0)

    def test_masking_a_full_precision_value_is_detected(self):
        for precision in (12, 14, 16, 24):
            shift = 32 - precision
            units = round(abs(-33.4969028) * 1e7)
            masked = (units >> shift) << shift
            self.assertGreaterEqual(insp.trailing_zero_bits(masked / 1e7), shift)


if __name__ == "__main__":
    unittest.main()
