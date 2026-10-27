# Scalability Study — Framing (WIP)

> **Status: EARLY STUDY.** The owner is still defining the governing equations,
> the architecture, and experimenting with the Meshtastic simulators. **Do not
> populate metrics or experiment tables yet** — this file holds the framing,
> the open questions and the ideas, so the study has a home to grow into.

## Goal

Characterise how a Meshtastic LoRa mesh behaves as it **scales** — more
nodes, more hops, more users, higher offered load — so its limits can be
predicted before they are built. The radios and their parameters (hardware,
antenna, power, role, cadences) are recorded per deployment in
`deployments/<name>.yaml`; `python configure.py show -d <name>` prints them.

## Metrics of interest (to be formalised)

Candidate metrics — equations and measurement method still **TBD by owner**:

- Packet Delivery Ratio (PDR) vs node count / hop count
- Average hop count and end-to-end latency
- Channel airtime utilisation and duty cycle (regulatory ceiling per region)
- Packet loss / collision rate under contention
- **Power consumption** per node (TX/RX/sleep duty) — of explicit interest;
  equations being defined by owner. Ties back to the solar power budget.

## Method (planned)

- **Meshtastic simulators** — the owner is exploring these to model mesh
  behaviour before and beyond the physical deployments. Record which
  simulator, version and configuration once settled.
- **Physical measurements**, from the deployments (`docs/testbeds/`):
  - `receiver.py` (this repository): per packet RSSI, SNR, hops and channel,
    every node's measurements, and the silences of each flow, with
    `session.json` tying each session to its deployment file;
  - `meshtastic-gateway`: PDR against the declared cadences, stored in
    InfluxDB. It shares no code with this repository and pairs with it
    through an identical copy of the deployment file.
- **Bench experiments** (`kind: bench`): every radio at its chip minimum, so
  the channel can be saturated on a desk; `meta.cadence_scale` divides every
  cadence to raise the offered load.
- **Analytical model** — equations relating airtime, preset and node count to
  the metrics above (owner defining).

## Open questions

- Which Meshtastic simulator(s), and how do their assumptions map to the
  presets in use (MEDIUM_FAST; LONG_FAST and LONG_TURBO as alternatives), the
  `ANZ` region and the real hardware?
- Governing equations for airtime, duty cycle, and power per node.
- Definition of "scale" for this study — node count? area? offered load? users?
- How power consumption is measured or modelled (bench vs firmware telemetry vs
  analytical).

## If the Rapa Nui mesh works well: two ideas

Not commitments: directions to study once a field mesh has proven itself.

### meshpbx on a PCB

The PCB of the prototype designed with Domi: a PBX that multiplexes the
access of several users to the Meshtastic mesh through one radio (today an
nRF52840 DK on a T-Beam's UART; the board is designed around an nRF54L15).
How far it can go is open. The idea is to fit it to field nodes such as the
SenseCAP as well as to the small radios.

- **Already in place:** a radio driven by a PBX is a `pbx` function in the
  deployment files; this platform gives it its membership in the mesh, and the
  PBX project configures the link (`docs/diagrams/pbx-connector.png`). The
  gateway decodes the PBX frames (portnum 256).
- **To study:** how many users one radio can serve before its airtime, or the
  mesh's, saturates — the scalability question proper; the power budget of a
  PBX on a solar node; which UART each host board exposes, and whether its
  pins are free.

### mesh-sniffer

Another MCU, connected by UART to a field node, that logs the reception data
of each message the node is about to relay (RSSI, SNR, hops, sender, time).
Those records can then be:

1. injected back into the mesh over the same UART, and received at a gateway;
2. offered over BLE; or
3. kept in local storage.

- **What it adds:** link measurements from inside the mesh, hop by hop. Today
  only the endpoints are measured (the receiver and the gateway see the last
  hop of each packet).
- **To study:** injecting the records adds airtime — the measurement perturbs
  the channel it measures, more so as the mesh grows; local storage or BLE do
  not. Whether the node's serial API (the same `PROTO` link the PBX uses)
  delivers the packets it relays with their reception data, or only the ones
  addressed to it.
- **In the platform** it would follow the PBX pattern: a function of its own,
  membership from the deployment file, its link owned by its own project; the
  injected records on a portnum of their own, decoded by the gateway.
