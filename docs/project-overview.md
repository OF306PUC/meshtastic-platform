# Project overview — meshtastic-platform

> Living document: always describes the current state. If a new agent reads one
> file, it is this one. Last updated 2026-10-27.

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

## The gateway (`meshtastic-gateway`, sibling repository)

Ingestion and persistence: a Docker container that decodes what its radio
hears, measures delivery (PDR), publishes over MQTT and stores in InfluxDB,
with a dashboard; it decodes the PBX frames (portnum 256) into its
`pbx_message` measurement. Settled by the user on 2026-10-26
(`GATEWAY-DIRECTIVES.md` §0.1 there):

* **No code dependency in either direction.** The gateway forked this
  repository's `decode/` into `gateway/decode.py`; the copies are not kept in
  sync — a fix in one is not a fix in the other.
* **Pairing only through deployment membership.** The same deployment file
  exists in both repositories, kept identical by hand: same SHA-256 (the hash
  `receiver.py` records in `session.json`; the gateway prints it at start).
  The gateway reads only the fields it uses and ignores the rest, so new keys
  here do not break it — but a different node, label or cadence there makes it
  drop packets or charge phantom losses, silently.

## Current status (2026-10-27)

* **Two programs, no installation:** `configure.py` (validate / show /
  provision / inspect) and `receiver.py` (channel-study logging), run from a
  clone with `pip install -r requirements.txt`.
* **Generic radio layer:** each deployment file has a `radio` block (region,
  preset, `channel_num`, channels with `psk_env`, rebroadcast mode, precision,
  RX boosted gain, `eirp_caps`). The code holds only generic knowledge:
  presets, regions, chips (SX1262, SX1276), the slot formula, the power
  derivation.
* **Membership:** `provision` writes, and `inspect` checks, a radio's
  membership in the mesh — and nothing else.
* **Functions:** `node`, `pbx`, `gateway`, `receiver`. A `pbx` radio is driven
  over UART by a PBX (a BLE processor that multiplexes phones onto the mesh;
  nRF52840 DK prototype, nRF54L15 board being designed). Its link to the PBX
  (serial module, Bluetooth) is the PBX project's and never written here; its
  `pbx` block records the PBX processor (`hardware.PBX_MCUS`) and firmware.
  Every other radio gets the serial module off.
* **Decoder** extracted once and proven equivalent to the old decoders (271
  packets; two deliberate differences, D1/D2). PRIVATE_APP payloads (portnum
  256, the PBX frames) are recorded by size only; the gateway decodes them.
  Text messages (TEXT_MESSAGE_APP) are shown by the receiver.
* **Channels are written by index** (`--ch-set ... --ch-index i`, never
  `--ch-add`), so re-provisioning a radio converges; the inspector flags any
  enabled channel the deployment does not declare.
* **Deployment files:** `rapa-nui` (6 SenseCAP cluster nodes, a LILYGO
  gateway, 2 LILYGO receivers; sites to fill on site; channels `EasterNetT` /
  `EasterNetM` with keys of their own), `san-joaquin` (target MEDIUM_FAST; the
  radios still run LONG_TURBO; nodes 1–3, pbx radios p1/p2, gateway),
  `bench-lilygo` (6 LILYGO + receiver at 2 dBm), `mini` (3 SenseCAP nodes +
  a receiver, for end-to-end tests; channel `miniT`, key `MINI_PSK`). All on
  MEDIUM_FAST slot 45.
