"""Registry loading and the invariants the validator enforces.

Each invariant is shown to FAIL on a minimal registry that is otherwise valid:
a validator test that only checks the happy path proves nothing. The registry
here is synthetic; the real deployment files are only required to validate.
"""
import copy
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

from meshtastic_platform import registry
from meshtastic_platform.registry import RegistryError, parse, validate

FIBER = {"type": "fiberglass", "gain_dbi": 5.8, "band_mhz": [902, 928]}
RUBBER = {"type": "rubber", "gain_dbi": 2.0}
SHT = [{"type": "SHT4X", "i2c_addr": "0x44", "port": "grove"}]
ENV = {"device": 120, "environment": 120, "position": 600}

RADIO = {
    "region": "ANZ",
    "modem_preset": "MEDIUM_FAST",
    "channel_num": 45,                                   # 926.125 MHz
    "channels": [{"index": 0, "name": "chPrimary", "psk_env": "TEST_PSK_0"},
                 {"index": 1, "name": "chSecondary", "psk_env": "TEST_PSK_1"}],
    "rebroadcast_mode": "LOCAL_ONLY",
    "position_precision": 32,
    "rx_boosted_gain": True,
    "eirp_caps": [{"band_mhz": [915, 928], "eirp_dbm": 27, "label": "rule A"},
                  {"band_mhz": [925, 928], "eirp_dbm": 30, "label": "rule B"}],
}


def node(ref, **kw):
    base = {
        "ref": ref, "function": "node", "status": "planned", "node_id": None,
        "hardware": "sensecap_solar_node_p1_pro", "mcu": "nrf52840", "firmware": None,
        "role": "CLIENT", "hop_limit": 1, "antenna": dict(RUBBER), "tx_power_dbm": 22,
        "intervals": {"device": 120, "position": 600}, "sensors": [],
    }
    base.update(kw)
    return base


def sink(ref, function):
    return node(ref, function=function, role="CLIENT_MUTE", hardware="lilygo_tbeam_sx1276",
                mcu="esp32", tx_power_dbm=20, intervals={})


PBX = {"mcu": "nrf54l15", "firmware": None}


def pbx_radio(ref, **kw):
    """A T-Beam driven by a PBX over UART: device telemetry and position, no sensor."""
    base = node(ref, function="pbx", hardware="lilygo_tbeam_sx1276", mcu="esp32",
                tx_power_dbm=20, hop_limit=2, pbx=copy.deepcopy(PBX))
    base.update(kw)
    return base


def field_registry():
    """N1 fiberglass + sensor, N2 fiberglass, N3 rubber + sensor, a gateway, a receiver."""
    return {
        "meta": {"deployment": "t", "kind": "field", "firmware_target": "2.7.26"},
        "radio": copy.deepcopy(RADIO),
        "nodes": [
            node("N1", antenna=dict(FIBER), sensors=SHT, intervals=dict(ENV)),
            node("N2", antenna=dict(FIBER)),
            node("N3", sensors=SHT, intervals=dict(ENV)),
            sink("GW", "gateway"),
            sink("R1", "receiver"),
        ],
    }


def bench(data):
    """Turn a registry into a bench one: every radio at its chip's minimum."""
    data["meta"]["kind"] = "bench"
    for n in data["nodes"]:
        n["tx_power_dbm"] = 2 if n["mcu"] == "esp32" else -9
    return data


def codes(data, level="error"):
    return {f.code for f in validate(parse(data)) if f.level == level}


