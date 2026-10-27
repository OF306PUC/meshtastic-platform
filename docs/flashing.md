# Flashing firmware

This repository ships **no firmware binaries**. Versioned UF2s in git were dead
weight that aged: the repo stayed anchored to a version nobody remembered
choosing. The source is the official
**[Meshtastic Web Flasher](https://flasher.meshtastic.org/)**, which serves both
architectures in the inventory.

The counterweight to dropping the binaries is invariant **V5**: every node
records the firmware it *measurably* runs, the validator rejects a registry with
mixed versions, and provisioning refuses a device that is off target. Mixed
firmware is mixed receive sensitivity — the `0x8B5` register patch that
improves it landed in 2.7.20/2.7.21; 2.7.19 lacks it, 2.7.26 has it — and that
reads as a propagation effect in any channel study.

## 1. Target version

Take it from the deployment registry, never from memory:

```bash
python configure.py show -d <deployment> | head -2
grep firmware_target deployments/<deployment>.yaml     # e.g. firmware_target: "2.7.26"
```

In the Web Flasher, pick exactly
that version (not "latest").

## 2. ESP32 route — LILYGO

The Web Flasher flashes ESP32 boards **directly over WebSerial** from the
browser (Chrome/Edge):

1. Plug the board in over USB; select the board model and version 2.7.26.
2. **Flash.** Choose a full erase on a board that is new to the project or comes
   from another deployment — leftover config (another PSK, another slot) is
   exactly the kind of drift that fails silently.
3. Close the browser tab before running any CLI tool: only one process can
   hold the serial port.

## 3. nRF52 route — SenseCAP Solar Node P1 Pro

The Web Flasher **downloads the UF2**; you copy it onto the drive the device
mounts in bootloader mode.

1. **Enter bootloader mode**: double-press reset, or
   `meshtastic --port <port> --enter-dfu`. A USB drive appears
   ([entering bootloader mode](https://meshtastic.org/docs/getting-started/flashing-firmware/nrf52/entering-bootloader-mode/)).
2. **Erase first if the device is new or reused**
   ([factory erase](https://meshtastic.org/docs/getting-started/flashing-firmware/nrf52/nrf52-erase/)).
   Open `INFO_UF2.TXT` on the drive:
   * it has a `Factory-Erase:` line → copy `meshtastic_factory_erase.uf2`;
   * it has none (older bootloader) → use the erase file matching the
     SoftDevice, `..._S140_7.3.0.uf2` or `..._S140_6.1.0.uf2`. **The wrong one
     can overwrite part of the SoftDevice** and leave the node needing a
     hardware programmer. Confirm the SoftDevice on each device; do not assume.
3. Re-enter bootloader mode and **copy the firmware UF2** onto the drive. It
   flashes and reboots by itself
   ([drag & drop](https://meshtastic.org/docs/getting-started/flashing-firmware/nrf52/drag-n-drop/)).

## 4. Rescue route — bootloader missing or corrupt

The UF2 procedure **requires the UF2 bootloader to already be present**: it is
the bootloader that mounts the drive you copy onto. The Web Flasher does **not**
solve a missing or corrupt bootloader. Two hardware routes, documented by
Meshtastic:

| When | Route |
|---|---|
| The drive still mounts, but the bootloader is old or misbehaving (e.g. no `Factory-Erase:` support) | [Update or recover the nRF52 bootloader](https://meshtastic.org/docs/getting-started/flashing-firmware/nrf52/update-nrf52-bootloader/) — UF2, adafruit-nrfutil, or a debugger. Verify the package checksum: a wrong bootloader can brick the board. |
| No drive mounts at all (no bootloader, or corrupt) | Program over **SWD**: a DAPLink/J-Link, or a [Raspberry Pi as the SWD programmer](https://meshtastic.org/docs/getting-started/flashing-firmware/nrf52/swdio/) with OpenOCD (`nrf5 mass_erase`, then `program firmware.hex verify`). |

## 5. After flashing: record the MEASURED version

Not the planned one — the one the device reports:

```bash
python configure.py inspect -d <deployment> --port /dev/serial/by-id/... --node N1
#   Firmware     : 2.7.26.54e0d8d
```

Write `firmware: "2.7.26"` (quoted — YAML reads `2.7` as a float) into the
node's entry, together with the `node_id` and `mac` the inspector printed, then
run `python configure.py validate -d <deployment>`. Provisioning
(`python configure.py provision`) refuses a device whose firmware is not the
deployment's `firmware_target`.
