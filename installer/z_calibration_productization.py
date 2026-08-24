from __future__ import annotations

"""Parser-safe ADZ namespace migration wrapper for ZCal productization.

The original productizer is preserved byte-for-byte in the sibling legacy
module.  This wrapper changes only the owned _USER_START_PRINT guard namespace
and teaches the transaction logic to migrate an already-owned
_AD5X_Z_SAVED_CHECK_POLICY hook to the parser-safe _ADZ_SAVED_CHECK_POLICY.
"""

import base64
import importlib.util
from pathlib import Path
import sys
import shutil
from typing import Any


LEGACY_PATH = Path(__file__).with_name("z_calibration_productization_legacy.py")
_spec = importlib.util.spec_from_file_location(
    "_ad5x_zcal_productization_legacy", LEGACY_PATH
)
if _spec is None or _spec.loader is None:
    raise RuntimeError(f"cannot load legacy productizer: {LEGACY_PATH}")
_impl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_impl)

GUARD = "_ADZ_SAVED_CHECK_POLICY"
LEGACY_GUARD = "_AD5X_Z_SAVED_CHECK_POLICY"
CC = _impl.CC
ALLOWED = {
    (): "empty",
    (CC,): "cc",
    (GUARD,): "patched_empty",
    (CC, GUARD): "patched_cc",
    (LEGACY_GUARD,): "patched_empty",
    (CC, LEGACY_GUARD): "patched_cc",
}

ProductizationError = _impl.ProductizationError
POLICY_ID = _impl.POLICY_ID
POLICY_MAX_AUTO = _impl.POLICY_MAX_AUTO
PRIME_GATE = "_ADZ_PRIME_GATE"
PRIME_DELEGATE_VARIABLE = "adz_prime_delegate"
MEASUREMENT_POLICY_ID = "adz-metrology-mesh5-median3-final05-median3-bias130-normalized-v4-20260825"
MESH_POLICY_VARIABLE = "adz_mesh_policy"
MESH_PROFILE_VARIABLE = "adz_mesh_profile"
MESH_POINTS_VARIABLE = "adz_mesh_points"
_LEGACY_BUILD_PREFLIGHT = _impl.build_preflight_plan
_LEGACY_UNINSTALL = _impl.uninstall
_LEGACY_VERIFY_LIVE = _impl.verify_live
_LEGACY_VERIFY_UNINSTALLED = _impl.verify_uninstalled
_LEGACY_SET_VARIABLE = _impl._set_variable

def _set_variable(path: Path, name: str, value: Any | None, present: bool) -> None:
    _LEGACY_SET_VARIABLE(path, name, repr(value) if present and isinstance(value, str) else value, present)

def _variable_spec(v: dict[str, Any], name: str, default: Any = None) -> dict[str, Any]:
    return {"present": name in v, "value": v.get(name, default)}

def _validate_prime_delegate(value: Any) -> str:
    d = str(value or "")
    if not d or d == PRIME_GATE or _impl.re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", d) is None:
        raise ProductizationError(f"invalid Z-Mod CLEAR delegate: {d!r}")
    return d

def build_preflight_plan(printer_config: Path, policy_source: Path, policy_dest: Path, variables_file: Path, state_dir: Path, backups_root: Path, live_payload: str) -> dict[str, Any]:
    plan = _LEGACY_BUILD_PREFLIGHT(printer_config, policy_source, policy_dest, variables_file, state_dir, backups_root, live_payload)
    runtime, _ = _impl._runtime_payload(live_payload); v = runtime["variables"]
    manifest = _impl._load_manifest(state_dir)
    if manifest is None or "original_clear" not in manifest:
        clear = _variable_spec(v, "clear", "LINE_PURGE"); clear["value"] = _validate_prime_delegate(clear["value"])
        plan["original_clear"] = clear
        plan["original_disable_priming"] = _variable_spec(v, "disable_priming", 0)
        plan["original_prime_delegate"] = _variable_spec(v, PRIME_DELEGATE_VARIABLE)
    else:
        _validate_prime_delegate(manifest["original_clear"].get("value", "LINE_PURGE"))
    if manifest is None or "original_mesh_policy" not in manifest:
        plan["original_mesh_policy"] = _variable_spec(v, MESH_POLICY_VARIABLE)
        plan["original_mesh_profile"] = _variable_spec(v, MESH_PROFILE_VARIABLE)
        plan["original_mesh_points"] = _variable_spec(v, MESH_POINTS_VARIABLE)
    plan["measurement_policy_id"] = MEASUREMENT_POLICY_ID
    return plan


