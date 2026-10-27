# Testbed — San Joaquín

> One document per physical deployment. The radios themselves — IDs, hardware,
> roles, cadences, antennas, positions — are in
> [`deployments/san-joaquin.yaml`](../../deployments/san-joaquin.yaml) and
> nowhere else; `python configure.py show -d san-joaquin` prints them. This page
> holds what that file cannot: the site, the history, the open questions.
> Fields marked _TBD (owner)_ need data only the deployer has.

## Identity

- **Site:** San Joaquín campus, Pontificia Universidad Católica de Chile.
- **Operated by:** Cyber-Physical Systems Research and Technology Center (CPS-RTC).
- **Purpose:** outdoor LoRa mesh testbed: environmental monitoring
  (temperature, humidity, position, power), the PBX prototypes on a live mesh,
  and the measurements behind the scalability study.
- **Status:** live. Nodes 1–3 deployed; the pbx radios p1 (MIDE) and p2 (DIE)
  installed; the gateway in exploration.

## What runs there

```
[node 1] [node 2] [node 3]          SenseCAP Solar Node P1 Pro, SHT4X
[p1 · MIDE] [p2 · DIE]              LILYGO T-Beam driven by a PBX (nRF52840 DK)
          ~~~~ LoRa mesh ~~~~
                 │
       [gateway radio · T-Beam] ──USB── Raspberry Pi (5G HAT under study)
                                            └─ meshtastic-gateway: PDR · MQTT · InfluxDB · dashboard
```

- **Membership** of every radio (region, preset, slot, channels, role, hop
  limit, tx_power, cadences) is written by `configure.py provision` from the
  deployment file. The pbx radios' link to their PBX is configured by the PBX
  project (`external/meshpbx`).
- **The gateway** (`meshtastic-gateway`) shares no code with this platform: it
  pairs through an identical copy of `deployments/san-joaquin.yaml`. Compare
  the two copies' SHA-256 before every campaign (its `deployments/README.md`).
  It decodes the PBX frames (portnum 256) into its `pbx_message` measurement.
- **Channel studies** run `receiver.py` on a laptop with a receiver radio
  registered in the file (none is registered yet).

## State of the radios

The deployment file is the **target** configuration. Until each radio is
reprovisioned, `python configure.py inspect -d san-joaquin --port ...` reports
it as drifted — that report is the list of radios still to do. What they run
today, and what the recorded data was taken under:

- modem preset **LONG_TURBO** (target: MEDIUM_FAST, slot 45 = 926.125 MHz).
  Radios set up before the team's slot plan sit on the firmware's hash slot
  17 = 923.25 MHz rather than the plan's 14 = 921.75 MHz;
- tx_power never set: the radios transmitted their chip ceiling;
- node 1 `CLIENT_BASE` and node 3 `CLIENT` (the target swaps them);
- firmware 2.7.26 (commit 54e0d8d) on nodes 1–3; not recorded for p1, p2 and
  the gateway;
- p1 and p2 never delivered a position packet against their declared 1800 s
  cadence (analysis of 2026-09-02).

The characterisation report of this testbed (`report/`, kept locally, not in
git) and every measurement recorded so far were taken under that
configuration: analyse them with `--preset LONG_TURBO`.

## Site & location

- **Area / building references:** _TBD (owner)_ — p1 is at MIDE, p2 at DIE.
- **Approximate extent (m):** _TBD (owner)_
- **Terrain / obstacles (line-of-sight notes):** _TBD (owner)_
- **Power per site (solar vs mains):** _TBD (owner)_
- **Antenna heights:** _TBD (owner)_ — `site.antenna_height_m` per node in the
  deployment file; the link model needs them.

## Deployment history

_TBD (owner)_ — a dated log of what was installed, moved or changed on site.

## Open questions

- The gateway radio's node ID: read it with `configure.py inspect` once the
  T-Beam is behind the Pi.
- Firmware of p1, p2 (radio and PBX) and of the gateway radio.
- Whether any SenseCAP antenna was replaced, and whether the T-Beams carry the
  stock antenna (assumed in the file).
- Whether the 5G backhaul changes anything on the mesh side (it should not:
  the gateway radio stays `CLIENT_MUTE`).
