/**
 * ============================================================================
 *  Breville "the AirRounder Plus Connect" — Homey Pro control script
 * ============================================================================
 *
 *  Runs in HomeyScript (Homey Pro).  Controls a Breville AirRounder Plus
 *  (heater / cooler / fan / 3-stage air purifier) that has been paired into
 *  Homey via a Tuya app (see homey/README.md for why and how).
 *
 *  It gives you one place for every function you asked for:
 *      • power on / off
 *      • heat  (with target temperature)
 *      • cool
 *      • fan-only
 *      • fan speed
 *      • sleep timer
 *      • light ring on / off
 *
 *  --------------------------------------------------------------------------
 *  HOW TO USE
 *  --------------------------------------------------------------------------
 *  1. First run: leave ACTION = 'discover'. The log will print the device it
 *     found and EVERY capability it exposes together with the current value.
 *     Copy those capability IDs into the CAPS map below if the auto-detected
 *     ones are wrong (Tuya pairings vary — this is expected).
 *
 *  2. Run an action manually by editing ACTION / ARG at the top, OR
 *
 *  3. Call it from a Flow with the "Run HomeyScript with argument" card and
 *     pass a small JSON string as the argument, e.g.
 *          {"action":"heat","value":22}
 *          {"action":"cool"}
 *          {"action":"fan_speed","value":3}
 *          {"action":"timer","value":2}
 *          {"action":"light","value":true}
 *          {"action":"off"}
 *     (The Flow argument, if present, overrides the ACTION/ARG constants.)
 * ============================================================================
 */

// ----------------------------------------------------------------------------
// CONFIG — edit these
// ----------------------------------------------------------------------------

// The exact device name as it appears in Homey (Settings → Devices).
const DEVICE_NAME = 'Breville AirRounder';

// Default action + argument when the script is run manually (no Flow argument).
// Actions: 'discover' | 'on' | 'off' | 'heat' | 'cool' | 'fan' |
//          'fan_speed' | 'timer' | 'light' | 'status'
const ACTION = 'discover';
const ARG    = null;          // e.g. 22 for heat, 3 for fan_speed, true for light

// Temperature range the unit accepts (used for clamping). Adjust if needed.
const TEMP_MIN = 15;
const TEMP_MAX = 30;

/**
 * Capability-ID overrides. Leave a value as null to auto-detect. After the
 * first 'discover' run, paste the real IDs here so behaviour is deterministic.
 * Common Tuya-paired IDs are listed as hints.
 */
const CAPS = {
  onoff:        null, // 'onoff'
  mode:         null, // 'thermostat_mode' | 'breville_mode' | 'fan_mode'
  target_temp:  null, // 'target_temperature'
  measure_temp: null, // 'measure_temperature'
  fan_speed:    null, // 'legacy_fan_speed' | 'fan_speed' | 'dim'
  timer:        null, // 'breville_timer' | 'dim.timer'
  light:        null, // 'onoff.light' | 'breville_light'
};

// Values your unit expects for its mode capability. Discover run will show the
// enum options; adjust these strings to match exactly.
const MODE_VALUES = {
  heat: 'heat',
  cool: 'cool',
  fan:  'fan_only',
};

// ----------------------------------------------------------------------------
// Helpers (you shouldn't need to edit below here)
// ----------------------------------------------------------------------------

const clamp = (n, lo, hi) => Math.min(hi, Math.max(lo, n));

/** Pick the first capability ID on the device matching one of `candidates`. */
function pick(device, override, candidates) {
  if (override && device.capabilities.includes(override)) return override;
  for (const c of candidates) {
    if (device.capabilities.includes(c)) return c;
  }
  // substring fallback (Tuya sometimes suffixes IDs, e.g. onoff.light)
  for (const c of candidates) {
    const hit = device.capabilities.find(cap => cap === c || cap.startsWith(c + '.'));
    if (hit) return hit;
  }
  return null;
}

async function findDevice() {
  const devices = await Homey.devices.getDevices();
  const list = Object.values(devices);
  let device = list.find(d => d.name === DEVICE_NAME);
  if (!device) {
    // fall back to a case-insensitive partial match on "breville"
    device = list.find(d => /breville|airrounder|air.?round/i.test(d.name));
  }
  if (!device) {
    throw new Error(
      `Device "${DEVICE_NAME}" not found. Devices seen: ` +
      list.map(d => `"${d.name}"`).join(', ')
    );
  }
  return device;
}

