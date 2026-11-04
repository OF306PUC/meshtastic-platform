"""Behaviour of decode() beyond the golden values: the contract every consumer leans on."""
import copy
import time
import unittest
from unittest import mock

from meshtastic_platform.decode import FLOW_KINDS, DecodeStats, decode
from tests.fixtures import packets as pk


class TestProtobufDefaults(unittest.TestCase):
    """protobuf3 omits zero values; an absent key is a zero, not an unknown.

    These two cases are the ONLY behaviour that differs from the previous
    decoders (classified D1/D2 by the equivalence run of 2026-10-23). The old
    code read both as None.
    """

    def test_D1_absent_hop_limit_with_hop_start_is_zero(self):
        """A packet that used up every hop arrives with no hopLimit key at all.
        With hop_limit=1 meshes that is every relayed packet."""
        pkt = pk.env_packet()
        pkt["hopStart"] = 1
        del pkt["hopLimit"]
        d = decode(pkt)
        self.assertEqual(d.hop_limit, 0)
        self.assertEqual(d.hops_taken, 1)

    def test_D1_explicit_none_hop_limit_reads_the_same(self):
        pkt = pk.env_packet()
        pkt["hopStart"], pkt["hopLimit"] = 3, None
        self.assertEqual(decode(pkt).hops_taken, 3)

    def test_hop_start_absent_means_unknown(self):
        """Pre-2.3 firmware never set hopStart; nothing can be inferred."""
        for hop_limit in (2, None):
            pkt = pk.env_packet()
            pkt["hopStart"], pkt["hopLimit"] = None, hop_limit
            self.assertIsNone(decode(pkt).hops_taken)
        pkt = pk.env_packet()
        del pkt["hopStart"], pkt["hopLimit"]
        self.assertIsNone(decode(pkt).hops_taken)

    def test_D2_absent_snr_with_rssi_is_zero_db(self):
        """The radio measures both on every LoRa reception; 0.0 dB is a reading."""
        pkt = pk.env_packet()
        del pkt["rxSnr"]
        self.assertEqual(decode(pkt).rx_snr, 0.0)

    def test_no_rssi_no_snr_stays_none(self):
        """No RSSI means it did not come over LoRa (local, API): no SNR either."""
        pkt = pk.env_packet()
        del pkt["rxSnr"], pkt["rxRssi"]
        d = decode(pkt)
        self.assertIsNone(d.rx_snr)
        self.assertIsNone(d.rx_rssi)

    def test_absent_channel_is_zero_not_none(self):
        pkt = pk.device_packet()
        self.assertNotIn("channel", pkt)
        self.assertEqual(decode(pkt).channel, 0)

    def test_channel_is_carried(self):
        pkt = pk.private_packet(b"\x01\x02")
        pkt["channel"] = 1
        self.assertEqual(decode(pkt).channel, 1)

    def test_metric_fields_are_not_defaulted(self):
        """The opposite rule for metrics: absent is None, a 0.0 would be a false reading."""
        pkt = pk.device_packet()
        del pkt["decoded"]["telemetry"]["deviceMetrics"]["batteryLevel"]
        self.assertIsNone(decode(pkt).device.battery_level)


class TestApplicationPayloads(unittest.TestCase):
    def test_private_app_is_opaque(self):
        """An application's own format is not the platform's to parse."""
        d = decode(pk.private_packet(b"\x01\x15\x09\xa6\x6fsome bytes"))
        self.assertEqual(d.kind, "private")
        self.assertEqual(d.payload_len, 15)
        self.assertEqual(d.flows, ())

    def test_payload_never_in_repr(self):
        """It may be real people's traffic: it must not reach a log line by accident."""
        d = decode(pk.private_packet(b"secret message"))
        self.assertNotIn("secret", repr(d))

    def test_plain_text(self):
        d = decode(pk.text_packet(b"test 012/050"))
        self.assertEqual((d.kind, d.text.text, d.payload_len), ("text", "test 012/050", 12))

    def test_library_text_field_is_preferred(self):
        pkt = pk.text_packet(b"abc")
        pkt["decoded"]["text"] = "abc"
        self.assertEqual(decode(pkt).text.text, "abc")

    def test_text_that_is_not_utf8(self):
        d = decode(pk.text_packet(b"\xff\xfe\xfd"))
        self.assertEqual(d.kind, "text")
        self.assertIsNone(d.text.text)