class TestLoaderIsStrict(unittest.TestCase):
    def test_minimal_registry_is_valid(self):
        self.assertEqual(codes(field_registry()), set())

    def test_unknown_key_is_an_error_not_ignored(self):
        data = field_registry()
        data["nodes"][0]["intervalls"] = {"device": 120}
        with self.assertRaises(RegistryError) as ctx:
            parse(data)
        self.assertIn("intervalls", str(ctx.exception))

    def test_the_radio_block_is_required_and_strict(self):
        data = field_registry()
        del data["radio"]
        with self.assertRaises(RegistryError):
            parse(data)
        data = field_registry()
        data["radio"]["channels"] = []
        with self.assertRaises(RegistryError):
            parse(data)
        data = field_registry()
        data["radio"]["channels"][0].pop("psk_env")
        with self.assertRaises(RegistryError):
            parse(data)

    def test_null_or_zero_interval_is_rejected(self):
        """Absence is the only signal of 'does not emit'; null and 0 are refused."""
        for value in (None, 0):
            data = field_registry()
            data["nodes"][1]["intervals"]["environment"] = value
            with self.assertRaises(RegistryError) as ctx:
                parse(data)
            self.assertIn("ABSENT", str(ctx.exception))

    def test_unknown_flow_kind_is_rejected(self):
        data = field_registry()
        data["nodes"][0]["intervals"]["humidity"] = 60
        with self.assertRaises(RegistryError):
            parse(data)

    def test_unquoted_node_id_gets_a_yaml_hint(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.yaml"
            path.write_text("meta: {}\nradio: {}\nnodes:\n  - node_id: !0b64122b\n")
            with self.assertRaises(RegistryError) as ctx:
                registry.load(path)
        self.assertIn("quote", str(ctx.exception))

    def test_unquoted_firmware_float_gets_a_hint(self):
        data = field_registry()
        data["meta"]["firmware_target"] = 2.7
        with self.assertRaises(RegistryError) as ctx:
            parse(data)
        self.assertIn("quote versions", str(ctx.exception))

    def test_position_validation(self):
        for bad in ({"lat": 0, "lon": -70.6}, {"lat": -95, "lon": 1}, {"lat": "x", "lon": 1},
                    {"lat": -33.4}, {"lat": -33.4, "lon": -70.6, "altitude": 3},
                    {"lat": -27.1, "lon": None}):
            data = field_registry()
            data["nodes"][0]["site"] = {"surveyed": bad}
            with self.assertRaises(RegistryError, msg=str(bad)):
                parse(data)

    def test_an_all_null_position_is_an_unfilled_template(self):
        data = field_registry()
        data["nodes"][0]["site"] = {"surveyed": {"lat": None, "lon": None, "alt_m": None}}
        self.assertIsNone(parse(data).nodes[0].site.surveyed)

    def test_unquoted_i2c_address_is_normalised(self):
        data = field_registry()
        data["nodes"][0]["sensors"] = [{"type": "SHT4X", "i2c_addr": 0x44}]
        self.assertEqual(parse(data).nodes[0].sensors[0].i2c_addr, "0x44")


class TestRadioBlock(unittest.TestCase):
    def mutate(self, fn):
        data = field_registry()
        fn(data["radio"])
        return codes(data)

    def test_profile_comes_from_the_declaration(self):
        reg = parse(field_registry())
        self.assertEqual((reg.radio.slot.channel_num, reg.radio.slot.center_mhz), (45, 926.125))
        self.assertEqual(reg.radio.band.label, "rule B")
        self.assertEqual([c.name for c in reg.radio.channels], ["chPrimary", "chSecondary"])

    def test_V7_live_deployments_set_the_slot(self):
        """Without it the firmware hashes the primary channel name: refused, and said where."""
        data = field_registry()
        data["radio"]["channel_num"] = None
        found = [f for f in validate(parse(data)) if f.code == "V7"]
        self.assertTrue(found and "hashes the channel name" in found[0].message)

    def test_out_of_range_slot(self):
        self.assertIn("R", self.mutate(lambda r: r.update(channel_num=99)))

    def test_channels(self):
        self.assertIn("R", self.mutate(lambda r: r["channels"][1].update(index=0)))
        self.assertIn("R", self.mutate(lambda r: r["channels"][0].update(index=2)))
        self.assertIn("R", self.mutate(lambda r: r["channels"][1].update(index=8)))
        self.assertIn("R", self.mutate(lambda r: r["channels"][1].update(index=2)))    # a gap

    def test_channel_names_fit_the_firmware(self):
        self.assertIn("R", self.mutate(lambda r: r["channels"][1].update(name="twelve-chars")))
        self.assertIn("R", self.mutate(lambda r: r["channels"][1].update(name="")))
        self.assertNotIn("R", self.mutate(lambda r: r["channels"][1].update(name="elevenchars")))

    def test_rebroadcast_and_precision(self):
        self.assertIn("R", self.mutate(lambda r: r.update(rebroadcast_mode="SOMETIMES")))
        self.assertIn("R", self.mutate(lambda r: r.update(position_precision=40)))

    def test_a_slot_outside_every_declared_band(self):
        self.assertIn("R", self.mutate(lambda r: r.update(
            eirp_caps=[{"band_mhz": [902, 915], "eirp_dbm": 30}])))

    def test_field_deployments_declare_their_caps(self):
        self.assertIn("V2", self.mutate(lambda r: r.pop("eirp_caps")))

    def test_no_cap_means_the_chip_maximum(self):
        data = field_registry()
        data["radio"]["eirp_caps"] = []
        reg = parse(data)
        self.assertEqual(reg.expected_tx_power(reg.by_ref("N1")), 22)
        self.assertEqual(reg.expected_tx_power(reg.by_ref("GW")), 20)


class TestInvariants(unittest.TestCase):
    def mutate(self, fn):
        data = field_registry()
        fn(data)
        return codes(data)

    def test_V1_node_id_shape_and_uniqueness(self):
        self.assertIn("V1", self.mutate(lambda d: d["nodes"][0].update(node_id="!xxxxxxxx")))
        def dup(d):
            d["nodes"][0]["node_id"] = d["nodes"][1]["node_id"] = "!0b64122b"
        self.assertIn("V1", self.mutate(dup))
        self.assertIn("V1", self.mutate(lambda d: d["nodes"][1].update(ref="N1")))

    def test_V1_mac_must_match_node_id_low_bytes_warns(self):
        data = field_registry()
        data["nodes"][0].update(node_id="!0b64122b", mac="AA:BB:0B:64:12:2B")
        self.assertNotIn("V1", codes(data, "warning"))
        data["nodes"][0]["mac"] = "AA:BB:CC:DD:EE:FF"
        self.assertIn("V1", codes(data, "warning"))

    def test_V2_eirp_over_the_cap(self):
        def over(d):
            d["radio"]["channel_num"] = 17       # 919.125 MHz: rule A only, 27 dBm
            d["nodes"][0]["tx_power_dbm"] = 22   # 22 + 5.8 = 27.8
        self.assertIn("V2", self.mutate(over))

    def test_V2_tx_power_is_derived_not_chosen(self):
        self.assertIn("V2", self.mutate(lambda d: d["nodes"][1].update(tx_power_dbm=21)))
        self.assertIn("V2", self.mutate(lambda d: d["nodes"][1].update(tx_power_dbm=None)))

    def test_V2_declared_policy_warns_instead_of_refusing(self):
        """tx_power_policy: declared — the deviations are reported, not fatal."""
        def declared(d):
            d["radio"]["tx_power_policy"] = "declared"
            d["nodes"][0]["tx_power_dbm"] = 30        # over the cap AND off the sx1262 range
        data = field_registry()
        declared(data)
        self.assertEqual(codes(data), set())
        self.assertIn("V2", codes(data, level="warning"))

    def test_V2_an_unknown_tx_power_policy_is_refused(self):
        data = field_registry()
        data["radio"]["tx_power_policy"] = "whatever"
        with self.assertRaises(Exception):
            parse(data)

    def test_V2_sx1276_refuses_18_and_19(self):
        self.assertIn("V2", self.mutate(lambda d: d["nodes"][3].update(tx_power_dbm=19)))
        self.assertIn("V2", self.mutate(lambda d: d["nodes"][3].update(tx_power_dbm=22)))

    def test_V2_bench_rejects_field_power(self):
        self.assertEqual(codes(bench(field_registry())), set())
        data = bench(field_registry())
        data["nodes"][2]["tx_power_dbm"] = 22
        self.assertIn("V2", codes(data))

    def test_V3b_environment_cadence_without_sensor(self):
        """Declaring a flow the node never sends fabricates 100 % loss."""
        self.assertIn("V3b", self.mutate(
            lambda d: d["nodes"][1]["intervals"].update(environment=120)))

    def test_V3b_sensor_without_environment_cadence(self):
        self.assertIn("V3b", self.mutate(lambda d: d["nodes"][0]["intervals"].pop("environment")))

    def test_V3_unknown_sensor_type(self):
        self.assertIn("V3", self.mutate(lambda d: d["nodes"][1].update(sensors=[{"type": "BME999"}])))

    def test_V4_antenna(self):
        self.assertIn("V4", self.mutate(lambda d: d["nodes"][0]["antenna"].update(gain_dbi=40)))
        self.assertIn("V4", self.mutate(lambda d: d["nodes"][2].update(antenna=None)))

    def test_V4_out_of_band_antenna_warns(self):
        data = field_registry()
        data["nodes"][2]["antenna"]["band_mhz"] = [868, 915]
        self.assertIn("V4", codes(data, "warning"))

    def test_V5_mixed_firmware(self):
        def mixed(d):
            d["nodes"][0]["firmware"] = "2.7.26"
            d["nodes"][1]["firmware"] = "2.7.19"
        self.assertIn("V5", self.mutate(mixed))
        self.assertIn("V5", self.mutate(lambda d: d["meta"].pop("firmware_target")))

    def test_V6_deployed_requires_a_survey(self):
        def deployed(d):
            d["nodes"][0].update(status="deployed", node_id="!0b64122b", firmware="2.7.26")
        self.assertIn("V6", self.mutate(deployed))
        def surveyed(d):
            deployed(d)
            d["nodes"][0]["site"] = {"surveyed": {"lat": -27.1683611, "lon": -109.438025}}
        self.assertNotIn("V6", self.mutate(surveyed))

    def test_planned_coordinates_are_not_a_survey(self):
        def planned_only(d):
            d["nodes"][0].update(status="deployed", node_id="!0b64122b", firmware="2.7.26",
                                 site={"planned": {"lat": -27.1683611, "lon": -109.438025}})
        self.assertIn("V6", self.mutate(planned_only))

    def test_V8_mcu_hardware_consistency(self):
        self.assertIn("V8", self.mutate(lambda d: d["nodes"][0].update(mcu="esp32")))
        self.assertIn("V8", self.mutate(lambda d: d["nodes"][0].update(hardware="unknown_board")))

    def test_I5_sinks_are_client_mute(self):
        self.assertIn("I5", self.mutate(lambda d: d["nodes"][3].update(role="CLIENT")))
        self.assertIn("I5", self.mutate(lambda d: d["nodes"][4].update(role="CLIENT")))

    def test_C1_cadence_scaling_only_on_the_bench_and_exact(self):
        self.assertIn("C1", self.mutate(lambda d: d["meta"].update(cadence_scale=4)))
        data = bench(field_registry())
        data["meta"]["cadence_scale"] = 7
        self.assertIn("C1", codes(data))           # 120 / 7 is not exact

    def test_effective_cadences_apply_the_scale_once(self):
        data = bench(field_registry())
        data["meta"]["cadence_scale"] = 12
        reg = parse(data)
        self.assertEqual(reg.intervals(reg.by_ref("N1")),
                         {"device": 10, "environment": 10, "position": 50})

    def test_deployed_node_must_be_fully_recorded(self):
        self.assertIn("V1", self.mutate(lambda d: d["nodes"][1].update(status="deployed")))

    def test_historical_registry_records_gaps_as_warnings(self):
        def historical(d):
            d["meta"]["kind"] = "historical"
            d["radio"]["channel_num"] = None
            d["radio"].pop("eirp_caps")
            d["nodes"][1].update(status="deployed", tx_power_dbm=None, antenna=None)
        self.assertEqual(self.mutate(historical), set())


class TestPbx(unittest.TestCase):
    def with_pbx(self, **kw):
        data = field_registry()
        data["nodes"].append(pbx_radio("P1", **kw))
        return data

    def test_a_pbx_radio_is_a_first_class_node(self):
        self.assertEqual(codes(self.with_pbx()), set())
        p = parse(self.with_pbx()).by_ref("P1")
        self.assertEqual((p.function, p.pbx.mcu), ("pbx", "nrf54l15"))
        self.assertEqual(p.record_fields()["tx_function"], "pbx")

    def test_the_pbx_block_belongs_to_pbx_radios_only(self):
        self.assertIn("X", codes(self.with_pbx(pbx=None)))
        data = field_registry()
        data["nodes"][0]["pbx"] = copy.deepcopy(PBX)
        self.assertIn("X", codes(data))

    def test_pbx_processor_from_the_catalogue(self):
        self.assertIn("X", codes(self.with_pbx(pbx={**PBX, "mcu": "esp32"})))

    def test_the_link_is_not_this_repositorys(self):
        """Pins and speed belong to the PBX project: the loader refuses them here."""
        with self.assertRaises(RegistryError):
            parse(self.with_pbx(pbx={**PBX, "uart": {"txd": 15, "rxd": 35, "baud": 115200}}))

    def test_pbx_firmware_is_part_of_commissioning(self):
        todo = [f.message for f in validate(parse(self.with_pbx()))
                if f.where == "P1" and f.code == "P"]
        self.assertIn("pbx.firmware", todo[0])
        self.assertIn("X", codes(self.with_pbx(status="deployed", node_id="!1234abcd",
                                               firmware="2.7.26",
                                               site={"surveyed": {"lat": 1.5, "lon": 2.5},
                                                     "antenna_height_m": 2.0})))


class TestAcrossDeployments(unittest.TestCase):
    def test_shared_channels(self):
        """Same channels, preset and slot: the two meshes hear each other."""
        a, b = field_registry(), bench(field_registry())
        a["meta"]["deployment"], b["meta"]["deployment"] = "a", "b"
        self.assertEqual(len(registry.shared_channels([parse(a), parse(b)])), 1)
        b["radio"]["channel_num"] = 46
        self.assertEqual(registry.shared_channels([parse(a), parse(b)]), [])

    def test_bench_and_field_are_not_comparable(self):
        reasons = registry.comparable(parse(field_registry()), parse(bench(field_registry())))
        self.assertIn("kind field vs bench (bench RSSI does not transfer)", reasons)


def write_deployment(tmp: str, data: dict) -> Path:
    path = Path(tmp) / f"{data['meta']['deployment']}.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    return path


class TestDeploymentSelection(unittest.TestCase):
    def test_there_is_no_default(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(registry.ENV_DEPLOYMENT, None)
            with self.assertRaises(RegistryError) as ctx:
                registry.resolve(None)
        self.assertIn("no default", str(ctx.exception))

    def test_environment_variable_and_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_deployment(tmp, field_registry())
            with mock.patch.dict(os.environ, {registry.ENV_DEPLOYMENT: "t",
                                              "MESH_DEPLOYMENTS_DIR": tmp}):
                self.assertEqual(registry.available(), ["t"])
                self.assertEqual(registry.resolve(None).name, "t.yaml")
                with self.assertRaises(RegistryError) as ctx:
                    registry.resolve("atlantis")
                self.assertIn("'t'", str(ctx.exception))       # lists what exists

    def test_name_must_match_the_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_deployment(tmp, field_registry())
            other = path.with_name("other.yaml")
            path.rename(other)
            found = validate(registry.load(other))
        self.assertIn("M", {f.code for f in found if f.level == "error"})

    def test_load_deployment_refuses_an_invalid_registry(self):
        data = field_registry()
        data["nodes"][0]["tx_power_dbm"] = 21
        with tempfile.TemporaryDirectory() as tmp:
            path = write_deployment(tmp, data)
            with self.assertRaises(RegistryError):
                registry.load_deployment(str(path), report=None)


class TestDeploymentFiles(unittest.TestCase):
    """deployments/ holds the application; it must always validate."""

    def test_every_deployment_validates(self):
        for name in registry.available():
            reg = registry.load(registry.resolve(name))
            errs = [str(f) for f in validate(reg) if f.level == "error"]
            self.assertEqual(errs, [], name)

    def test_the_template_is_valid_and_not_a_deployment(self):
        path = registry.deployments_dir() / "_template.yaml"
        self.assertNotIn("_template", registry.available())
        reg = parse(yaml.safe_load(path.read_text()))
        self.assertEqual([str(f) for f in validate(reg) if f.level == "error"], [])

    def test_filling_the_template_on_site(self):
        """What an operator does at a site: the filled node validates as deployed."""
        text = (registry.deployments_dir() / "_template.yaml").read_text()
        for old, new in (
            ("status: planned", "status: deployed"),
            ("node_id: null", 'node_id: "!0b64122b"'),
            ("mac: null", 'mac: "AA:BB:0B:64:12:2B"'),
            ("firmware: null", 'firmware: "2.7.26"'),
            ("name: null", "name: Site one"),
            ("surveyed: {lat: null, lon: null, alt_m: null, alt_source: null}",
             'surveyed: {lat: -27.1683611, lon: -109.438025, alt_m: 80.2, alt_source: "GPS, 10 fixes"}'),
            ("antenna_height_m: null", "antenna_height_m: 6.0"),
        ):
            text = text.replace(old, new, 1)              # first occurrence = the first node
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "my-mesh.yaml"
            path.write_text(text)
            reg = registry.load_deployment(str(path), report=None)
            n1 = reg.by_ref("N1")
            self.assertEqual(n1.status, "deployed")
            self.assertEqual((n1.site.surveyed.lat, n1.site.surveyed.alt_m), (-27.1683611, 80.2))
            self.assertNotIn("N1", {f.where for f in validate(reg)})
            # Deployed without the survey is refused (V6).
            path.write_text(text.replace(
                'surveyed: {lat: -27.1683611, lon: -109.438025, alt_m: 80.2, alt_source: "GPS, 10 fixes"}',
                "surveyed: {lat: null, lon: null, alt_m: null, alt_source: null}", 1))
            with self.assertRaises(RegistryError) as ctx:
                registry.load_deployment(str(path), report=None)
            self.assertIn("V6", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