* **Diagrams:** `docs/diagrams/`. `mesh-platform.png` (the user's, not
  generated) is the repository's overview, shown at the top of the README.
  The detailed ones are TikZ (`build.sh` writes PNG and PDF): `membership`
  (who configures what on each radio) and `pbx-connector` (the PBX module, its
  UART connector and the radio's membership), shown in
  `docs/architecture/ADR-0002-membership-and-connectors.md` (the membership /
  connector decision, the PBX connection, the San Joaquín p1 example).
* 190 unit tests green with the repository not installed; `validate --all`
  passes with warnings only (commissioning still to record).
* **Removed** from this repo: PBX frame decoding (the gateway's), and the
  gateway-export analysis scripts (`plot_panels`, `analyze_phy`; originals in
  the monorepo).

## Vision

1. Commission nodes with `configure.py provision` + `inspect`, filling each
   node's site on site (node_id, MAC, firmware, surveyed position, antenna
   height).
2. Channel studies with `receiver.py`.
3. Bench experiments where saturating the channel is safe (`cadence_scale`).
4. If the Rapa Nui mesh works well: the PBX on a PCB, fitted to field and
   small nodes, and a mesh sniffer (`docs/scalability/README.md`).

## Architecture

```
configure.py ─────────────┐            receiver.py ──────────────────┐
                          ▼                                          ▼
meshtastic_platform/                      channel_study/
  radio/     presets · regulatory · profile ◄── listener ─► Reception ─► sinks
  registry/  load + validate deployment files   (decode + clock + file facts)
  decode/    packet dict → DecodedPacket   ◄─   gaps · summary · session.json
  provision/ plan · preflight · inspector       analysis/ (plotstyle, figures)
  cli/       meshtastic CLI runner
deployments/*.yaml   ── the application: the only place it lives; a copy of
                        each is the gateway's only link to this repository
external/            ── submodules (meshpbx; gateway later); never imported
```

Stack: Python ≥ 3.10, `meshtastic[cli]==2.7.8`, PyYAML; matplotlib, pandas,
numpy for the figures. Tests: `unittest`; lint: pyflakes. Diagrams: pdflatex.

## Key decisions and why

* **The application lives only in deployment files** (user, 2026-10-26).
  `tests/test_hard_rules.py` builds the forbidden names from the files
  themselves (deployment, channel, `psk_env`, labels) plus project names.
* **Membership vs connector** (user, 2026-10-26): this platform owns a radio's
  membership in the mesh; whatever the radio is attached to owns its link to it.
* **No code shared with the gateway** (user, 2026-10-26): the deployment file
  is the contract.
* **Scripts, not an installed package** (user, 2026-10-26). No
  `pyproject.toml`, no sys.path tricks.
* **Strict loader, no default deployment**: data analysed against the wrong
  file is silently wrong.
* **A deployment file is the target configuration**; the inspector reports
  radios not yet brought to it.
* **`tx_power` derived, enforced by equality** (field) or the chip minimum
  (bench); caps are data (`eirp_caps`).
* **Sites as an empty template** until decided; only a GPS reading on site goes
  into `surveyed` (V6).
* **`DISENO-ANTENAS-SENSORES.md` is not followed** (user instruction).

## Directory structure

See the Layout section of the README. Also `docs/` (flashing,
troubleshooting, session log, this file, `diagrams/`, `architecture/`,
`testbeds/san-joaquin.md`, `scalability/`). `report/` — the San Joaquín
characterisation report (context, methodology, analytical layer; English and
`es/`) — exists only locally: it is git-ignored, since it belongs to one
application. Updated 2026-10-27 to the split and to the target configuration.

## Known constraints and open questions

* bench-lilygo and san-joaquin share slot 45, channel names and PSKs: on air in
  the same place they hear each other (`validate --all` notes it). Give one a
  different `channel_num` if they must coexist. rapa-nui and mini share neither
  names nor keys with them, only the airtime.
* A change to a deployment file here must be copied to the gateway's copy
  (`external/meshtastic-gateway/deployments/`, which holds none yet); nothing
  checks it except comparing the SHA-256 by hand.
* **SX1276 minimum:** 2 dBm (PA_BOOST); whether the RFO output, used below
  2 dBm, reaches the antenna is unverified.
* A LILYGO indoors may get no GPS fix, hence no position flow (V3).
* Noise figure: figures use 6.0 dB; earlier analyses used 4.5 and 6.5 dB —
  unreconciled.