def _classify(commands: list[str]) -> str:
    guard_count = commands.count(GUARD) + commands.count(LEGACY_GUARD)
    if guard_count > 1:
        return "duplicate_guard"
    kind = ALLOWED.get(tuple(commands))
    if kind is None:
        raise ProductizationError(f"unexpected _USER_START_PRINT body: {commands!r}")
    return kind


def _patch_baseline(data: bytes, *, guard: str = GUARD) -> bytes:
    (_, _), commands, lines = _impl._hook_range_and_commands(data)
    kind = _classify(commands)
    if kind not in {"empty", "cc"}:
        raise ProductizationError(f"baseline hook is not pristine: {commands!r}")

    ranges = _impl._section_ranges(lines, "[gcode_macro _user_start_print]")
    start, end = ranges[0]
    gcode_idx = next(
        i for i in range(start + 1, end) if lines[i].strip().lower() == "gcode:"
    )
    if kind == "cc":
        cc_indexes = [i for i in range(gcode_idx + 1, end) if lines[i].strip() == CC]
        if len(cc_indexes) != 1:
            raise ProductizationError("CC_APPLY_PROFILE count != 1")
        idx = cc_indexes[0]
        indent = lines[idx][: len(lines[idx]) - len(lines[idx].lstrip())]
        newline = "\r\n" if lines[idx].endswith("\r\n") else "\n"
        lines.insert(idx + 1, indent + guard + newline)
    else:
        newline = "\r\n" if any(x.endswith("\r\n") for x in lines) else "\n"
        lines.insert(gcode_idx + 1, "    " + guard + newline)
    return "".join(lines).encode("utf-8")


def _compatible_with_expected(current: bytes, expected: bytes, original: bytes) -> str:
    if current == expected:
        return "expected"
    if current == original:
        return "original"
    legacy_expected = _patch_baseline(original, guard=LEGACY_GUARD)
    if current == legacy_expected:
        return "legacy_guard"
    try:
        _, commands, lines = _impl._hook_range_and_commands(current)
    except ProductizationError:
        return "foreign"
    if commands.count(GUARD) + commands.count(LEGACY_GUARD) > 1:
        ranges = _impl._section_ranges(lines, "[gcode_macro _user_start_print]")
        start, end = ranges[0]
        filtered = [
            line
            for i, line in enumerate(lines)
            if not (
                start <= i < end
                and line.strip() in {GUARD, LEGACY_GUARD}
            )
        ]
        if "".join(filtered).encode("utf-8") == original:
            return "duplicate_guard"
    return "foreign"


