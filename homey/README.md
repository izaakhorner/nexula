# Breville AirRounder Plus → Homey Pro

A [HomeyScript](https://homey.app/en-us/homeyscript/) that controls a **Breville
"the AirRounder Plus"** heater / cooler / fan / 3-stage air purifier from Homey
Pro — heat, cool, fan-only, fan speed, sleep timer, and the light ring.

## Read this first — how the Breville actually connects

There is **no official Breville app for Homey**, and the AirRounder has no open
local API. But the smart version of this unit is a **Tuya white-label device**:
the "Breville Home Connect" app is hosted at `smartapp.tuya.com/brevilleconnect`.
That's the key that unlocks Homey.

So the connection is a two-step chain — Homey cannot talk to the Breville
directly, only *after* it's been paired via Tuya:

```
Breville AirRounder ──Wi-Fi──> Tuya cloud ──> Homey Tuya app ──> this HomeyScript
```

### Which unit do you have?

| Unit | Wi-Fi? | Works with this script? |
|------|--------|--------------------------|
| **AirRounder Plus _Connect_** (e.g. LPH708 / BPH708 / LPH408) | Yes, via Breville Home Connect (Tuya) | ✅ Yes — follow the setup below |
| **AirRounder Plus** (non-Connect) | No | ❌ Not over the network — see [No-Wi-Fi fallback](#no-wi-fi-fallback) |

If the box/manual says **"Connect"** and you set it up in the Breville Home
Connect app, you're on the supported path.

## Setup

### 1. Get the Breville into a Tuya app

You almost certainly already did this with **Breville Home Connect** — that *is*
a Tuya app, so the device now lives in your Tuya account. (If you want, you can
also add it to the generic **Smart Life** / **Tuya Smart** app with the same
account; some Homey Tuya integrations pair more reliably from there.)

### 2. Add the Tuya app to Homey and pair the device

Install one of the Tuya apps from the Homey App Store, then add the Breville as
a new device:

- **Tuya** (by Tuya Inc. / Athom) — the official cloud app, or
- **Tuya Cloud** / **Tuya Smart Life** community apps — good fallbacks.

> ⚠️ Heads-up: Tuya has periodically restricted third-party cloud API access, so
> pairing reliability can vary by app and region. If one Tuya app won't pair the
> AirRounder, try another. Once it's paired and visible in **Settings → Devices**,
> this script will find it.

### 3. Add the HomeyScript

1. Open **[my.homey.app](https://my.homey.app) → HomeyScript**.
2. Create a new script, paste in [`breville-airrounder.js`](./breville-airrounder.js).
3. Set `DEVICE_NAME` at the top to match the device's exact name in Homey.
4. **Run it once with `ACTION = 'discover'`.** The log prints every capability
   the device exposes and its current value — this tells you the real Tuya
   capability IDs for *your* pairing (they differ between firmware/apps).
5. Paste any corrected IDs into the `CAPS` map and adjust `MODE_VALUES` to match
   the mode enum options the discover run printed.

## Using it

### Manually
Edit the constants at the top and press Run:

```js
const ACTION = 'heat';
const ARG    = 22;      // °C target
```

### From a Flow (recommended)
Use the **"Run HomeyScript with argument"** Flow card and pass a small JSON
string. The Flow argument overrides the constants:

| Argument | Effect |
|----------|--------|
| `{"action":"on"}` | Power on |
| `{"action":"off"}` | Power off |
| `{"action":"heat","value":22}` | Heat mode, target 22° |
| `{"action":"cool","value":20}` | Cool mode, target 20° |
| `{"action":"fan"}` | Fan-only mode |
| `{"action":"fan_speed","value":3}` | Fan speed (step, 1–4) |
| `{"action":"timer","value":2}` | Sleep timer, 2 hours |
| `{"action":"light","value":true}` | Light ring on |
| `{"action":"status"}` | Log current state |

This lets you wire the Breville into voice control, schedules, temperature
triggers, presence, etc. — e.g. *"when bedroom drops below 19°, heat to 21°"*.

## Notes & tuning

- **Capability IDs are not guaranteed.** Tuya devices often expose generic or
  numbered data-points. The `discover` run is the source of truth — always start
  there. The script auto-detects common IDs and lets you override every one.
- **Fan speed** is sent as Homey's usual `0..1` range. If your unit uses discrete
  steps, pass a step number (1–4) and the script converts it; adjust `FAN_STEPS`
  in the script if it has a different number of speeds.
- **Timer units** depend on the Tuya data-point (hours vs minutes). Check the
  `discover` output and adjust the value you pass.
- **Temperature clamping** uses `TEMP_MIN`/`TEMP_MAX` (default 15–30 °C). Set
  these to your unit's real range and units (°C/°F) as shown on its display.

## No-Wi-Fi fallback

If you have the **non-Connect** AirRounder (no Wi-Fi), the network path above
does not exist. Your only Homey option is **infrared**:

- **Homey Pro (Early 2023)** has a built-in IR blaster. If your unit shipped with
  the round magnetic remote, you can learn its IR codes into Homey (via the
  built-in IR / a community IR app) and trigger them from Flows.
- Older Homey Pro models have no IR — you'd need an add-on IR blaster
  (e.g. a Broadlink RM via the Broadlink Homey app).

IR is one-way (no state feedback), so it can *send* heat/cool/fan/light commands
but can't read the unit's current temperature or mode. This script targets the
Wi-Fi/Tuya path; IR would be a separate setup.
