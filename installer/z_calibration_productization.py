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

    variables = Path(plan["variables_file"])
    _impl._set_variable(variables, "mesh_test", 3, True)
    _impl._set_variable(variables, "cc_enabled", 0, True)

    manifest_path.write_text(
        _impl.json.dumps(manifest, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


# Patch the legacy implementation's globals.  Its main()/preflight/uninstall
# functions then retain the already accepted transaction/ownership behavior,
# while this wrapper supplies only the namespace-migration delta.
_impl.GUARD = GUARD
_impl.ALLOWED = ALLOWED
_impl._classify = _classify
_impl._patch_baseline = _patch_baseline
_impl._compatible_with_expected = _compatible_with_expected
_impl._legacy_candidates = _legacy_candidates
_impl.apply_plan = apply_plan

# Public functions/classes are delegated to the patched implementation.
build_preflight_plan = _impl.build_preflight_plan
resolve_owner = _impl.resolve_owner
hook_commands = _impl.hook_commands
transaction_snapshot = _impl.transaction_snapshot
transaction_restore = _impl.transaction_restore
uninstall = _impl.uninstall
verify_uninstalled = _impl.verify_uninstalled
finalize_uninstall = _impl.finalize_uninstall
verify_live = _impl.verify_live
main = _impl.main


def __getattr__(name: str) -> Any:
    return getattr(_impl, name)


if __name__ == "__main__":
    raise SystemExit(main())
