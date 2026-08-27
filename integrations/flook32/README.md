# FLOOK32 integration for AD5X

Upstream: `schreider/flook32`; exact imported revision is recorded in `UPSTREAM_COMMIT`.

The ESP32 remains the sole physical heater controller. The Klipper extension adds a `[flook32 chamber]` object to Klipper's normal `heaters` registry, so Fluidd can use its stock target-temperature UI and `SET_HEATER_TEMPERATURE` without a fake MCU/PWM heater.

Runtime files live in persistent Z-Mod `mod_data`. The only file inside the Klipper checkout is an ignored symlink, repaired by `ensure.sh`, so normal Z-Mod/Klipper updates stay clean.

The firmware fix is deliberately small: `firmware/apply_moonraker_status_fix.py` changes only the Moonraker/auto-shutdown gate and preserves upstream CRLF byte-for-byte everywhere else. It fails closed if the expected upstream anchors change.


## Installation / update safety

Run `integrations/flook32/install.sh` from any checkout/archive of this branch.
The source checkout may be temporary; runtime files are installed into persistent
`/opt/config/mod_data/plugins/flook32`. The installer backs up the currently
working FLOOK32 files, preserves an existing `flook32.cfg` unchanged, installs
the Python adapter/ensure script, and registers an idempotent `power_on.sh` hook.
The boot hook uses `ensure.sh --boot`, so it never waits for a network `pip`
install during printer startup.

Normal Z-Mod/Klipper updates remain clean: `flook32.py` inside the Klipper
checkout is an ignored symlink. If an update removes that symlink,
`power_on.sh` repairs it from persistent `mod_data`. A full destructive Klipper
re-clone can still make the first Klipper start miss the module because Z-Mod's
user `power_on.sh` hook runs later; the hook repairs the runtime for the next
Klipper restart without patching Z-Mod-owned startup files.

The AD5X native heater proxy defaults to a 65C maximum. Existing upstream config
needs no migration; optional `native_heater`, `native_heater_name`,
`native_heater_max_temp`, and `native_heater_wait_delta` keys may be added to the
`[temperature_sensor chamber]` section if customization is required.
