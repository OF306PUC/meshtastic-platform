"""The channel-study receiver end to end, with injected clocks and no radio."""
import copy
import csv
import io
import json
import tempfile
import unittest
from pathlib import Path

from channel_study import session as sess
from channel_study.gaps import GapWatcher
from channel_study.listener import ChannelStudyReceiver, expected_flows
from channel_study.records import columns
from channel_study.sink import jsonable
from channel_study.sink.csv import CsvSink
from channel_study.sink.jsonl import JsonlSink
from channel_study.sink.terminal import TerminalSink
from channel_study.summary import Summary, percentile
from meshtastic_platform.registry import parse
from tests.fixtures import packets as pk
from tests.test_registry import field_registry


def registry():
    data = field_registry()
    data["nodes"][0]["node_id"] = pk.KNOWN_NODE_ID            # N1: fiberglass + SHT4X
    data["nodes"][3]["node_id"] = pk.GATEWAY_ID               # GW: the receiving radio
    return parse(data)


class Clock:
    def __init__(self, t=1_761_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


class Rig:
    """A receiver wired to a terminal, a CSV and a JSONL sink in a temp dir."""

    def __init__(self, **kw):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.reg = registry()
        self.wall, self.mono = Clock(), Clock(100.0)
        self.out = io.StringIO()
        self.term = TerminalSink(self.out, snr_floor=self.reg.radio.snr_floor_db, color=False,
                                 raw=kw.pop("raw", False))
        self.csv = CsvSink(self.dir, run_id="run-1", clock=self.wall)
        self.jsonl = JsonlSink(self.dir, run_id="run-1", clock=self.wall)
        self.rx = ChannelStudyReceiver(
            self.reg, [self.term, self.csv, self.jsonl], run_id="run-1",
            my_id=pk.GATEWAY_ID, my_num=pk.GATEWAY_NUM, rx_node=self.reg.by_ref("GW"),
            wall=self.wall, mono=self.mono, **kw)

    def feed(self, packet, advance=0.0):
        self.wall.t += advance
        self.mono.t += advance
        self.rx.on_packet(packet)

    def lines(self):
        return [l for l in self.out.getvalue().splitlines() if l and not l.startswith(("HH", "─"))]

    def table(self, name):
        with open(self.dir / name, newline="") as fh:
            return list(csv.DictReader(fh))

    def close(self):
        self.rx.close()
        self.tmp.cleanup()


class TestTerminal(unittest.TestCase):
    def setUp(self):
        self.rig = Rig()

    def tearDown(self):
        self.rig.close()

    def test_column_order_is_the_specification(self):
        self.rig.feed(pk.env_packet())
        line = self.rig.lines()[0]
        cols = line.split()
        # time, ref, kind, hops, RSSI, SNR, payload — in that order
        self.assertRegex(cols[0], r"^\d\d:\d\d:\d\d$")
        self.assertEqual(cols[1:6], ["N1", "env", "2*", "-85", "+7.5"])
        self.assertTrue(line.endswith("T=22.5C  RH=55%"))
        header = self.rig.out.getvalue().splitlines()[0].split()
        self.assertEqual(header, ["HH:MM:SS", "ref", "kind", "hops", "RSSI", "SNR", "payload"])

    def test_columns_are_aligned(self):
        self.rig.feed(pk.env_packet())
        self.rig.feed(pk.device_packet())
        a, b = self.rig.lines()
        self.assertEqual(a.index("-85"), b.index("-90"))

    def test_low_snr_is_highlighted(self):
        pkt = pk.device_packet()
        pkt["rxSnr"] = -13.0          # below MEDIUM_FAST's -12.5 dB floor
        self.rig.feed(pkt)
        self.assertIn("-13.0!", self.rig.lines()[0])

    def test_direct_packets_are_not_marked(self):
        pkt = pk.device_packet()
        pkt["hopStart"] = pkt["hopLimit"] = 1
        self.rig.feed(pkt)
        self.assertEqual(self.rig.lines()[0].split()[3], "0")

    def test_duplicates_are_marked_not_dropped(self):
        pkt = pk.env_packet(pkt_id=4242)
        self.rig.feed(pkt)
        self.rig.feed(copy.deepcopy(pkt))
        lines = self.rig.lines()
        self.assertEqual(len(lines), 2)
        self.assertIn("(dup)", lines[1])

    def test_unknown_sender_is_shown_by_id(self):
        pkt = pk.env_packet()
        pkt["fromId"], pkt["from"] = "!deadbeef", 0xDEADBEEF
        self.rig.feed(pkt)
        self.assertIn("?beef", self.rig.lines()[0])

    def test_text_and_private(self):
        self.rig.feed(pk.text_packet(b"test 012/050"))
        self.rig.feed(pk.private_packet(b"\x01\x02\x03\x04"))
        a, b = self.rig.lines()
        self.assertIn('"test 012/050"', a)
        self.assertEqual(b.split()[2], "private")
        self.assertTrue(b.endswith("4 B"))

    def test_other_kinds_only_with_raw(self):
        pkt = pk.env_packet()
        pkt["decoded"]["portnum"] = "NODEINFO_APP"
        self.rig.feed(pkt)
        self.assertEqual(self.rig.lines(), [])


class TestCsv(unittest.TestCase):
    def setUp(self):
        self.rig = Rig()

    def tearDown(self):
        self.rig.close()

    def test_one_file_per_node_and_kind_with_a_stable_header(self):
        self.rig.feed(pk.env_packet())
        self.rig.feed(pk.env_packet(include_humidity=False), advance=120)
        self.rig.feed(pk.device_packet())
        self.rig.csv.close()
        env = self.rig.table("N1_environment.csv")
        with open(self.rig.dir / "N1_environment.csv") as fh:
            self.assertEqual(fh.readline().strip().split(","), columns("environment"))
        self.assertEqual(len(env), 2)
        self.assertEqual(env[1]["relative_humidity"], "")        # absent, never 0
        self.assertTrue((self.rig.dir / "N1_device.csv").is_file())

    def test_registry_facts_of_both_ends_travel_with_every_record(self):
        self.rig.feed(pk.env_packet())
        self.rig.csv.close()
        row = self.rig.table("N1_environment.csv")[0]
        self.assertEqual((row["tx_antenna_type"], row["tx_antenna_gain_dbi"], row["tx_power_dbm"]),
                         ("fiberglass", "5.8", "22"))
        self.assertEqual(row["tx_sensors"], "SHT4X")
        self.assertEqual((row["rx_ref"], row["rx_antenna_type"]), ("GW", "rubber"))
        self.assertEqual((row["run_id"], row["deployment"]), ("run-1", "t"))

    def test_making_csv_optional_changes_nothing_else(self):
        a, b = Rig(), Rig()
        b.rx.sinks.remove(b.csv)
        for rig in (a, b):
            rig.feed(pk.env_packet(pkt_id=9))
            rig.feed(pk.device_packet(pkt_id=10), advance=200)
        self.assertEqual(a.out.getvalue(), b.out.getvalue())
        self.assertEqual(a.rx.summary_rows(), b.rx.summary_rows())
        a.close()
        b.close()


class TestGaps(unittest.TestCase):
    def test_expected_flows_come_from_the_registry(self):
        reg = registry()
        flows = expected_flows(reg, exclude_node_id=pk.GATEWAY_ID, nodes=None, kinds=None)
        self.assertEqual(flows, {("N1", "device"): 120, ("N1", "environment"): 120,
                                 ("N1", "position"): 600})

    def test_gap_opens_at_one_and_a_half_cadences_and_closes_on_return(self):
        rig = Rig()
        rig.feed(pk.env_packet())
        rig.mono.t += 179
        rig.rx.tick()
        self.assertNotIn("no reception from N1/env", rig.out.getvalue())
        rig.mono.t += 2                                       # 181 s > 1.5 x 120
        rig.rx.tick()
        self.assertIn("── no reception from N1/env for 181 s ──", rig.out.getvalue())
        rig.rx.tick()                                         # announced once
        self.assertEqual(rig.out.getvalue().count("no reception from N1/env"), 1)
        rig.feed(pk.env_packet(), advance=60)
        self.assertIn("── N1/env back after 241 s ──", rig.out.getvalue())
        rig.csv.close()
        states = [(r["ref"], r["kind"], r["state"]) for r in rig.table("gaps.csv")]
        self.assertIn(("N1", "environment", "open"), states)
        self.assertIn(("N1", "environment", "closed"), states)
        rig.close()

    def test_a_flow_never_heard_is_announced_too(self):
        w = GapWatcher({("N1", "position"): 600}, start=0.0)
        events = w.check(901.0)
        self.assertEqual([e.text() for e in events], ["── no reception from N1/pos for 901 s ──"])

    def test_duplicates_do_not_close_a_gap(self):
        rig = Rig()
        pkt = pk.device_packet(pkt_id=777)
        rig.feed(pkt)
        rig.mono.t += 200
        rig.rx.tick()
        rig.feed(copy.deepcopy(pkt))                          # a rebroadcast, not a new packet
        self.assertNotIn("back after", rig.out.getvalue())
        rig.close()


class TestOwnPacketsAndFilters(unittest.TestCase):
    def test_own_gps_track_is_recorded_as_own(self):
        rig = Rig()
        pkt = pk.position_packet()
        pkt["fromId"], pkt["from"] = pk.GATEWAY_ID, pk.GATEWAY_NUM
        rig.feed(pkt)
        rig.csv.close()
        self.assertIn("(own)", rig.lines()[0])
        self.assertEqual(rig.table("GW_position.csv")[0]["own"], "1")
        self.assertEqual(rig.rx.summary_rows(), [])            # not a reception of the mesh
        rig.close()

    def test_node_and_kind_filters(self):
        rig = Rig(nodes={"N1"}, kinds={"environment"})
        rig.feed(pk.device_packet())
        rig.feed(pk.env_packet())
        self.assertEqual(len(rig.lines()), 1)
        self.assertEqual(rig.rx.gaps.flows, [("N1", "environment")])
        rig.close()


class TestJsonl(unittest.TestCase):
    def test_everything_is_kept_and_content_redacted(self):
        rig = Rig()
        other = pk.env_packet()
        other["decoded"]["portnum"] = "NODEINFO_APP"
        rig.feed(other)
        rig.feed(pk.private_packet(b"private words"))
        rig.feed(pk.text_packet(b"a personal message"))
        rig.jsonl.close()
        objs = [json.loads(l) for l in (rig.dir / "packets.jsonl").read_text().splitlines()]
        self.assertEqual([o["record"]["kind"] for o in objs], ["other", "private", "text"])
        self.assertNotIn("private words", json.dumps(objs))
        self.assertNotIn("personal", json.dumps(objs))
        self.assertTrue(objs[1]["packet"]["decoded"]["payload"].startswith("<redacted"))
        self.assertEqual(objs[1]["record"]["payload_len"], 13)
        self.assertIsNone(objs[2]["record"]["text"])
        rig.close()

    def test_capture_content_is_opt_in(self):
        rig = Rig(capture_content=True)
        rig.feed(pk.text_packet(b"hello"))
        rig.jsonl.close()
        obj = json.loads((rig.dir / "packets.jsonl").read_text())
        self.assertEqual(obj["record"]["text"], "hello")
        self.assertEqual(obj["packet"]["decoded"]["payload"], "hex:" + b"hello".hex())
        rig.close()

    def test_jsonable(self):
        out = jsonable({"a": b"\x01\x02", "raw": object(), "decoded": {"portnum": "TEXT_MESSAGE_APP",
                                                                       "payload": b"hi", "text": "hi"}})
        self.assertEqual(out["a"], "hex:0102")
        self.assertNotIn("raw", out)
        self.assertEqual(out["decoded"]["text"], "<redacted 2 B>")


class TestSummary(unittest.TestCase):
    def test_percentile_matches_numpy_linear(self):
        self.assertEqual(percentile([1, 2, 3, 4, 5], 50), 3)
        self.assertAlmostEqual(percentile([10, 20], 5), 10.5)
        self.assertIsNone(percentile([], 50))

    def test_levels_use_direct_receptions_only(self):
        s = Summary()
        s.add("N1", "device", 0, -80, 5.0, False)
        s.add("N1", "device", 0, -90, 3.0, False)
        s.add("N1", "device", 1, -40, 12.0, False)        # relayed: the relay's link
        s.add("N1", "device", 0, -85, 4.0, True)          # duplicate
        row = s.rows({})[0]
        self.assertEqual((row["receptions"], row["duplicates"], row["direct"]), (3, 1, 2))
        self.assertEqual(row["rssi_p95"], -80.5)
        self.assertEqual(row["hops"], {"0": 2, "1": 1})
        self.assertEqual(len(Summary.render([row])), 2)

    def test_counters_report_what_was_not_mapped(self):
        rig = Rig()
        enc = pk.env_packet()
        del enc["decoded"]
        enc["encrypted"] = b"x"
        rig.feed(enc)
        text = " ".join(rig.rx.counters_lines())
        self.assertIn("undecryptable", text)
        rig.close()


class TestPubsubWiring(unittest.TestCase):
    """The listener must survive pypubsub's signature checks, whichever comes
    first: our subscription, or the library's sendMessage on a subtopic."""

    def _run(self, subscribe_first: bool):
        from pubsub import pub
        rig = Rig()
        topic = "meshtastic.receive.telemetry"
        try:
            if not subscribe_first:
                pub.sendMessage(topic, packet={}, interface=None)
            pub.subscribe(rig.rx.pubsub_listener, "meshtastic.receive")
            pub.sendMessage(topic, packet=pk.env_packet(), interface=None)
            self.assertEqual(len(rig.lines()), 1)
        finally:
            pub.unsubscribe(rig.rx.pubsub_listener, "meshtastic.receive")
            pub.getDefaultTopicMgr().delTopic("meshtastic")
            rig.close()

    def test_subscribe_then_library_publishes(self):
        self._run(subscribe_first=True)

    def test_library_publishes_then_subscribe(self):
        self._run(subscribe_first=False)


class TestSession(unittest.TestCase):
    def test_session_json_round_trip_and_no_mixing(self):
        reg = registry()
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            meta = sess.SessionMeta(run_id="r1", started_utc=sess.iso(0), operator="op",
                                    deployment=sess.SessionMeta.deployment_block(reg),
                                    receiver={"node_id": pk.GATEWAY_ID}, git="test")
            meta.write(a)
            loaded = sess.load_session(a)
            for key in ("run_id", "started_utc", "operator", "deployment", "receiver", "git",
                        "notes", "platform_version"):
                self.assertIn(key, loaded)
            self.assertEqual(loaded["deployment"]["slot_mhz"], 926.125)
            other = copy.deepcopy(meta)
            other.deployment = {**meta.deployment, "name": "bench-lilygo"}
            other.write(b)
            with self.assertRaises(ValueError):
                sess.load_sessions([a, b])
            self.assertEqual(len(sess.load_sessions([a, b], allow_mixed=True)), 2)

    def test_unlabelled_data_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(FileNotFoundError):
                sess.load_session(d)

    def test_run_id_shape(self):
        import datetime as dt
        rid = sess.new_run_id(dt.datetime(2026, 11, 3, 10, 42, 17, tzinfo=dt.timezone.utc))
        self.assertRegex(rid, r"^20261103T104217Z-[0-9a-f]{4}$")


if __name__ == "__main__":
    unittest.main()
