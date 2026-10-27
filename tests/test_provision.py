"""Provisioning plans and the preflight guardrails, without a radio."""
import subprocess
import unittest
from unittest import mock

from meshtastic_platform.cli import meshtastic_cli
from meshtastic_platform.provision import identity, plan
from meshtastic_platform.provision import node as node_prov
from meshtastic_platform.provision.identity import DeviceIdentity
from meshtastic_platform.registry import parse
from tests.test_registry import bench, field_registry, pbx_radio

PSKS = {0: "base64:AAAA", 1: "base64:BBBB"}


def flags(steps):
    """{setting: value} across every --set in a plan."""
    out = {}
    for s in steps:
        a = s.argv
        for i, tok in enumerate(a):
            if tok == "--set":
                out[a[i + 1]] = a[i + 2]
    return out


class TestNodePlan(unittest.TestCase):
    def setUp(self):
        self.reg = parse(field_registry())

    def plan_for(self, ref, reg=None):
        reg = reg or self.reg
        return plan.node_steps(reg, reg.by_ref(ref), None, PSKS)

    def test_everything_radio_comes_from_the_deployment(self):
        f = flags(self.plan_for("N1"))
        self.assertEqual((f["lora.region"], f["lora.modem_preset"], f["lora.channel_num"]),
                         ("ANZ", "MEDIUM_FAST", "45"))
        self.assertEqual((f["lora.hop_limit"], f["lora.tx_power"]), ("1", "22"))
        self.assertEqual(f["device.rebroadcast_mode"], "LOCAL_ONLY")

    def test_channels_come_from_the_deployment(self):
        argv = [" ".join(s.argv) for s in self.plan_for("N1")]
        self.assertTrue(any("--ch-set name chPrimary" in a and "--ch-index 0" in a for a in argv))
        self.assertTrue(any("--ch-set name chSecondary" in a and "--ch-index 1" in a for a in argv))
        # --ch-add picks the first free slot: on a reused radio, the wrong index.
        self.assertFalse(any("--ch-add" in a for a in argv))
        self.assertTrue(all("module_settings.position_precision 32" in a
                            for a in argv if "--ch-set psk" in a))

    def test_tx_power_follows_the_antenna_and_the_cap(self):
        data = field_registry()
        data["radio"]["channel_num"] = 17               # 919.125 MHz: the 27 dBm band
        data["nodes"][0]["tx_power_dbm"] = 21           # fiberglass 5.8 dBi
        data["nodes"][1]["tx_power_dbm"] = 21
        reg = parse(data)
        self.assertEqual(flags(self.plan_for("N1", reg))["lora.tx_power"], "21")
        self.assertEqual(flags(self.plan_for("N3", reg))["lora.tx_power"], "22")   # rubber

    def test_rx_boosted_gain_only_on_sx126x(self):
        sensecap, tbeam = flags(self.plan_for("N1")), flags(self.plan_for("GW"))
        self.assertEqual(sensecap["lora.sx126x_rx_boosted_gain"], "true")
        self.assertNotIn("lora.sx126x_rx_boosted_gain", tbeam)
        self.assertEqual(tbeam["lora.tx_power"], "20")

    def test_cadences_come_from_the_registry(self):
        f = flags(self.plan_for("N1"))
        self.assertEqual(f["telemetry.device_update_interval"], "120")
        self.assertEqual(f["telemetry.environment_update_interval"], "120")
        self.assertEqual(f["position.position_broadcast_secs"], "600")

    def test_environment_telemetry_follows_the_sensor(self):
        with_sensor, without = flags(self.plan_for("N3")), flags(self.plan_for("N2"))
        self.assertEqual(with_sensor["telemetry.environment_measurement_enabled"], "true")
        self.assertEqual(without["telemetry.environment_measurement_enabled"], "false")
        self.assertNotIn("telemetry.environment_update_interval", without)

    def test_smart_position_is_always_off(self):
        for n in self.reg.nodes:
            f = flags(self.plan_for(n.ref))
            self.assertEqual(f["position.position_broadcast_smart_enabled"], "false", n.ref)

    def test_gateway_is_listen_only_with_gps_off(self):
        f = flags(self.plan_for("GW"))
        self.assertEqual(f["device.role"], "CLIENT_MUTE")
        self.assertEqual(f["position.gps_mode"], "DISABLED")
        self.assertEqual(f["telemetry.device_telemetry_enabled"], "false")

    def test_fixed_receiver_keeps_gps_off(self):
        """A radio on a PC at a fixed point: no broadcasts on the channel it measures."""
        f = flags(self.plan_for("R1"))
        self.assertEqual((f["device.role"], f["position.gps_mode"]), ("CLIENT_MUTE", "DISABLED"))
        self.assertNotIn("position.position_broadcast_secs", f)

    def test_walking_receiver_logs_its_track(self):
        data = field_registry()
        data["nodes"][4]["intervals"] = {"position": 30}
        f = flags(self.plan_for("R1", parse(data)))
        self.assertEqual((f["position.gps_mode"], f["position.position_broadcast_secs"],
                          f["position.gps_update_interval"]), ("ENABLED", "30", "30"))

    def test_no_position_is_ever_written_to_a_radio(self):
        """The surveyed position is a record, never a radio setting."""
        for reg in (self.reg, parse(bench(field_registry()))):
            for n in reg.nodes:
                argv = " ".join(" ".join(s.argv) for s in self.plan_for(n.ref, reg))
                for forbidden in ("--setlat", "--setlon", "--setalt", "fixed_position"):
                    self.assertNotIn(forbidden, argv, n.ref)

    def test_psks_are_never_displayed(self):
        steps = self.plan_for("N1")
        shown = " ".join(s.display() for s in steps)
        self.assertNotIn("AAAA", shown)
        self.assertNotIn("BBBB", shown)
        self.assertIn("AAAA", " ".join(" ".join(s.argv) for s in steps))

    def test_bench_runs_at_the_chip_minimum(self):
        reg = parse(bench(field_registry()))
        self.assertEqual(flags(self.plan_for("N1", reg))["lora.tx_power"], "-9")   # SX1262
        self.assertEqual(flags(self.plan_for("GW", reg))["lora.tx_power"], "2")    # SX1276

    def test_a_pbx_radio_gets_its_membership_only(self):
        """Its serial module and Bluetooth are the PBX's link: never written here."""
        data = field_registry()
        data["nodes"].append(pbx_radio("P1"))
        f = flags(self.plan_for("P1", parse(data)))
        self.assertEqual((f["lora.channel_num"], f["device.role"], f["lora.hop_limit"],
                          f["lora.tx_power"]), ("45", "CLIENT", "2", "20"))
        self.assertFalse([k for k in f if k.startswith(("serial.", "bluetooth."))])

    def test_other_radios_turn_the_serial_module_off(self):
        for ref in ("N1", "GW", "R1"):
            f = flags(self.plan_for(ref))
            self.assertEqual(f["serial.enabled"], "false", ref)
            self.assertNotIn("bluetooth.enabled", f)

    def test_cadence_scale_reaches_the_radio(self):
        data = bench(field_registry())
        data["meta"]["cadence_scale"] = 4
        f = flags(self.plan_for("N1", parse(data)))
        self.assertEqual(f["telemetry.device_update_interval"], "30")
        self.assertEqual(f["position.position_broadcast_secs"], "150")