/** Resolve every capability ID we care about for this device. */
function resolveCaps(device) {
  return {
    onoff:        pick(device, CAPS.onoff,        ['onoff']),
    mode:         pick(device, CAPS.mode,         ['thermostat_mode', 'fan_mode', 'breville_mode', 'mode']),
    target_temp:  pick(device, CAPS.target_temp,  ['target_temperature']),
    measure_temp: pick(device, CAPS.measure_temp, ['measure_temperature']),
    fan_speed:    pick(device, CAPS.fan_speed,    ['legacy_fan_speed', 'fan_speed', 'dim']),
    timer:        pick(device, CAPS.timer,        ['breville_timer', 'timer', 'dim.timer']),
    light:        pick(device, CAPS.light,        ['onoff.light', 'breville_light', 'light_onoff']),
  };
}

async function set(device, capId, value, label) {
  if (!capId) {
    console.log(`  ⚠︎  no capability found for "${label}" — skipped`);
    return false;
  }
  await device.setCapabilityValue(capId, value);
  console.log(`  ✓  ${label}: set ${capId} = ${JSON.stringify(value)}`);
  return true;
}

function currentValue(device, capId) {
  if (!capId || !device.capabilitiesObj) return undefined;
  const obj = device.capabilitiesObj[capId];
  return obj ? obj.value : undefined;
}

// ----------------------------------------------------------------------------
// Actions
// ----------------------------------------------------------------------------

async function run(action, value) {
  const device = await findDevice();
  const caps = resolveCaps(device);

  if (action === 'discover' || action === 'status') {
    console.log(`Device found: "${device.name}"  (id: ${device.id})`);
    console.log(`Driver: ${device.driverUri || device.driverId || '?'}`);
    console.log('---- Capabilities ----');
    for (const capId of device.capabilities) {
      const val = currentValue(device, capId);
      const def = device.capabilitiesObj ? device.capabilitiesObj[capId] : null;
      const enumHint = def && def.values ? `  options=[${def.values.map(v => v.id).join(', ')}]` : '';
      console.log(`  ${capId} = ${JSON.stringify(val)}${enumHint}`);
    }
    console.log('---- Resolved mapping ----');
    console.log(JSON.stringify(caps, null, 2));
    return true;
  }

  switch (action) {
    case 'on':
      return set(device, caps.onoff, true, 'power on');

    case 'off':
      return set(device, caps.onoff, false, 'power off');

    case 'heat': {
      await set(device, caps.onoff, true, 'power on');
      await set(device, caps.mode, MODE_VALUES.heat, 'mode heat');
      if (value != null) {
        const t = clamp(Number(value), TEMP_MIN, TEMP_MAX);
        await set(device, caps.target_temp, t, 'target temperature');
      }
      return true;
    }

    case 'cool': {
      await set(device, caps.onoff, true, 'power on');
      await set(device, caps.mode, MODE_VALUES.cool, 'mode cool');
      if (value != null) {
        const t = clamp(Number(value), TEMP_MIN, TEMP_MAX);
        await set(device, caps.target_temp, t, 'target temperature');
      }
      return true;
    }

    case 'fan': {
      await set(device, caps.onoff, true, 'power on');
      await set(device, caps.mode, MODE_VALUES.fan, 'mode fan-only');
      return true;
    }

    case 'fan_speed': {
      // Homey fan/dim capabilities are usually 0..1. If the unit uses discrete
      // steps 1..N, set FAN_STEPS below and pass a step number.
      const FAN_STEPS = 4;
      let v = Number(value);
      if (v > 1) v = clamp(v, 1, FAN_STEPS) / FAN_STEPS; // convert step -> 0..1
      else v = clamp(v, 0, 1);
      return set(device, caps.fan_speed, v, 'fan speed');
    }

    case 'timer': {
      // hours (or whatever unit the Tuya timer capability expects)
      return set(device, caps.timer, Number(value), 'sleep timer');
    }

    case 'light': {
      const on = value === true || value === 'true' || value === 1;
      return set(device, caps.light, on, 'light ring');
    }

    default:
      throw new Error(`Unknown action "${action}". Valid: discover, on, off, heat, cool, fan, fan_speed, timer, light, status.`);
  }
}

// ----------------------------------------------------------------------------
// Entry point — supports Flow argument (JSON) or the ACTION/ARG constants
// ----------------------------------------------------------------------------

let action = ACTION;
let value = ARG;

if (typeof args !== 'undefined' && args.length > 0 && args[0]) {
  try {
    const parsed = JSON.parse(args[0]);
    if (parsed && typeof parsed === 'object') {
      action = parsed.action || action;
      value  = ('value' in parsed) ? parsed.value : value;
    } else if (typeof parsed === 'string') {
      action = parsed;
    }
  } catch (e) {
    // Not JSON — treat the raw argument as the action name.
    action = args[0];
  }
}

console.log(`▶ Breville AirRounder — action="${action}"${value != null ? `, value=${JSON.stringify(value)}` : ''}`);
return await run(action, value);
