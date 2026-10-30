"""The spreadsheet export: a view of the registry, and only a view.

The point of these tests is that the sheet carries the registry's own
distinctions rather than flattening them: a flow a node does not emit stays an
EMPTY cell (V3b: absent, never 0), the two MCU families land on separate
sheets, and nothing here can turn a sheet back into a deployment.
"""
import csv
import tempfile
import unittest
from pathlib import Path

from meshtastic_platform.registry import export, parse
from tests.test_registry import ENV, FIBER, SHT, field_registry, node, pbx_radio


def registry():
    return parse(field_registry())


def sheet(reg, mcu):
    header, rows = export.sheets(reg)[mcu]
    return header, {r["ref"]: r for r in rows}


class TestSheetsSplitByMcu(unittest.TestCase):
    def test_each_mcu_family_gets_its_own_sheet(self):
        # A `mac` is an eFuse WiFi address on one and a BLE static address on
        # the other: the columns stop meaning the same thing (V8).
        sheets = export.sheets(registry())
        self.assertEqual(set(sheets), {"nrf52840", "esp32"})
        self.assertEqual([r["ref"] for r in sheets["nrf52840"][1]], ["N1", "N2", "N3"])
        self.assertEqual([r["ref"] for r in sheets["esp32"][1]], ["GW", "R1"])

    def test_a_node_with_no_recorded_mcu_is_not_silently_dropped(self):
        data = field_registry()
        data["nodes"].append(node("N4", mcu=None, hardware=None))
        sheets = export.sheets(parse(data))
        self.assertIn("unrecorded", sheets)
        self.assertEqual([r["ref"] for r in sheets["unrecorded"][1]], ["N4"])


class TestTheSheetKeepsTheRegistrysDistinctions(unittest.TestCase):
    def test_a_flow_a_node_does_not_emit_is_an_empty_cell_not_a_zero(self):
        # In the file the key is ABSENT (V3b). A 0 in a spreadsheet would read
        # as "every zero seconds", which is the opposite of what it means.
        _, rows = sheet(registry(), "nrf52840")
        self.assertEqual(rows["N1"]["cadence_environment_s"], 120)   # has the sensor
        self.assertNotIn("cadence_environment_s", rows["N2"])        # has none

    def test_every_declared_flow_becomes_a_column_even_if_one_node_lacks_it(self):
        header, _ = sheet(registry(), "nrf52840")
        for flow in ("device", "environment", "position"):
            self.assertIn(f"cadence_{flow}_s", header)

    def test_the_columns_come_from_the_deployment_not_from_a_list_here(self):
        # No node declares `environment`, so the column does not exist at all.
        # Reading the flows from the data is also what keeps the sheet correct
        # if the set of flow kinds ever grows: nothing is dropped in silence.
        data = field_registry()
        for n in data["nodes"]:
            n["intervals"] = {k: v for k, v in n["intervals"].items() if k != "environment"}
            n["sensors"] = []
        header, _ = sheet(parse(data), "nrf52840")
        self.assertNotIn("cadence_environment_s", header)
        self.assertIn("cadence_device_s", header)

    def test_the_label_column_is_absent_when_the_refs_are_the_labels(self):
        # An empty column on a sheet whose blanks mean "still to fill" reads as
        # a missing answer. If no node carries a label, there is no question.
        self.assertNotIn("label", sheet(registry(), "nrf52840")[0])
        data = field_registry()
        data["nodes"][0]["label"] = "SC-01"
        header, rows = sheet(parse(data), "nrf52840")
        self.assertEqual(header[header.index("ref") + 1], "label")
        self.assertEqual(rows["N1"]["label"], "SC-01")
        self.assertIsNone(rows["N2"]["label"])

    def test_the_pbx_columns_appear_only_where_a_pbx_is_attached(self):
        self.assertNotIn("pbx_mcu", sheet(registry(), "esp32")[0])
        data = field_registry()
        data["nodes"].append(pbx_radio("P1", intervals={"device": 600}))
        header, rows = sheet(parse(data), "esp32")
        self.assertIn("pbx_mcu", header)
        self.assertEqual(rows["P1"]["pbx_mcu"], "nrf54l15")

    def test_what_is_not_recorded_stays_empty_it_is_the_to_fill_list(self):
        _, rows = sheet(registry(), "nrf52840")
        for column in ("node_id", "mac", "firmware", "site_name", "asset_code",
                       "asset_type", "surveyed_lat", "antenna_height_m"):
            self.assertIsNone(rows["N1"][column], column)

    def test_the_site_carries_the_operators_own_words_for_the_asset(self):
        # Which installation the node is bolted to, so a reading can be read
        # back against the operator's inventory. No vocabulary is fixed here.
        data = field_registry()
        data["nodes"][0]["site"] = {"name": "Well 7", "asset_code": "X-7",
                                    "asset_type": "intake"}
        _, rows = sheet(parse(data), "nrf52840")
        self.assertEqual(rows["N1"]["asset_code"], "X-7")
        self.assertEqual(rows["N1"]["asset_type"], "intake")

    def test_the_antenna_travels_with_the_unit(self):
        # Which antenna came out of which box is the thing the sheet exists to
        # settle, so it is columns, not one squashed string.
        _, rows = sheet(registry(), "nrf52840")
        self.assertEqual(rows["N1"]["antenna_type"], "fiberglass")
        self.assertEqual(rows["N1"]["antenna_gain_dbi"], 5.8)
        self.assertEqual(rows["N1"]["antenna_band_mhz"], "902-928")
        self.assertEqual(rows["N3"]["antenna_type"], "rubber")

    def test_derived_values_travel_with_the_node(self):
        data = field_registry()
        data["nodes"][0] = node("N1", antenna=dict(FIBER), sensors=SHT,
                                intervals=dict(ENV), tx_power_dbm=22)
        _, rows = sheet(parse(data), "nrf52840")
        self.assertEqual(rows["N1"]["eirp_dbm"], 27.8)       # 22 + 5.8
        self.assertEqual(rows["N1"]["chip"], "sx1262")
        self.assertEqual(rows["N1"]["sensors"], "SHT4X")


class TestWritingTheFiles(unittest.TestCase):
    def test_one_file_per_mcu_family_named_after_the_deployment(self):
        reg = registry()
        with tempfile.TemporaryDirectory() as tmp:
            written = export.write_csv(reg, Path(tmp) / "sheets")
            self.assertEqual(sorted(p.name for p in written),
                             [f"{reg.name}-esp32.csv", f"{reg.name}-nrf52840.csv"])
            with (Path(tmp) / "sheets" / f"{reg.name}-nrf52840.csv").open(encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))
        self.assertEqual([r["ref"] for r in rows], ["N1", "N2", "N3"])
        # On disk, absent and not-recorded are both the empty string; the
        # header is what says which column was supposed to hold a cadence.
        self.assertEqual(rows[1]["cadence_environment_s"], "")
        self.assertEqual(rows[0]["cadence_environment_s"], "120")
        self.assertEqual(rows[0]["node_id"], "")


class TestItOnlyExports(unittest.TestCase):
    def test_there_is_no_way_back_from_a_sheet_into_a_deployment(self):
        # A sheet that could be edited back would be a second place the mesh is
        # declared (rule 1), and nothing would say which copy won.
        public = [n for n in dir(export) if not n.startswith("_")]
        for name in public:
            self.assertNotIn("read", name.lower(), name)
            self.assertNotIn("load", name.lower(), name)
            self.assertNotIn("import", name.lower(), name)


if __name__ == "__main__":
    unittest.main()