SENSECAP = DeviceIdentity("!0b64122b", 0x0B64122B, "SEEED_SOLAR_NODE", False, "2.7.26.54e0d8d",
                          "AA:BB:0B:64:12:2B")
LILYGO = DeviceIdentity("!1234abcd", 0x1234ABCD, "TBEAM", True, "2.7.26.54e0d8d", None)


class TestPreflight(unittest.TestCase):
    def setUp(self):
        self.reg = parse(field_registry())

    def test_commissioning_a_placeholder_entry(self):
        problems, notes = identity.preflight(SENSECAP, self.reg, self.reg.by_ref("N1"))
        self.assertEqual(problems, [])
        self.assertTrue(any("!0b64122b" in n for n in notes))

    def test_a_different_real_id_stops(self):
        data = field_registry()
        data["nodes"][0]["node_id"] = "!deadbeef"
        reg = parse(data)
        problems, _ = identity.preflight(SENSECAP, reg, reg.by_ref("N1"))
        self.assertTrue(any("Not overwriting" in p for p in problems))

    def test_an_esp32_on_an_nrf52_entry_stops(self):
        """A lab radio must not get a field node's configuration."""
        problems, _ = identity.preflight(LILYGO, self.reg, self.reg.by_ref("N1"))
        self.assertTrue(any("wrong device" in p for p in problems))

    def test_hardware_model_mismatch_stops(self):
        dev = DeviceIdentity("!0b64122b", 1, "T_ECHO", False, "2.7.26.x", None)
        problems, _ = identity.preflight(dev, self.reg, self.reg.by_ref("N1"))
        self.assertTrue(any("T_ECHO" in p for p in problems))

    def test_firmware_off_target_stops(self):
        dev = DeviceIdentity("!0b64122b", 1, "SEEED_SOLAR_NODE", False, "2.7.19.bb3d6d5", None)
        problems, _ = identity.preflight(dev, self.reg, self.reg.by_ref("N1"))
        self.assertTrue(any("flash first" in p for p in problems))

    def test_a_device_registered_elsewhere_under_another_ref_stops(self):
        other = bench(field_registry())
        other["meta"]["deployment"] = "lab"
        other["nodes"][3]["node_id"] = "!1234abcd"              # the device is "GW" in "lab"
        problems, _ = identity.preflight(LILYGO, self.reg, self.reg.by_ref("R1"), [parse(other)])
        self.assertTrue(any("GW in deployment lab" in p for p in problems))

    def test_same_ref_in_two_deployments_is_allowed(self):
        """The same receiver may serve two deployments under the same ref."""
        other = bench(field_registry())
        other["meta"]["deployment"] = "lab"
        other["nodes"][4]["node_id"] = "!1234abcd"              # "R1" in both
        problems, _ = identity.preflight(LILYGO, self.reg, self.reg.by_ref("R1"), [parse(other)])
        self.assertEqual(problems, [])

    def test_ambiguous_hardware_model_lists_the_variants(self):
        _, notes = identity.preflight(LILYGO, self.reg, self.reg.by_ref("R1"))
        self.assertFalse(any("TBEAM" in n for n in notes))       # recorded hardware matches
        data = field_registry()
        data["nodes"][4]["hardware"] = None
        reg = parse(data)
        _, notes = identity.preflight(LILYGO, reg, reg.by_ref("R1"))
        self.assertTrue(any("lilygo_tbeam_sx1276" in n and "lilygo_tbeam_sx1262" in n
                            for n in notes), notes)


