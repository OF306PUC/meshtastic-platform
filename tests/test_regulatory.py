"""Slots, radiated-power caps, derived tx_power and LoRa arithmetic."""
import os
import unittest
from unittest import mock

from meshtastic_platform.radio import presets, profile as rp, regulatory as rg

SX1262 = rg.get_chip("sx1262")
SX1276 = rg.get_chip("sx1276")

# A cap set with the shape regulations take: a wide band, and narrower bands
# inside it with a higher cap.
CAPS = (rg.Band(915.0, 928.0, 27.0, "wide"),
        rg.Band(913.0, 919.0, 30.0, "narrow"),
        rg.Band(925.0, 928.0, 30.0, "narrow"))


class TestSlots(unittest.TestCase):
    def test_slot_frequencies_follow_the_firmware_formula(self):
        """centre = 915 + BW/2 + (slot - 1) * BW, in ANZ."""
        for preset, slot, mhz in (("LONG_TURBO", 14, 921.75), ("LONG_FAST", 20, 919.875),
                                  ("MEDIUM_FAST", 45, 926.125), ("LONG_TURBO", 17, 923.25)):
            s = rg.resolve_slot("ANZ", preset, slot, "x")
            self.assertEqual((s.source, s.center_mhz), ("explicit", mhz), preset)

    def test_slot_counts(self):
        self.assertEqual(rg.resolve_slot("ANZ", "LONG_TURBO", 1, "x").n_slots, 26)    # 500 kHz
        self.assertEqual(rg.resolve_slot("ANZ", "MEDIUM_FAST", 1, "x").n_slots, 52)   # 250 kHz

    def test_without_a_slot_the_firmware_hashes_the_primary_channel_name(self):
        s = rg.resolve_slot("ANZ", "MEDIUM_FAST", None, "some name")
        self.assertEqual(s.source, "hash")
        self.assertEqual(s.channel_num, rg.djb2("some name") % 52 + 1)

    def test_djb2(self):
        self.assertEqual(rg.djb2(""), 5381)
        self.assertEqual(rg.djb2("a"), 5381 * 33 + ord("a"))
        self.assertLess(rg.djb2("x" * 200), 2 ** 32)       # uint32 arithmetic

    def test_the_most_permissive_band_containing_the_whole_channel(self):
        s45 = rg.resolve_slot("ANZ", "MEDIUM_FAST", 45, "x")   # 926.0–926.25
        self.assertEqual(rg.eirp_cap(s45, CAPS).eirp_dbm, 30.0)
        s40 = rg.resolve_slot("ANZ", "MEDIUM_FAST", 40, "x")   # 924.75–925.00: touches, not inside
        self.assertEqual(rg.eirp_cap(s40, CAPS).eirp_dbm, 27.0)
        s17 = rg.resolve_slot("ANZ", "MEDIUM_FAST", 17, "x")   # 919.0–919.25: straddles 919
        self.assertEqual(rg.eirp_cap(s17, CAPS).eirp_dbm, 27.0)

    def test_no_caps_declared_and_out_of_every_band(self):
        s = rg.resolve_slot("ANZ", "MEDIUM_FAST", 45, "x")
        self.assertIsNone(rg.eirp_cap(s, ()))
        with self.assertRaises(ValueError):
            rg.eirp_cap(s, (rg.Band(902.0, 915.0, 30.0),))

    def test_out_of_range_slot_is_rejected(self):
        with self.assertRaises(ValueError):
            rg.resolve_slot("ANZ", "LONG_TURBO", 27, "x")      # 26 slots at 500 kHz

    def test_unknown_region_is_rejected_not_guessed(self):
        with self.assertRaises(ValueError):
            rg.resolve_slot("EU_868", "LONG_FAST", 1, "x")


class TestDerivedTxPower(unittest.TestCase):
    TABLE = [  # (gain, cap 27, cap 30) -> expected on an SX1262
        (2.0, 22, 22),     # 25 allowed under 27, the chip delivers 22
        (5.8, 21, 22),
        (8.0, 19, 22),
    ]

    def test_table(self):
        for gain, at27, at30 in self.TABLE:
            self.assertEqual(rg.derive_tx_power(gain, 27.0, SX1262), at27, f"{gain} dBi @27")
            self.assertEqual(rg.derive_tx_power(gain, 30.0, SX1262), at30, f"{gain} dBi @30")

    def test_integer_boundaries_do_not_lose_a_db_to_float_error(self):
        self.assertEqual(rg.derive_tx_power(5.0, 27.0, SX1262), 22)

    def test_eirp_never_exceeds_the_cap(self):
        for gain in (0.5, 2.0, 3.1, 5.8, 6.5, 8.0, 9.9):
            for cap in (27.0, 30.0):
                for chip in (SX1262, SX1276):
                    tx = rg.derive_tx_power(gain, cap, chip)
                    self.assertLessEqual(rg.eirp_dbm(tx, gain), cap)
                    self.assertTrue(chip.valid(tx))

    def test_no_cap_means_the_chip_maximum(self):
        self.assertEqual(rg.derive_tx_power(5.8, None, SX1262), 22)
        self.assertEqual(rg.derive_tx_power(5.8, None, SX1276), 20)

    def test_sx1276_never_derives_18_or_19(self):
        self.assertEqual(rg.derive_tx_power(2.0, 30.0, SX1276), 20)     # RF95_MAX_POWER
        self.assertEqual(rg.derive_tx_power(8.0, 27.0, SX1276), 17)     # 19 and 18 are refused
        self.assertFalse(SX1276.valid(19))
        self.assertFalse(SX1276.valid(1))                               # below PA_BOOST: RFO path

    def test_impossible_antenna_raises(self):
        with self.assertRaises(ValueError):
            rg.derive_tx_power(40.0, 27.0, SX1262)


