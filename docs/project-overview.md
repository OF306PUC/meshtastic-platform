# Project overview — meshtastic-platform

> Living document: always describes the current state. If a new agent reads one
> file, it is this one. Last updated 2026-11-16.

## Identity

A platform to configure the field nodes of a Meshtastic mesh from one
deployment file, verify that each radio matches it, and run a channel-study
receiver (a LoRa radio on a laptop). The code is application-agnostic: every
fact about a particular mesh — nodes, channels, slot, power limits, sites —
lives in `deployments/<name>.yaml`, and a test forbids application names in
the code.

Split out of `meshtastic-testbed-platform` (read-only reference; it has
uncommitted work). The split's guide, `REFACTOR-PLATFORM-GATEWAY.md`, now lives
in `meshtastic-gateway`. Companion repos are submodules under `external/`:
`meshpbx` (PBX firmware) and `meshtastic-gateway`, both as a reference only —
no code here imports or builds from them.

Its first real application is the SASIPA water-cluster mesh on Rapa Nui,
installed in November 2026; see
[Field deployment: Rapa Nui](#field-deployment-rapa-nui-2026-11). Its
**official** deployment file is the gateway's
`meshtastic-gateway/deployments/sasipa/rapa-nui.yaml` (user, 2026-11-16);
`deployments/rapa-nui.yaml` here is a byte-identical copy of it.

## The gateway (`meshtastic-gateway`, sibling repository)

Ingestion and persistence: a Docker container that decodes what its radio
hears, measures delivery (PDR), publishes over MQTT and stores in InfluxDB,
with a dashboard; it decodes the PBX frames (portnum 256) into its
`pbx_message` measurement. Settled by the user on 2026-10-26
(`GATEWAY-DIRECTIVES.md` §0.1 there):

* **No code dependency in either direction.** The gateway forked this
  repository's `decode/` into `gateway/decode.py`; the copies are not kept in
  sync — a fix in one is not a fix in the other. The NeighborInfo decoding
  added here on 2026-11-04 (portnum 71) has not been ported to the fork yet.
* **Pairing only through deployment membership.** The same deployment file
  exists in both repositories, kept identical by hand: same SHA-256 (the hash
  `receiver.py` records in `session.json`; the gateway prints it at start).
  For rapa-nui the official file is the gateway's
  `deployments/sasipa/rapa-nui.yaml` (user, 2026-11-16), so changes flow
  **from the gateway to here**. The two were made identical on 2026-11-16
  (SHA-256 `6935a193…`). The gateway reads only the fields it uses
  and ignores the rest, so new keys here do not break it — but a different
  node, label or cadence there makes it drop packets or charge phantom
  losses, silently.

## Current status (2026-11-16)

* **Two programs, no installation:** `configure.py` (validate / show /
  provision / inspect) and `receiver.py` (channel-study logging), run from a
  clone with `pip install -r requirements.txt`. `show --csv DIR` exports the
  registry as a spreadsheet, one CSV per MCU family (`<name>-<mcu>.csv`); it
  is export-only, never read back.
* **Generic radio layer:** each deployment file has a `radio` block (region,
  preset, `channel_num`, channels with `psk_env`, rebroadcast mode, precision,
  RX boosted gain, `eirp_caps`, `tx_power_policy`, `ble_pin_env`,
  `node_info_secs`, `neighbor_info`). The code holds only generic knowledge:
  presets, regions, chips (SX1262, SX1276), the slot formula, the power
  derivation, the firmware's beacon floors.
* **Membership:** `provision` writes, and `inspect` checks, a radio's
  membership in the mesh — and nothing else. Since 2026-10-27 that also
  covers:
  * **Bluetooth**, written explicitly: on for node, access and receiver
    radios, OFF for a gateway radio (driven over USB, nobody pairs with it),
    untouched on a pbx radio (the PBX project's).
  * **The BLE pairing PIN**, when the file names one (`ble_pin_env`):
    `FIXED_PIN` plus the PIN from `.env`, redacted in the printed plan and
    compared by `inspect` without printing it. The placeholder `CHANGE_ME` is
    refused.
  * **The two beacons**, NodeInfo and NeighborInfo, including the OFF case
    (all three NeighborInfo settings). They are written one config section at
    a time, because a multi-section write rewrites the whole device section.
    See [Beacons](#beacons-and-diagnostic-modules-2026-11-02).
* **Functions:** `node`, `pbx`, `gateway`, `receiver`, `access`.
  * An `access` radio (D1, D2 on Rapa Nui) is the door a person uses to
    reach the mesh from a phone: `CLIENT_MUTE`. Its `hop_limit` is what its
    own messages start with.
  * A `pbx` radio is driven over UART by a PBX (a BLE processor that
    multiplexes phones onto the mesh; nRF52840 DK prototype, nRF54L15 board
    being designed). Its link to the PBX (serial module, Bluetooth) is the
    PBX project's and never written here; its `pbx` block records the PBX
    processor (`hardware.PBX_MCUS`) and firmware.
  * Every other radio gets the serial module off.
* **Decoder** extracted once and proven equivalent to the old decoders (271
  packets; two deliberate differences, D1/D2).
  * PRIVATE_APP payloads (portnum 256, the PBX frames) are recorded by size
    only; the gateway decodes them.
  * Text messages (TEXT_MESSAGE_APP) are shown by the receiver.
  * NeighborInfo (portnum 71) is decoded into kind `neighborinfo`: who a node
    hears directly, with the SNR of each. It is the only source of the
    adjacency graph.
  * NeighborInfo is not a `FLOW_KIND`. `last_sent_by_id` is kept apart from
    the author, because each relay rewrites it. An empty neighbour list is an
    observation and is kept.
* **Receiver:** besides the mesh, it can log its own radio's GPS track over
  USB (`--track-secs`, costs no airtime). A (0, 0) fix is counted as no lock
  and discarded with its own counter.
* **Channels are written by index** (`--ch-set ... --ch-index i`, never
  `--ch-add`), so re-provisioning a radio converges; the inspector flags any
  enabled channel the deployment does not declare.
* **Deployment files.** All are on MEDIUM_FAST slot 45 (926.125 MHz).
  * **`rapa-nui`** — ten radios (copy of the gateway's official file):
    * N1–N6: SenseCAP Solar Node P1 Pro, `CLIENT`. `hop_limit 2` on N1,
      `3` on N2–N6.
    * GW: LILYGO, `gateway`, `CLIENT_MUTE`.
    * D1, D2: LILYGO, `access`, `hop_limit 1`.
    * Rx: LILYGO, `receiver`, `CLIENT_MUTE`, the channel-study radio.
    * Node IDs and MACs are recorded. Sites carry the SASIPA asset codes.
    * Channels are `EasterNetT` (telemetry) and `EasterNetM` (messaging).
    * `tx_power_policy: declared` at 30 dBm, which the SX1262 clamps to
      22 dBm.
    * NodeInfo every 2 h. NeighborInfo every 4 h, on air.
    * BLE PIN named by `RAPA_NUI_BLE_PIN`.
    * Every node is still `status: planned` with empty `surveyed`; see
      [Field deployment](#field-deployment-rapa-nui-2026-11).
  * **`bench-lilygo`** — 6 LILYGO plus a receiver, at 2 dBm.
  * **`mini`** — 3 SenseCAP plus a receiver, for end-to-end tests. It has no
    `ble_pin_env`, which validation reports as R3.
  * **Removed on 2026-10-30:** `san-joaquin`, `san-joaquin-longturbo` and
    `office-bench` were deleted together with the PSKs committed with them
    (rule: one radio, one identity).
* **Diagrams:** `docs/diagrams/`.
  * `mesh-platform.png` (the user's, not generated) is the repository's
    overview, shown at the top of the README.
  * The detailed ones are TikZ (`build.sh` writes PNG and PDF; the outputs
    are git-ignored):
    * `membership`: who configures what on each radio.
    * `pbx-connector`: the PBX module, its UART connector and the radio's
      membership. Shown in
      `docs/architecture/ADR-0002-membership-and-connectors.md`.
    * `rebroadcast`, plus the channel-access set (`trip`, `loop`, `irq`,
      `model`, `window`). Drawn from firmware v2.7.26: CWmin/CWmax 3/8; a
      CLIENT relays no sooner than 2·CWmax = 16 slots = 272 ms.
* **Health:** 256 unit tests green with the repository not installed.
  `validate --all` passes with warnings only:
  * the declared power (V2);
  * commissioning still to record (P);
  * NeighborInfo on air (R2);
  * mixed MCU families (V8);
  * mini's missing BLE PIN (R3).
* **Removed** from this repo: PBX frame decoding (the gateway's), and the
  gateway-export analysis scripts (`plot_panels`, `analyze_phy`; originals in
  the monorepo).

## Field deployment: Rapa Nui (2026-11)

The deployment guide (Spanish, LaTeX) and the field itinerary live outside
this repository, in `network-platforms/SASIPA_mesh_deploy/`.

* **Preset: MEDIUM_FAST slot 45** (user, 2026-11-06). LONG_FAST was
  evaluated and dropped, for three reasons:
  * Its slot 20 (919.875 MHz) falls outside the SUBTEL j.4 band and loses the
    30 dBm exception, which would put the fibreglass nodes above the cap.
  * Time on air would grow 3.5×.
  * At that channel load NeighborInfo, which only transmits under the
    "polite" channel-utilisation threshold, could stop filling the graph.
* **N6 sits at the SASIPA plant, beside GW** (user, 2026-11-06), so the
  `rapa-nui.yaml` comment calling it the "centralising node" that relays the
  cluster is stale. The RE site stays a candidate relay, not installed.
* **N6 stays `CLIENT`** (2026-11-04, from the firmware):
  * `REPEATER` is deprecated since 2.7.11 and hides the node from the list.
  * `ROUTER` adds redundant relays, not paths.
  * `CLIENT_BASE` behaves like `CLIENT` here, because no favourites are
    written.
  * If a relay is ever needed, the candidate is `ROUTER_LATE`, chosen with
    measured data.
* **Installed positions** come from the nodes' own GPS fixes (receiver run of
  2026-11-11). Compared with `planned`:
  * N1–N3 moved 16–22 m.
  * N6/GW moved 51 m.
  * N4 is 1.0 km south.
  * N5 is 593 m away.
* **Line of sight at the installed sites.** The model is SRTM 30 m and 90 m
  relief, k = 4/3, 6 m masts assumed, keeping the worse of the two reliefs:
  * N1, N3 and N5 clear the first Fresnel zone to N6/GW (143, 72 and 107 %).
  * N4 has no LoS to GW (−25 %); its only clear link is N3 (139 %).
  * N2 has no clear link.

  GPS altitude was too noisy (±10 m) to measure the masts. These are
  predictions until NeighborInfo measures the real graph.
* **The registry does not yet describe the installed mesh.** Every node is
  `planned`, with empty `surveyed` and `antenna_height_m`.
  * The user's rule (gateway session, 2026-11-16): the source of truth for a
    position is the GPS fix measured on site, which is what the nodes
    transmit. A measured position that is needed goes into `surveyed`.
  * Rule 11 still forbids desk coordinates.
  * Any change is made in the gateway's official file first and copied here.

## Vision

1. Record the Rapa Nui commissioning (status, surveyed positions, antenna
   heights) in the gateway's official file, and keep the copy here identical.
2. Measure the real adjacency graph from NeighborInfo. Possibly add a
   traceroute wrapper that records each trace as a measurement.
3. Channel studies with `receiver.py`.
4. Bench experiments where saturating the channel is safe (`cadence_scale`).
5. If the Rapa Nui mesh works well: the PBX on a PCB, fitted to field and
   small nodes, and a mesh sniffer (`docs/scalability/README.md`).

## Architecture

```
configure.py ─────────────┐            receiver.py ──────────────────┐
                          ▼                                          ▼
meshtastic_platform/                      channel_study/
  radio/     presets · regulatory · profile ◄── listener ─► Reception ─► sinks
  registry/  load + validate + export (csv)     (decode + clock + file facts)
  decode/    packet dict → DecodedPacket   ◄─   gaps · summary · session · track
  provision/ plan · preflight · inspector       analysis/ (plotstyle, figures)
  cli/       meshtastic CLI runner
deployments/*.yaml   ── the application: the only place it lives; a copy of
                        each is the gateway's only link to this repository
deployments/sasipa-info/ ── SASIPA's site list and asset cadastre (source data
                        for rapa-nui's planned sites)
external/            ── submodules (meshpbx, meshtastic-gateway); never imported
```

Stack: Python ≥ 3.10, `meshtastic[cli]==2.7.8`, PyYAML; matplotlib, pandas,
numpy for the figures. Target firmware 2.7.26. Tests: `unittest`; lint:
pyflakes. Diagrams: pdflatex.

## Key decisions and why

* **The application lives only in deployment files** (user, 2026-10-26).
  `tests/test_hard_rules.py` builds the forbidden names from the files
  themselves (deployment, channel, `psk_env`, labels) plus project names.
* **Membership vs connector** (user, 2026-10-26): this platform owns a radio's
  membership in the mesh; whatever the radio is attached to owns its link to it.
* **No code shared with the gateway** (user, 2026-10-26): the deployment file
  is the contract.
* **The official rapa-nui file lives in the gateway** (user, 2026-11-16):
  `meshtastic-gateway/deployments/sasipa/rapa-nui.yaml`. This repository
  keeps a byte-identical copy, because `configure.py` reads only
  `deployments/*.yaml`.
* **Scripts, not an installed package** (user, 2026-10-26). No
  `pyproject.toml`, no sys.path tricks.
* **Two cadences for the receiver's own position** (user, 2026-10-27): what the
  radio puts on air is a declared `position` flow in the deployment file; how
  often the laptop reads that radio's fix over USB is `--track-secs`, a property
  of the recording machine. Reading costs no airtime, so a channel study can
  trace its route without filling the channel it measures.
* **Strict loader, no default deployment**: data analysed against the wrong
  file is silently wrong.
* **A deployment file is the target configuration**; the inspector reports
  radios not yet brought to it.
* **`tx_power` derived, enforced by equality** (field) or the chip minimum
  (bench); caps are data (`eirp_caps`). One escape hatch, in the file:
  `tx_power_policy: declared` writes each node's own number and turns the V2
  errors into warnings printed on every run (rapa-nui; user, 2026-10-30).
* **One radio, one identity** (2026-10-30): a `node_id` belongs to one
  deployment. A planned node does not claim a concrete radio. Retiring a
  radio means `node_id: null`, because `Registry.by_node_id` ignores
  `status`.
* **D1/D2 are `access`, not `pbx`** (user, 2026-10-30): turning them into pbx
  radios would switch messaging off before the meshpbx replacement works.
* **The spreadsheet is export-only** (2026-10-30): a sheet that could be read
  back would be a second place the mesh is declared.
* **Beacons go in `radio:`, not in `intervals:`** (2026-11-02): at hours scale
  there is no cadence to estimate a gap against, and keeping them out of
  `intervals` keeps them out of `cadence_scale`.
* **BLE is written, never assumed; its PIN lives in `.env`** (2026-10-30 to
  11-06). A screenless board otherwise pairs with the published default PIN.
* **Sites as an empty template** until decided; only a GPS reading on site goes
  into `surveyed` (V6).
* **`DISENO-ANTENAS-SENSORES.md` is not followed** (user instruction).

## Directory structure

See the Layout section of the README. Also:

* `docs/`: flashing, troubleshooting, the session log, this file,
  `diagrams/`, `architecture/` (ADR-0001, ADR-0002), `scalability/` and
  `testbeds/`.
* `docs/testbeds/`: `san-joaquin.md`, and `range-test-lilygo.md`, a field
  range test with two T-Beams and the phone app only.
* `deployments/_template.yaml` and `deployments/sasipa-info/`.
* `report/`: the San Joaquín characterisation report (context, methodology,
  analytical layer; English and `es/`). It exists only locally and is
  git-ignored, since it belongs to one application.

## Known constraints and open questions

* All three deployment files share slot 45. `validate --all` no longer finds
  shared channel names or keys between them, so on air in the same place they
  share only the airtime.
* The two copies of rapa-nui are kept identical by hand, from the gateway's
  official file to `deployments/rapa-nui.yaml`. Nothing checks it except
  comparing the SHA-256. The submodule pin `external/meshtastic-gateway`
  (efaca4c) is behind the gateway's HEAD and holds an older copy; it is a
  reference, not the copy that counts.
* Pending edits to rapa-nui, made in the official file and batched so the
  SHA moves once:
  * N6's "centralising node" comment.
  * A note in the slot plan that changing slot can change the EIRP cap that
    applies.
  * The commissioning record of the installed mesh.
* Two campus PSKs leaked in `cebcf4f` were still to be rotated as of
  2026-11-04.
* **SX1276 minimum:** 2 dBm (PA_BOOST); whether the RFO output, used below
  2 dBm, reaches the antenna is unverified.
* A LILYGO indoors may get no GPS fix, hence no position flow (V3).
* Noise figure: figures use 6.0 dB; earlier analyses used 4.5 and 6.5 dB —
  unreconciled.

### Beacons and diagnostic modules (2026-11-02)

Besides the measured flows in `intervals`, a radio emits two background
beacons, and both are now declared in the `radio:` block — not as flows.
NodeInfo cannot be switched off and every node emits it; NeighborInfo is
floored by the firmware at four hours. At that scale there is no cadence for
the gap estimator to measure against, so they are mesh-wide policy, like
`rebroadcast_mode`. Keeping them out of `intervals` also keeps them out of
`cadence_scale`, which would otherwise push a bench value below the firmware
floor and make `inspect` report drift for ever.

* **NodeInfo** — `radio.node_info_secs`, required, never 0 (the firmware reads
  0 as "use the default"). Floor 3600 s, firmware default 10800. rapa-nui runs
  7200.
* **NeighborInfo** (portnum 71) — `radio.neighbor_info`, the block omitted
  when the mesh does not want it.
  * Omitted, provisioning writes all three settings off:
    `enabled false`, `update_interval 0`, `transmit_over_lora false`.
  * Floor 14400 s.
  * `transmit_over_lora` is the only field that costs airtime. When it is
    false, the firmware swaps the destination for `NODENUM_BROADCAST_NO_LORA`
    and delivers the beacon locally only.
  * rapa-nui runs 14400 on air, which `validate` reports as an R2 warning on
    every run. The receiver decodes the beacons as kind `neighborinfo`.
* **Duty:** measured with the repo's own `presets.time_on_air_ms` at
  MEDIUM_FAST, over nine nodes and seven transmissions per broadcast:
  * rapa-nui's NodeInfo at 2 h: 0.27 %.
  * NeighborInfo at 4 h: 0.16 %.
  * The 120 s device telemetry: **8.95 %**.

  Seven transmissions is the worst case: a `CLIENT` cancels its relay when it
  hears another one first. The beacons are noise next to the study's own
  flows, which is why the fast end of the allowed range is the right choice
  rather than the slow one.

Still not configured, and deliberately:

* **Range Test** (`range_test`, portnum 66). Its settings are `enabled`,
  `sender` (0 = receive only), `save` and `clear_on_reboot`.
  * `save` writes `rangetest.csv` to flash on **ESP32 only**: the T-Beams,
    not the nRF52840 SenseCAPs. Retrieving it needs Wi-Fi, which this
    platform never configures.
  * Saturating the channel is its purpose, so it belongs on a bench or on a
    mobile site survey, never on a mesh being measured.
  * The firmware stops the sender after 8 hours by itself.
  * `docs/testbeds/range-test-lilygo.md` runs it from the phone app only.
* **Traceroute** (portnum 70). No config block exists; it is invoked per
  command (`meshtastic --traceroute '!xxxxxxxx'`).
  * One request per 30 s per sending node, up to 8 hops per direction, with
    per-hop SNR in 0.25 dB steps.
  * Nothing to provision. What is missing is a wrapper that runs it against a
    deployment's refs and records the result as a measurement.
  * A `CLIENT_MUTE` radio never appears as an intermediate hop, so GW, D1 and
    D2 can be the destination of a trace but never a waypoint.

Neither of those two is a declared flow, so their portnums land in
`DecodeStats.unknown_portnum`: counted and named, but not attributable to any
cadence — which is what hard rule 3 exists to prevent. Adding one as a flow
means extending `FLOW_KINDS` (today `device`, `environment`, `position`) and
`decode()` in the same change.