class TestMeshtasticCli(unittest.TestCase):
    def test_retryable_errors(self):
        self.assertTrue(meshtastic_cli.is_retryable("Input/output error", ""))
        self.assertFalse(meshtastic_cli.is_retryable("", "ok"))

    def test_run_reports_failure_after_retries(self):
        fail = subprocess.CompletedProcess([], 1, stdout="", stderr="boom")
        with mock.patch.object(meshtastic_cli.subprocess, "run", return_value=fail) as run, \
                mock.patch.object(meshtastic_cli.time, "sleep"), mock.patch("builtins.print"):
            self.assertFalse(meshtastic_cli.run(["meshtastic", "--info"]))
        self.assertEqual(run.call_count, meshtastic_cli.MAX_RETRIES)
        self.assertFalse(run.call_args.kwargs["shell"])        # argv list: no shell

    def test_run_success_and_redacted_display(self):
        ok = subprocess.CompletedProcess([], 0, stdout="done", stderr="")
        with mock.patch.object(meshtastic_cli.subprocess, "run", return_value=ok), \
                mock.patch.object(meshtastic_cli.time, "sleep"), \
                mock.patch("builtins.print") as out:
            self.assertTrue(meshtastic_cli.run(["meshtastic", "--ch-set", "psk", "SECRET"],
                                               display="meshtastic --ch-set psk <psk>"))
        printed = " ".join(str(c) for c in out.call_args_list)
        self.assertNotIn("SECRET", printed)

    def test_an_enum_read_back_as_a_number_is_not_a_failure(self):
        """`meshtastic --get` prints an enum as its protobuf int, not its name.

        Comparing the name against that output reported every provisioned node
        as having lost device.rebroadcast_mode, which it had not.
        """
        from meshtastic.protobuf import config_pb2
        mode = config_pb2.Config.DeviceConfig.RebroadcastMode
        self.assertEqual(mode.Value("LOCAL_ONLY"), 2)
        self.assertTrue(meshtastic_cli.reads_as("2", "LOCAL_ONLY", mode))
        self.assertTrue(meshtastic_cli.reads_as("LOCAL_ONLY", "LOCAL_ONLY", mode))
        # A different mode, an unreadable value, or no enum to resolve: no match.
        self.assertFalse(meshtastic_cli.reads_as("0", "LOCAL_ONLY", mode))
        self.assertFalse(meshtastic_cli.reads_as("", "LOCAL_ONLY", mode))
        self.assertFalse(meshtastic_cli.reads_as("2", "LOCAL_ONLY", None))

    def test_execute_accepts_the_numeric_read_back(self):
        """The whole path: a radio that answers '2' provisions without failures."""
        steps = [plan.Step("device role + rebroadcast_mode",
                           ["meshtastic", "--set", "device.role", "CLIENT"])]
        with mock.patch.object(meshtastic_cli, "run", return_value=True), \
                mock.patch.object(node_prov, "get_config_value", return_value="2"), \
                mock.patch.object(node_prov, "run", return_value=True), \
                mock.patch("builtins.print"):
            failures = node_prov.execute(steps, rebroadcast_mode="LOCAL_ONLY")
        self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main()
