# Range test — two LILYGO T-Beam (SX1276), no laptop in the field

> **Brief for the agent running this campaign.** Read it end to end before
> touching a radio. It tells you what to build, what the platform already does
> for you, and the ways this measurement fails *without producing an error*.
> Everything else here assumes you did not skip §9.

## 0. The job

Measure, with **two LILYGO T-Beam radios**, how far a link holds and what the
channel looks like along the way — once on **`MEDIUM_FAST`** and once on
**`LONG_FAST`** — and produce a comparison between the two.

This repeats, at two nodes, what `deployments/rapa-nui.yaml` does at nine. The
radios are different (SX1276 instead of the field SenseCAP's SX1262) and the
antennas are different, so **none of the field deployment's RSSI numbers carry
over**. What carries over is the method.

**Deliverable:** a log table per preset, a testbed page in this directory
(`docs/testbeds/<site>.md`, in the shape of [`san-joaquin.md`](san-joaquin.md))
and a comparison that states at minimum:

- SNR against distance, per preset, in **both directions** of the link;
- the distance at which the link stops closing, and whether range or terrain
  closed it;
- the measured cost of `LONG_FAST`: it buys **5 dB** of link budget and charges
  **3.5×** the airtime (600.1 ms vs 170.5 ms for a 48-byte frame). That trade
  is the whole point of the campaign.

## 1. What the test needs

**In the field — this and nothing else:**

- the two T-Beam radios, each with a **charged 18650**;
- **two phones with the Meshtastic app**, one paired by BLE to each radio;
- something to hold the fixed radio up, and a way to record a table.

No laptop, no USB, no `receiver.py`. The phones are the instrument: the app's
node list is where you read SNR, last-heard time and distance.

**At the bench, once, before going out:** a computer with this repository and a
USB cable, to provision both radios (§5). That is the only step that needs one.

Two consequences you have to plan for:

- **Battery bounds the outing.** No solar here. The fixed radio has to survive
  unattended for the whole walk plus the walk back, transmitting on every
  cadence. Charge both cells full, and bring the fixed one back before you
  trust a long silence — a flat cell and a dead link look identical from the
  far end.
- **Both phones must be in Bluetooth range of their radio the whole time.**
  The walker's phone is what logs the position; if it unpairs, the stop is lost.

## 2. Where you are

A platform that configures the field radios of a Meshtastic mesh from a
deployment file and verifies them. Read `CLAUDE.md` first — it is short and
every rule in it is enforced by a test or by CI. The ones that will bite here:

- **The campaign lives only in `deployments/*.yaml`.** No site name, node
  label, channel name or key goes into `meshtastic_platform/`, `channel_study/`
  or the two scripts. `tests/test_hard_rules.py` builds the forbidden list from
  the deployment files themselves and will fail you.
- **No implicit deployment.** Every tool takes `--deployment`/`-d` or
  `MESH_DEPLOYMENT`. Nothing defaults.
- **`tx_power` is derived**, from antenna gain, the file's `eirp_caps` and the
  chip's valid settings — never chosen by hand.
- **Surveyed positions are never written to a radio**, smart position broadcast
  stays off, and a listen-only receiver is `CLIENT_MUTE` (**I5**).
- **No secrets in git**: PSKs live in `.env`, referenced by `psk_env`.
- **Fail loudly or report what was discarded.**
- The repository is **not installed**: run the scripts from the clone,
  `requirements.txt` only. No `pip install -e`, no `sys.path` tricks.

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -t .   # green before you start
```

## 3. What you do not have to build

| You need | Use |
|---|---|
| Write a radio's membership | `configure.py provision -d <dep> --node <ref> --port <port>` |
| Check a radio against the file | `configure.py inspect …` — exits 1 on any drift |
| See what a file will write | `configure.py show -d <dep>` |
| Check the file itself | `configure.py validate -d <dep>` |

`receiver.py` and `channel_study/` are the laptop-based path. **They are out of
scope for this campaign** — they exist, they are good, and they need a computer
on the walk. Do not reach for them and do not modify them.

## 4. Step 1 — the deployment file

Create `deployments/range-lilygo.yaml`. Start from
[`bench-lilygo.yaml`](../../deployments/bench-lilygo.yaml), which is already a
LILYGO-only file and carries the SX1276 notes.

```yaml
# deployments/range-lilygo.yaml — two-radio range and channel test, read from
# the Meshtastic app. T1 is fixed at a known point; R1 is carried.
#
# BOTH radios emit position and device telemetry, so each phone shows the
# other node's distance and SNR: the link gets measured in both directions.

meta:
  deployment: range-lilygo
  kind: bench                    # not the field mesh; never on air at the same time
  description: Two-radio LoRa range test, SX1276, phone-read
  firmware_target: "2.7.26"      # identical on both radios, or the comparison is not one

radio:
  region: ANZ
  modem_preset: MEDIUM_FAST      # session 2 switches this; the slot does NOT move
  channel_num: 45                # 926.125 MHz on BOTH presets — see §7
  channels:
    - {index: 0, name: <channel name>, psk_env: <ENV VAR NAME>}
  rebroadcast_mode: LOCAL_ONLY
  position_precision: 32
  rx_boosted_gain: true          # SX1262 only; the planner skips it on an SX1276
  node_info_secs: 10800
  # The BLE pairing PIN: the NAME of the .env variable, never the number.
  # Without it both radios keep the firmware default, which is published.
  ble_pin_env: <ENV VAR NAME>
  eirp_caps:
    - {band_mhz: [915, 928], eirp_dbm: 27, label: "SUBTEL j.3"}
    - {band_mhz: [913, 919], eirp_dbm: 30, label: "SUBTEL j.4"}
    - {band_mhz: [925, 928], eirp_dbm: 30, label: "SUBTEL j.4"}

nodes:
  - ref: T1                      # fixed, high, known point
    function: node
    status: planned
    node_id: null                # filled from `inspect` after the first provision
    mac: null
    hardware: lilygo_tbeam_sx1276
    mcu: esp32
    firmware: null
    role: CLIENT
    hop_limit: 1                 # two radios: nothing to relay, nothing ambiguous
    antenna: {type: <real type>, gain_dbi: <REAL>, band_mhz: null, model: <model>}
    site: {name: <fixed point>}
    intervals: {device: 60, position: 60}
    sensors: []

  - ref: R1                      # carried
    function: receiver
    status: planned
    node_id: null
    mac: null
    hardware: lilygo_tbeam_sx1276
    mcu: esp32
    firmware: null
    role: CLIENT_MUTE            # I5: a sink that relays contaminates its own measurement
    hop_limit: 1
    antenna: {type: <real type>, gain_dbi: <REAL>, band_mhz: null, model: <model>}
    site: {name: walking}
    intervals: {device: 60, position: 60}
    sensors: []
```

```bash
.venv/bin/python configure.py validate -d range-lilygo
.venv/bin/python configure.py show     -d range-lilygo   # read the DERIVED tx_power here
```

Three things to decide before you fill the placeholders:

**The antenna gain must be the real one.** It is not decoration: `tx_power` is
derived from it, so an inflated figure makes the platform *lower* the power and
your range collapses for a reason you will not see in the data.

**The cadence sets your resolution.** 60 s means a fresh SNR reading roughly
every minute; at a walking pace that is about one sample per 80 m, and at a
stop it means waiting up to a minute for a reading. Pick the number from how
long you are willing to stand still, and declare it in the file.

**R1 is `receiver` but still emits.** `CLIENT_MUTE` means it does not relay
*other* traffic; it transmits its own just fine. That is what gives you the
reverse direction of the link and the distance readout on T1's phone.

## 5. Step 2 — the bench (the only step with a computer)

Provision **both** radios. The carried one is a radio too, and a radio on
another preset or another key hears nothing and says nothing.

```bash
.venv/bin/python configure.py provision -d range-lilygo --node T1 --port <port> --dry-run
.venv/bin/python configure.py provision -d range-lilygo --node T1 --port <port>
.venv/bin/python configure.py inspect   -d range-lilygo --node T1 --port <port>   # exits 1 on drift
```

Repeat for `R1`. From each `inspect`, copy `node_id`, `mac` and `firmware` back
into the file **in quotes** — YAML reads an unquoted `!` as a tag and `2.7` as
a number:

```yaml
    node_id: "!6c72f308"
    mac: "A0:DD:6C:72:F3:08"
    firmware: "2.7.26"
```

Then `validate` again, and **pair each phone to its radio at the bench**, not
in the field: you need the BLE PIN, and discovering that it is wrong on a hill
is an afternoon lost.

## 6. Step 3 — the walk

Leave T1 at the fixed point, as high and as clear as you can get it, and note
its coordinates from the phone that is paired to it. Then walk away in steps.

**At each stop, with the phone, record one row:**

| Field | Where it comes from |
|---|---|
| stop number, time | you |
| coordinates | the walking phone's GPS |
| distance | computed afterwards from the coordinates; the app also shows it when both radios have a fix — log both and use the disagreement as a check |
| **SNR of the last packet from T1** | the app's node list, on the walker's phone |
| **SNR of the last packet from R1** | the app's node list, on T1's phone (read it on the way back, or have a second person there) |
| seconds since last heard | the app's node list — this is how you see the link degrade before it dies |
| message delivered? | send a short text from the walker and record whether the app marks it delivered, and after how long |
| terrain | one line: line of sight, trees, a ridge in the way, a building |
| photo | optional, but the terrain line is worth more with one |

Walk until you lose the link, then take **two more stops back toward T1** to
find where it recovers. The recovery point is a better number than the loss
point: losing a link once can be a passing obstruction, recovering it twice is
a distance.

**Keep a stop at zero.** The first row, with both radios a few metres apart, is
your reference: it tells you what "perfect" looks like on this hardware and
makes every later SNR readable as a drop from it.

If your app build offers the **Range Test module**, you may enable it on T1 to
send numbered messages automatically instead of typing them. Treat it as a
convenience, not the method: getting its saved CSV off the device generally
needs a computer, which is exactly what this campaign does not have in the
field. The log table is the deliverable.

## 7. Step 4 — the second preset, without going back to the bench

Change `MEDIUM_FAST` → `LONG_FAST` **from the app**, on both radios, at the
fixed point — radio settings are reachable over BLE.

**Do not change the frequency slot.** Both presets use BW 250 kHz, so they
share the same 52-slot grid in ANZ: slot 45 is **926.125 MHz on both**. Leaving
the slot alone is not laziness, it removes a confound — the only thing that
differs between your two datasets should be the modulation.

Then walk the same route again, same stops, same antenna heights, same day if
you can.

Two obligations that come with configuring from the app:

1. **Edit the deployment file to match** (`modem_preset: LONG_FAST`) before
   you analyse the second session. The file is what says which configuration
   produced which data.
2. **Run `inspect` on both radios when you get back.** It is the only thing
   that tells you what the radios actually ran, as opposed to what you meant to
   set. If the app changed something you did not intend, that is where it
   surfaces.

## 8. Analysis

Distance from the logged coordinates; SNR from the log; one chart per preset,
both directions on the same axes.

The free-space upper bound, for orientation only — it is the number terrain
will make a liar of, which is the finding worth reporting:

| Preset | Sensitivity | Link budget at 20 dBm, 2 dBi both ends | FSPL range |
|---|---|---|---|
| `MEDIUM_FAST` | −126.5 dBm | 150.5 dB | ~866 km |
| `LONG_FAST` | −131.5 dBm | 155.5 dB | ~1550 km |

Nobody will walk that far. The gap between those numbers and what you measure
**is** the result: Fresnel clearance and terrain decide range here, not link
budget. Report the measured distance, the terrain where it failed, and the SNR
at which packets started dropping.

Watch for **asymmetry**: if T1 hears R1 well past the distance at which R1
hears T1, the difference is in the antennas, the heights or the surroundings of
each end — not in the radios. That is a real finding and it only appears
because both directions were logged.

## 9. The silent failures

None of these print an error. Each produces a plausible-looking empty result.

1. **A regenerated PSK.** An existing key is *copied* from whoever provisioned
   the mesh, never regenerated. A new key leaves the radio deaf and mute with
   no error. The value includes the `base64:` prefix.
2. **Preset or slot mismatch between the two radios.** They simply do not hear
   each other. After a field preset change, confirm on *both* phones that the
   other node is still listed before you start walking.
3. **18 or 19 dBm.** RadioLib refuses them on the SX1276's PA_BOOST output and
   the node records a critical `INVALID_RADIO_SETTING`. Valid: 2–17, or exactly
   20. Below 2 the driver switches to the RFO output, a different RF path that
   does not reach the antenna on every board. This is why `tx_power` is derived
   and not typed.
4. **A stale SNR.** The app shows the SNR of the **last** packet heard, not of
   now. At a 60 s cadence, a reading taken ten seconds after arriving at a stop
   describes the previous stop. Always log the seconds-since-last-heard beside
   the SNR, and wait for it to reset before writing the row.
5. **No GPS fix.** Under cover, a T-Beam sends no position packets at all, and
   the app's distance stops updating while the SNR keeps arriving — a stop that
   looks measured and has no position. The walking phone's own GPS is the
   fallback; log it every time.
6. **Smart position broadcast turned back on.** It fires on movement, so there
   is no cadence left to read against. The platform writes it off; do not turn
   it on from the app "to get more samples".
7. **A flat cell at the fixed end.** Indistinguishable from an out-of-range
   link. If the link does not recover on the way back, suspect the battery
   before you write down a range.
8. **Two deployments on air at once.** Slot 45 is the campus testbed's slot
   too. The data looks fine and belongs to neither.

## 10. Out of scope

- `receiver.py` and `channel_study/`: the laptop path. Not used, not modified.
- The gateway (`meshtastic-gateway`): not used here at all.
- `DISENO-ANTENAS-SENSORES.md`: **do not follow it** (standing user
  instruction), whatever other documents point at it.
- Anything that writes a surveyed position into a radio.
- Changing `decode()`: it stays pure — no clock, no I/O, no deduplication.

## 11. When you finish

- `docs/testbeds/<site>.md`, in the shape of `san-joaquin.md`: identity, what
  runs there, state of the radios, site, history, open questions.
- The log tables, as data, beside that page.
- An entry at the **top** of `docs/session-log.md`, in Spanish, with the date,
  what was asked, what was done, what was decided and why, and what is open.
- The deployment file with `node_id`, `mac` and `firmware` filled in, and the
  preset the radios were left on.

Conversation with the user is in neutral Spanish; everything written — code,
docs, registries — in English, except `docs/session-log.md`.