def _legacy_candidates(
    backups_root: Path,
    current_owner: Path,
    current_bytes: bytes,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    if not backups_root.is_dir():
        return candidates
    for d in sorted((p for p in backups_root.iterdir() if p.is_dir()), reverse=True):
        old_mesh = d / "old_mesh_test"
        old_cc = d / "old_cc_enabled"
        if not old_mesh.is_file() or not old_cc.is_file():
            continue
        owner_backups = []
        for name in ("user.cfg", "user_start_owner.before"):
            p = d / name
            if p.is_file():
                owner_backups.append(p)
        if not owner_backups:
            continue
        for old_owner in owner_backups:
            original = old_owner.read_bytes()
            try:
                new_expected = _patch_baseline(original)
                legacy_expected = _patch_baseline(original, guard=LEGACY_GUARD)
                if current_bytes not in {new_expected, legacy_expected}:
                    continue
                mesh = int(old_mesh.read_text(encoding="ascii").strip())
                cc = int(old_cc.read_text(encoding="ascii").strip())
            except (ProductizationError, ValueError, OSError):
                continue
            policy_backup = d / "zcal_owner_rc.cfg"
            candidates.append(
                {
                    "backup_dir": str(d),
                    "original_hook_b64": base64.b64encode(original).decode("ascii"),
                    "mesh_test": mesh,
                    "cc_enabled": cc,
                    "policy_original_present": policy_backup.is_file(),
                    "policy_original_b64": (
                        base64.b64encode(policy_backup.read_bytes()).decode("ascii")
                        if policy_backup.is_file()
                        else ""
                    ),
                }
            )
    return candidates


def apply_plan(plan: dict[str, Any], policy_source: Path) -> dict[str, Any]:
    state_dir = Path(plan["state_dir"])
    previous_manifest = _impl._load_manifest(state_dir)
    previous_measurement_policy = (previous_manifest or {}).get("measurement_policy_id")
    manifest = _impl._write_manifest_from_plan(plan, policy_source)
    manifest_path, original_hook_path, _ = _impl._manifest_paths(state_dir)
    original = original_hook_path.read_bytes()
    expected = _patch_baseline(original)
    owner = Path(manifest["owner_path"])
    current = owner.read_bytes()
    compat = _compatible_with_expected(current, expected, original)
    if compat == "foreign":
        raise ProductizationError("hook owner changed outside Plugins AD5X ownership")
    if compat in {"original", "legacy_guard", "duplicate_guard"}:
        _impl._atomic_write(owner, expected, mode_from=owner)

    policy_dest = Path(manifest["policy_dest"])
    manifest["policy_sha256"] = _impl._policy_deploy(
        policy_source, policy_dest, manifest
    )
    manifest["expected_patched_hook_sha256"] = _impl._sha(expected)

    for key in ("original_clear", "original_disable_priming", "original_prime_delegate", "original_mesh_policy", "original_mesh_profile", "original_mesh_points"):
        if key not in manifest:
            if key not in plan:
                raise ProductizationError(f"missing ZCAL ownership field: {key}")
            manifest[key] = plan[key]
    manifest["measurement_policy_id"] = MEASUREMENT_POLICY_ID
    delegate = _validate_prime_delegate(manifest["original_clear"].get("value", "LINE_PURGE"))
    variables = Path(plan["variables_file"])
    _set_variable(variables, "mesh_test", 3, True)
    _set_variable(variables, "cc_enabled", 0, True)
    _set_variable(variables, "clear", PRIME_GATE, True)
    _set_variable(variables, "disable_priming", 0, True)
    _set_variable(variables, PRIME_DELEGATE_VARIABLE, delegate, True)
    if previous_measurement_policy != MEASUREMENT_POLICY_ID:
        _set_variable(variables, MESH_POLICY_VARIABLE, "", True)
        _set_variable(variables, MESH_PROFILE_VARIABLE, "", True)
        _set_variable(variables, MESH_POINTS_VARIABLE, [], True)

    manifest_path.write_text(
        _impl.json.dumps(manifest, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def _restore_extra_variables(manifest: dict[str, Any], variables_file: Path) -> None:
    for key, name in (("original_clear", "clear"), ("original_disable_priming", "disable_priming"), ("original_prime_delegate", PRIME_DELEGATE_VARIABLE), ("original_mesh_policy", MESH_POLICY_VARIABLE), ("original_mesh_profile", MESH_PROFILE_VARIABLE), ("original_mesh_points", MESH_POINTS_VARIABLE)):
        spec = manifest.get(key)
        if spec is not None:
            _set_variable(variables_file, name, spec.get("value"), bool(spec.get("present")))

def uninstall(state_dir: Path, variables_file: Path, *, keep_state: bool = False) -> None:
    manifest = _impl._load_manifest(state_dir)
    if manifest is None: return
    _LEGACY_UNINSTALL(state_dir, variables_file, keep_state=True)
    _restore_extra_variables(manifest, variables_file)
    if not keep_state: shutil.rmtree(state_dir)

def _verify_spec(v: dict[str, Any], spec: dict[str, Any], name: str) -> None:
    present = name in v
    if bool(spec.get("present")) != present: raise ProductizationError(f"{name} presence was not restored")
    if present and v.get(name) != spec.get("value"): raise ProductizationError(f"{name} value was not restored")

def verify_live(live_payload: str, state_dir: Path) -> None:
    _LEGACY_VERIFY_LIVE(live_payload, state_dir)
    manifest = _impl._load_manifest(state_dir)
    if manifest is None or "original_clear" not in manifest: raise ProductizationError("prime-gate ownership missing from manifest")
    runtime, status = _impl._runtime_payload(live_payload); v = runtime["variables"]
    d = _validate_prime_delegate(manifest["original_clear"].get("value", "LINE_PURGE"))
    if v.get("clear") != PRIME_GATE: raise ProductizationError("Z-Mod CLEAR is not routed through ZCAL prime gate")
    if int(v.get("disable_priming", -1)) != 0: raise ProductizationError("Z-Mod line priming disabled; prime gate cannot run")
    if v.get(PRIME_DELEGATE_VARIABLE) != d: raise ProductizationError("ZCAL prime delegate mismatch")
    settings = status.get("configfile", {}).get("settings", {})
    normalized = {str(k).strip().lower(): value for k, value in settings.items()}
    if "gcode_macro _adz_prime_gate" not in normalized: raise ProductizationError("ZCAL prime gate macro is not loaded")
    measurement = status.get("gcode_macro _ADZ_MEASUREMENT_POLICY", {})
    if measurement.get("policy_id") != MEASUREMENT_POLICY_ID: raise ProductizationError("ZCAL measurement policy identity missing/mismatched")
    tare = status.get("gcode_macro LOAD_CELL_TARE", {})
    if "adz_reuse_armed" not in tare: raise ProductizationError("ZCAL LOAD_CELL_TARE policy wrapper is not loaded")
    if abs(float(measurement.get("mesh_probe_speed", -1.0)) - 5.0) > 1e-12: raise ProductizationError("ZCAL mesh probe speed mismatch")
    if int(measurement.get("mesh_probe_samples", -1)) != 3: raise ProductizationError("ZCAL mesh probe sample-count mismatch")
    if str(measurement.get("mesh_probe_result", "")).lower() != "median": raise ProductizationError("ZCAL mesh probe estimator mismatch")
    if abs(float(measurement.get("final_probe_speed", -1.0)) - 0.5) > 1e-12: raise ProductizationError("ZCAL final probe speed mismatch")
    if int(measurement.get("final_probe_samples", -1)) != 3: raise ProductizationError("ZCAL final probe sample-count mismatch")
    if str(measurement.get("final_probe_result", "")).lower() != "median": raise ProductizationError("ZCAL final probe estimator mismatch")
    if abs(float(measurement.get("mesh_final_bias", -99.0)) - 0.130000) > 1e-12: raise ProductizationError("ZCAL mesh/final bias mismatch")
    if "final_probe_armed" not in measurement: raise ProductizationError("ZCAL precision one-shot state missing")
    if "fresh_mesh_built" not in measurement: raise ProductizationError("ZCAL fresh-mesh proof state missing")
    if "fresh_native_check_done" not in measurement: raise ProductizationError("ZCAL native fresh-check proof state missing")
    if "native_bias_pending" not in measurement: raise ProductizationError("ZCAL split-speed normalization state missing")
    saved_check = status.get("gcode_macro _ADZ_SAVED_CHECK_POLICY", {})
    if abs(float(saved_check.get("max_bias_residual", -1.0)) - 0.050000) > 1e-12: raise ProductizationError("ZCAL split-speed residual limit mismatch")
    mesh_adapter = normalized.get("gcode_macro _bed_mesh_calibrate", {})
    if mesh_adapter.get("rename_existing") != "_ADZ_BED_MESH_CALIBRATE_BASE": raise ProductizationError("ZCAL bed-mesh precision adapter is not loaded")
    probe_adapter = normalized.get("gcode_macro probe", {})
    if probe_adapter.get("rename_existing") != "_ADZ_PROBE_BASE": raise ProductizationError("ZCAL final-probe precision adapter is not loaded")
    if manifest.get("measurement_policy_id") != MEASUREMENT_POLICY_ID: raise ProductizationError("ZCAL productization measurement policy provenance mismatch")

def verify_uninstalled(live_payload: str, state_dir: Path) -> None:
    _LEGACY_VERIFY_UNINSTALLED(live_payload, state_dir)
    manifest = _impl._load_manifest(state_dir)
    if manifest is None: raise ProductizationError("productization manifest missing during uninstall verify")
    runtime, _ = _impl._runtime_payload(live_payload); v = runtime["variables"]
    for key, name in (("original_clear", "clear"), ("original_disable_priming", "disable_priming"), ("original_prime_delegate", PRIME_DELEGATE_VARIABLE), ("original_mesh_policy", MESH_POLICY_VARIABLE), ("original_mesh_profile", MESH_PROFILE_VARIABLE), ("original_mesh_points", MESH_POINTS_VARIABLE)):
        spec = manifest.get(key)
        if spec is not None: _verify_spec(v, spec, name)

# Patch the legacy implementation's globals.  Its main()/preflight/uninstall
# functions then retain the already accepted transaction/ownership behavior,
# while this wrapper supplies only the namespace-migration delta.
_impl.GUARD = GUARD
_impl.ALLOWED = ALLOWED
_impl._classify = _classify
_impl._patch_baseline = _patch_baseline
_impl._compatible_with_expected = _compatible_with_expected
_impl._legacy_candidates = _legacy_candidates
_impl._set_variable = _set_variable
_impl.build_preflight_plan = build_preflight_plan
_impl.apply_plan = apply_plan
_impl.uninstall = uninstall
_impl.verify_uninstalled = verify_uninstalled
_impl.verify_live = verify_live

# Public functions/classes are delegated to the patched implementation.
resolve_owner = _impl.resolve_owner
hook_commands = _impl.hook_commands
transaction_snapshot = _impl.transaction_snapshot
transaction_restore = _impl.transaction_restore
finalize_uninstall = _impl.finalize_uninstall
main = _impl.main


def __getattr__(name: str) -> Any:
    return getattr(_impl, name)


if __name__ == "__main__":
    raise SystemExit(main())