class TestNeighborInfo(unittest.TestCase):
    """Portnum 71: the only packet that says who a node HEARS, not who sent it."""

    def test_the_adjacency_list_is_parsed(self):
        d = decode(pk.neighborinfo_packet())
        self.assertEqual(d.kind, "neighborinfo")
        ni = d.neighborinfo
        self.assertEqual(ni.node_num, 0x7C70DA02)
        self.assertEqual(ni.broadcast_interval_secs, 14400)
        self.assertEqual([(n.node_num, n.snr) for n in ni.neighbors],
                         [(0x0B64122B, 10.75), (0x32FE0D4E, -3.25)])

    def test_it_is_not_a_measured_flow(self):
        """At four hours there is no cadence for the gap estimator (rule 3)."""
        d = decode(pk.neighborinfo_packet())
        self.assertEqual(d.flows, ())
        self.assertNotIn("neighborinfo", FLOW_KINDS)

    def test_hearing_nobody_is_still_an_observation(self):
        d = decode(pk.neighborinfo_packet(neighbors=()))
        self.assertEqual(d.kind, "neighborinfo")
        self.assertEqual(d.neighborinfo.neighbors, ())

    def test_last_sent_by_is_the_relay_not_the_author(self):
        """Each relay rewrites it, so the two differ on a packet that was relayed."""
        d = decode(pk.neighborinfo_packet(last_sent_by=0x403192D7))
        self.assertEqual(d.neighborinfo.node_num, 0x7C70DA02)
        self.assertEqual(d.neighborinfo.last_sent_by_num, 0x403192D7)

    def test_a_field_this_decoder_does_not_map_stays_visible(self):
        pkt = pk.neighborinfo_packet()
        pkt["decoded"]["neighborinfo"]["somethingNew"] = 7
        self.assertEqual(decode(pkt).neighborinfo.extra, {"somethingNew": 7})


class TestNothingDroppedSilently(unittest.TestCase):
    def test_unknown_portnum_lands_in_raw_and_is_counted(self):
        pkt = pk.env_packet()
        pkt["decoded"]["portnum"] = "PAXCOUNTER_APP"
        d = decode(pkt)
        self.assertEqual(d.kind, "other")
        self.assertIs(d.raw, pkt)
        stats = DecodeStats()
        stats.record(d)
        self.assertEqual(stats.unknown_portnum["PAXCOUNTER_APP"], 1)

    def test_unmapped_telemetry_variant_is_counted(self):
        pkt = pk.env_packet()
        pkt["decoded"]["telemetry"] = {"time": 1, "powerMetrics": {"ch1Voltage": 3.3}}
        d = decode(pkt)
        self.assertEqual(d.kind, "telemetry")
        self.assertEqual(d.flows, ())
        stats = DecodeStats()
        stats.record(d)
        self.assertEqual(stats.unhandled_telemetry["powerMetrics"], 1)

    def test_new_metric_fields_are_kept_in_extra(self):
        pkt = pk.device_packet()
        pkt["decoded"]["telemetry"]["deviceMetrics"]["newFirmwareField"] = 7
        pkt["decoded"]["telemetry"]["raw"] = object()       # the library's protobuf mirror
        d = decode(pkt)
        self.assertEqual(d.device.extra, {"newFirmwareField": 7})

    def test_undecryptable_packet(self):
        pkt = pk.env_packet()
        del pkt["decoded"]
        pkt["encrypted"] = b"\x00\x01"
        d = decode(pkt)
        self.assertEqual(d.kind, "encrypted")
        self.assertEqual(d.rx_rssi, -85)        # still a reception on our frequency

    def test_empty_inputs_do_not_raise(self):
        for packet in (None, {}, {"fromId": pk.KNOWN_NODE_ID, "id": 1}):
            self.assertEqual(decode(packet).kind, "empty")

    def test_unknown_senders_are_counted(self):
        stats = DecodeStats()
        pkt = pk.env_packet()
        pkt["fromId"] = "!deadbeef"
        stats.record(decode(pkt, known_nodes={pk.KNOWN_NODE_ID: "x"}))
        self.assertEqual(stats.unknown_sender["!deadbeef"], 1)


class TestPurity(unittest.TestCase):
    def test_decoder_never_reads_the_clock(self):
        """Time is the caller's: without this, PDR cannot be tested against fixtures."""
        boom = mock.Mock(side_effect=AssertionError("decode() read the clock"))
        with mock.patch.object(time, "time", boom), mock.patch.object(time, "monotonic", boom):
            for p in (pk.env_packet(), pk.device_packet(), pk.position_packet(),
                      pk.private_packet(b"\x01\x02"), pk.text_packet(b"hi")):
                no_ts = copy.deepcopy(p)
                for sub in ("telemetry", "position"):
                    (no_ts["decoded"].get(sub) or {}).pop("time", None)
                d = decode(no_ts)
                for part in (d.device, d.environment, d.position):
                    if part is not None:
                        self.assertIsNone(part.device_ts)   # no wall-clock fallback

    def test_deterministic_and_input_untouched(self):
        pkt = pk.device_packet(pkt_id=77)
        before = copy.deepcopy(pkt)
        self.assertEqual(decode(pkt), decode(pkt))
        self.assertEqual(pkt, before)

    def test_known_nodes_attaches_without_filtering(self):
        known = {pk.KNOWN_NODE_ID: "the-node"}
        self.assertEqual(decode(pk.env_packet(), known_nodes=known).node, "the-node")
        pkt = pk.env_packet()
        pkt["fromId"] = "!deadbeef"
        d = decode(pkt, known_nodes=known)
        self.assertIsNone(d.node)
        self.assertEqual(d.kind, "environment")     # unknown senders still decode

    def test_position_flow_counts_even_without_a_fix(self):
        pkt = pk.position_packet()
        pkt["decoded"]["position"] = {}
        d = decode(pkt)
        self.assertEqual(d.flows, ("position",))
        self.assertIsNone(d.position.latitude)


if __name__ == "__main__":
    unittest.main()