class TestEffectiveTxPower(unittest.TestCase):
    """The unset-tx_power trap: config reads the region limit, the radio sends the chip max."""

    def test_unset_becomes_region_limit_then_chip_ceiling(self):
        anz = rg.get_region("ANZ")
        self.assertEqual(anz.power_limit_dbm, 30)
        self.assertEqual(rg.effective_tx_power(0, anz, SX1262), 22)
        self.assertEqual(rg.effective_tx_power(30, anz, SX1262), 22)
        self.assertEqual(rg.effective_tx_power(0, anz, SX1276), 20)

    def test_explicit_values_pass_through_within_the_chip_range(self):
        anz = rg.get_region("ANZ")
        self.assertEqual(rg.effective_tx_power(21, anz, SX1262), 21)
        self.assertEqual(rg.effective_tx_power(-9, anz, SX1262), -9)


class TestPresets(unittest.TestCase):
    def test_time_on_air(self):
        """Semtech formula, 32 B on air: 139.8 / 312.3 / 477.2 ms."""
        for name, ms in (("MEDIUM_FAST", 139.8), ("LONG_TURBO", 312.3), ("LONG_FAST", 477.2)):
            self.assertAlmostEqual(presets.preset_time_on_air_ms(name, 32), ms, delta=0.05)

    def test_every_preset_is_in_exactly_one_family(self):
        listed = [p for members in presets.FAMILIES.values() for p in members]
        self.assertEqual(sorted(listed), sorted(presets.PRESETS))
        self.assertEqual(len(listed), len(set(listed)))

    def test_snr_floor(self):
        self.assertEqual(presets.snr_floor_db("MEDIUM_FAST"), -12.5)   # SF9


def spec(**kw):
    base = dict(region="ANZ", modem_preset="MEDIUM_FAST", channel_num=45,
                channels=(rp.Channel(0, "p", "TEST_PSK_0"), rp.Channel(1, "s", "TEST_PSK_1")),
                rebroadcast_mode="LOCAL_ONLY", position_precision=32, rx_boosted_gain=True,
                eirp_caps=CAPS)
    base.update(kw)
    return rp.RadioSpec(**base)


class TestProfile(unittest.TestCase):
    def test_profile(self):
        p = rp.build_profile(spec())
        self.assertEqual((p.channel_num_setting, p.eirp_cap_dbm, p.primary_channel.name),
                         (45, 30.0, "p"))
        self.assertIn("926.125 MHz", p.describe())
        hashed = rp.build_profile(spec(channel_num=None))
        self.assertEqual(hashed.channel_num_setting, 0)       # 0 = let the firmware hash

    def test_psks_come_from_the_variables_the_deployment_names(self):
        p = rp.build_profile(spec())
        with mock.patch.dict(os.environ, {"TEST_PSK_0": "base64:AQ==", "TEST_PSK_1": "base64:Ag=="}):
            self.assertEqual(rp.channel_psks(p), {0: "base64:AQ==", 1: "base64:Ag=="})
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError) as ctx:
                rp.channel_psks(p)
        self.assertIn("TEST_PSK_0", str(ctx.exception))
        self.assertEqual(rp.decode_psk("base64:AQ=="), b"\x01")

    def test_a_placeholder_or_malformed_key_is_refused_without_echoing_it(self):
        p = rp.build_profile(spec())
        for bad in ("base64:CHANGE_ME", "base64:AAAAAAAA"):          # not base64; 6 bytes
            with mock.patch.dict(os.environ, {"TEST_PSK_0": bad, "TEST_PSK_1": "base64:Ag=="}):
                with self.assertRaises(RuntimeError) as ctx:
                    rp.channel_psks(p)
            self.assertIn("TEST_PSK_0", str(ctx.exception))
            self.assertNotIn(bad.split(":")[1], str(ctx.exception))
        aes256 = "base64:" + "A" * 43 + "="
        with mock.patch.dict(os.environ, {"TEST_PSK_0": aes256, "TEST_PSK_1": aes256}):
            self.assertEqual(rp.channel_psks(p)[0], aes256)


if __name__ == "__main__":
    unittest.main()
