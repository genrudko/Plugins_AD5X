from __future__ import annotations

import argparse
import base64
import glob
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from typing import Any

GUARD = "_AD5X_Z_SAVED_CHECK_POLICY"
CC = "CC_APPLY_PROFILE"
ALLOWED = {
    (): "empty",
    (CC,): "cc",
    (GUARD,): "patched_empty",
    (CC, GUARD): "patched_cc",
}
POLICY_ID = "zcal-saved-check-v1-20260817"
POLICY_MAX_AUTO = 0.120000


class ProductizationError(RuntimeError):
    pass


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _atomic_write(path: Path, data: bytes, *, mode_from: Path | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        if mode_from and mode_from.exists():
            shutil.copymode(mode_from, tmp)
        elif path.exists():
            shutil.copymode(path, tmp)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ProductizationError(f"non-UTF-8 config: {path}") from exc


def _section_ranges(lines: list[str], section_name: str) -> list[tuple[int, int]]:
    wanted = section_name.strip().lower()
    out: list[tuple[int, int]] = []
    for i, line in enumerate(lines):
        if line.strip().lower() != wanted:
            continue
        end = len(lines)
        for j in range(i + 1, len(lines)):
            if lines[j].lstrip().startswith("["):
                end = j
                break
        out.append((i, end))
    return out


def _hook_range_and_commands(data: bytes) -> tuple[tuple[int, int], list[str], list[str]]:
    text = data.decode("utf-8")
    lines = text.splitlines(keepends=True)
    ranges = _section_ranges(lines, "[gcode_macro _user_start_print]")
    if len(ranges) != 1:
        raise ProductizationError(
            f"expected exactly one _USER_START_PRINT in owner file, found {len(ranges)}"
        )
    start, end = ranges[0]
    gcode_idx = None
    for i in range(start + 1, end):
        if lines[i].strip().lower() == "gcode:":
            gcode_idx = i
            break
    if gcode_idx is None:
        raise ProductizationError("_USER_START_PRINT has no gcode: field")
    commands: list[str] = []
    command_lines: list[str] = []
    for i in range(gcode_idx + 1, end):
        raw = lines[i]
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if raw and not raw[0].isspace() and re.match(r"^[A-Za-z0-9_]+[ \t]*:", stripped):
            break
        commands.append(stripped)
        command_lines.append(raw)
    return (start, end), commands, lines


def hook_commands(path: Path) -> list[str]:
    return _hook_range_and_commands(path.read_bytes())[1]


def _classify(commands: list[str]) -> str:
    guard_count = commands.count(GUARD)
    if guard_count > 1:
        return "duplicate_guard"
    kind = ALLOWED.get(tuple(commands))
    if kind is None:
        raise ProductizationError(f"unexpected _USER_START_PRINT body: {commands!r}")
    return kind


def _include_graph(root: Path) -> list[Path]:
    include_re = re.compile(r"^\s*\[include\s+(.+?)\]\s*$", re.IGNORECASE)
    seen: set[Path] = set()
    order: list[Path] = []

    def walk(path: Path) -> None:
        try:
            real = path.resolve(strict=True)
        except FileNotFoundError:
            return
        if real in seen or not real.is_file():
            return
        seen.add(real)
        order.append(real)
        text = _read_text(real)
        base = real.parent
        for line in text.splitlines():
            m = include_re.match(line.strip())
            if not m:
                continue
            pattern = m.group(1).strip()
            full = Path(pattern) if os.path.isabs(pattern) else base / pattern
            for child in sorted(glob.glob(str(full))):
                walk(Path(child))

    walk(root)
    return order


def physical_definitions(printer_config: Path) -> list[dict[str, Any]]:
    defs: list[dict[str, Any]] = []
    for path in _include_graph(printer_config):
        text = _read_text(path)
        lines = text.splitlines(keepends=True)
        ranges = _section_ranges(lines, "[gcode_macro _user_start_print]")
        for ordinal, (start, end) in enumerate(ranges):
            block = "".join(lines[start:end]).encode("utf-8")
            try:
                _, commands, _ = _hook_range_and_commands(block)
            except ProductizationError:
                commands = ["<unparseable>"]
            defs.append(
                {
                    "path": str(path),
                    "ordinal": ordinal,
                    "commands": commands,
                }
            )
    return defs


def _load_manifest(state_dir: Path) -> dict[str, Any] | None:
    path = state_dir / "manifest.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ProductizationError("invalid productization manifest") from exc
    if data.get("schema") != 1:
        raise ProductizationError("unsupported productization manifest schema")
    return data


def resolve_owner(
    printer_config: Path,
    effective_commands: list[str],
    *,
    manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    kind = _classify(effective_commands)
    defs = physical_definitions(printer_config)
    exact = [d for d in defs if d["commands"] == effective_commands]

    if kind == "duplicate_guard":
        if manifest is None:
            raise ProductizationError("duplicate guard without ownership manifest")
        expected_owner = str(Path(manifest["owner_path"]).resolve())
        exact_owned = [d for d in exact if str(Path(d["path"]).resolve()) == expected_owner]
        if len(exact_owned) != 1:
            raise ProductizationError("duplicate guard owner cannot be proven")
        owner = exact_owned[0]
    elif len(exact) == 1:
        owner = exact[0]
    elif len(exact) == 0:
        if manifest is not None:
            expected_owner = str(Path(manifest["owner_path"]).resolve())
            owned_defs = [
                d for d in defs if str(Path(d["path"]).resolve()) == expected_owner
            ]
            if len(owned_defs) != 1:
                raise ProductizationError(
                    f"winning _USER_START_PRINT owner not found for effective body {effective_commands!r}"
                )
            physical = owned_defs[0]["commands"]
            baseline_kind = manifest.get("baseline_kind")
            accepted_physical = (
                (baseline_kind == "empty" and physical in ([], [GUARD]))
                or (baseline_kind == "cc" and physical in ([CC], [CC, GUARD]))
                or physical.count(GUARD) > 1
            )
            if not accepted_physical:
                raise ProductizationError("manifest owner has foreign physical hook body")
            owner = owned_defs[0]
        else:
            raise ProductizationError(
                f"winning _USER_START_PRINT owner not found for effective body {effective_commands!r}"
            )
    else:
        if manifest is not None:
            expected_owner = str(Path(manifest["owner_path"]).resolve())
            exact_owned = [d for d in exact if str(Path(d["path"]).resolve()) == expected_owner]
            if len(exact_owned) == 1:
                owner = exact_owned[0]
            else:
                raise ProductizationError(
                    f"ambiguous physical _USER_START_PRINT definitions: {len(exact)}"
                )
        else:
            raise ProductizationError(
                f"ambiguous physical _USER_START_PRINT definitions: {len(exact)}"
            )

    return {
        "kind": kind,
        "owner_path": owner["path"],
        "definitions": defs,
    }


def _patch_baseline(data: bytes) -> bytes:
    (_, _), commands, lines = _hook_range_and_commands(data)
    kind = _classify(commands)
    if kind not in {"empty", "cc"}:
        raise ProductizationError(f"baseline hook is not pristine: {commands!r}")

    ranges = _section_ranges(lines, "[gcode_macro _user_start_print]")
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
        lines.insert(idx + 1, indent + GUARD + newline)
    else:
        newline = "\r\n" if any(x.endswith("\r\n") for x in lines) else "\n"
        lines.insert(gcode_idx + 1, "    " + GUARD + newline)
    return "".join(lines).encode("utf-8")


def _compatible_with_expected(current: bytes, expected: bytes, original: bytes) -> str:
    if current == expected:
        return "expected"
    if current == original:
        return "original"
    try:
        _, commands, lines = _hook_range_and_commands(current)
    except ProductizationError:
        return "foreign"
    if commands.count(GUARD) > 1:
        ranges = _section_ranges(lines, "[gcode_macro _user_start_print]")
        start, end = ranges[0]
        filtered = [
            line for i, line in enumerate(lines)
            if not (start <= i < end and line.strip() == GUARD)
        ]
        if "".join(filtered).encode("utf-8") == original:
            return "duplicate_guard"
    return "foreign"


def _runtime_payload(stdin_text: str) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        outer = json.loads(stdin_text)
        status = outer.get("result", outer).get("status", outer.get("result", outer))
        settings = status["configfile"]["settings"]
        variables = status["save_variables"]["variables"]
    except (json.JSONDecodeError, KeyError, TypeError, AttributeError) as exc:
        raise ProductizationError("invalid Moonraker configfile/save_variables payload") from exc
    key = next(
        (k for k in settings if str(k).lower() == "gcode_macro _user_start_print"),
        None,
    )
    if key is None:
        raise ProductizationError("effective _USER_START_PRINT is missing")
    gcode = str(settings[key].get("gcode", ""))
    commands = [line.strip() for line in gcode.splitlines() if line.strip()]
    return {"commands": commands, "variables": variables}, status


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
                if _patch_baseline(original) != current_bytes:
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


def build_preflight_plan(
    printer_config: Path,
    policy_source: Path,
    policy_dest: Path,
    variables_file: Path,
    state_dir: Path,
    backups_root: Path,
    live_payload: str,
) -> dict[str, Any]:
    runtime, _ = _runtime_payload(live_payload)
    commands = runtime["commands"]
    variables = runtime["variables"]
    manifest = _load_manifest(state_dir)
    resolved = resolve_owner(printer_config, commands, manifest=manifest)
    owner = Path(resolved["owner_path"]).resolve()
    current = owner.read_bytes()
    policy_bytes = policy_source.read_bytes()
    if not policy_bytes:
        raise ProductizationError("empty canonical RC policy")

    plan: dict[str, Any] = {
        "schema": 1,
        "owner_path": str(owner),
        "effective_commands": commands,
        "kind": resolved["kind"],
        "policy_source_sha256": _sha(policy_bytes),
        "policy_dest": str(policy_dest),
        "variables_file": str(variables_file),
        "state_dir": str(state_dir),
        "definitions": resolved["definitions"],
    }

    if manifest is not None:
        if str(Path(manifest["owner_path"]).resolve()) != str(owner):
            raise ProductizationError("manifest owner differs from proven effective owner")
        plan["baseline_source"] = "manifest"
        return plan

    kind = resolved["kind"]
    if kind in {"empty", "cc"}:
        original_hook = current
        plan.update(
            {
                "baseline_source": "current",
                "original_hook_b64": base64.b64encode(original_hook).decode("ascii"),
                "original_mesh_test": {
                    "present": "mesh_test" in variables,
                    "value": variables.get("mesh_test"),
                },
                "original_cc_enabled": {
                    "present": "cc_enabled" in variables,
                    "value": variables.get("cc_enabled"),
                },
                "policy_original_present": policy_dest.is_file(),
                "policy_original_b64": (
                    base64.b64encode(policy_dest.read_bytes()).decode("ascii")
                    if policy_dest.is_file()
                    else ""
                ),
            }
        )
        if policy_dest.exists() and policy_dest.read_bytes() != policy_bytes:
            raise ProductizationError("foreign pre-existing RC policy destination")
        return plan

    if kind in {"patched_empty", "patched_cc"}:
        legacy = _legacy_candidates(backups_root, owner, current)
        if not legacy:
            raise ProductizationError(
                "already-patched unowned hook requires compatible legacy RC backup "
                "with old_mesh_test and old_cc_enabled"
            )
        signatures = {
            (
                c["original_hook_b64"],
                c["mesh_test"],
                c["cc_enabled"],
                c["policy_original_present"],
                c["policy_original_b64"],
            )
            for c in legacy
        }
        if len(signatures) != 1:
            raise ProductizationError("conflicting compatible legacy RC backups")
        c = legacy[0]
        plan.update(
            {
                "baseline_source": "legacy_backup",
                "legacy_backup_dir": c["backup_dir"],
                "original_hook_b64": c["original_hook_b64"],
                "original_mesh_test": {"present": True, "value": c["mesh_test"]},
                "original_cc_enabled": {"present": True, "value": c["cc_enabled"]},
                "policy_original_present": c["policy_original_present"],
                "policy_original_b64": c["policy_original_b64"],
            }
        )
        if policy_dest.exists() and policy_dest.read_bytes() != policy_bytes:
            raise ProductizationError("foreign policy during legacy RC adoption")
        return plan

    raise ProductizationError(f"unsupported preflight state: {kind}")


def _manifest_paths(state_dir: Path) -> tuple[Path, Path, Path]:
    return state_dir / "manifest.json", state_dir / "original_hook", state_dir / "original_policy"


def _write_manifest_from_plan(plan: dict[str, Any], policy_source: Path) -> dict[str, Any]:
    state_dir = Path(plan["state_dir"])
    manifest_path, original_hook_path, original_policy_path = _manifest_paths(state_dir)
    existing = _load_manifest(state_dir)
    if existing is not None:
        return existing

    original_hook = base64.b64decode(plan["original_hook_b64"])
    expected = _patch_baseline(original_hook)
    manifest = {
        "schema": 1,
        "owner_path": plan["owner_path"],
        "original_hook_sha256": _sha(original_hook),
        "expected_patched_hook_sha256": _sha(expected),
        "baseline_kind": _classify(_hook_range_and_commands(original_hook)[1]),
        "original_mesh_test": plan["original_mesh_test"],
        "original_cc_enabled": plan["original_cc_enabled"],
        "policy_dest": plan["policy_dest"],
        "policy_original_present": bool(plan["policy_original_present"]),
        "policy_original_sha256": (
            _sha(base64.b64decode(plan["policy_original_b64"]))
            if plan["policy_original_present"]
            else None
        ),
        "policy_sha256": _sha(policy_source.read_bytes()),
        "baseline_source": plan["baseline_source"],
    }
    state_dir.parent.mkdir(parents=True, exist_ok=True)
    tmp = state_dir.with_name(state_dir.name + f".tmp.{os.getpid()}")
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir()
    (tmp / "original_hook").write_bytes(original_hook)
    if plan["policy_original_present"]:
        (tmp / "original_policy").write_bytes(base64.b64decode(plan["policy_original_b64"]))
    (tmp / "manifest.json").write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(tmp, state_dir)
    return manifest


def _variables_lines(path: Path) -> list[str]:
    if not path.is_file():
        raise ProductizationError(f"variables file missing: {path}")
    return path.read_text(encoding="utf-8").splitlines(keepends=True)


def _set_variable(path: Path, name: str, value: Any | None, present: bool) -> None:
    lines = _variables_lines(path)
    section_start = None
    section_end = len(lines)
    for i, line in enumerate(lines):
        if line.strip().lower() == "[variables]":
            section_start = i
            for j in range(i + 1, len(lines)):
                if lines[j].lstrip().startswith("["):
                    section_end = j
                    break
            break
    if section_start is None:
        raise ProductizationError("variables file has no [Variables] section")
    rx = re.compile(rf"^\s*{re.escape(name)}\s*=", re.IGNORECASE)
    indexes = [i for i in range(section_start + 1, section_end) if rx.match(lines[i])]
    if len(indexes) > 1:
        raise ProductizationError(f"duplicate variable {name}")
    newline = "\r\n" if any(x.endswith("\r\n") for x in lines) else "\n"
    if present:
        rendered = f"{name} = {value}{newline}"
        if indexes:
            lines[indexes[0]] = rendered
        else:
            lines.insert(section_end, rendered)
    elif indexes:
        del lines[indexes[0]]
    _atomic_write(path, "".join(lines).encode("utf-8"), mode_from=path)


def _policy_deploy(policy_source: Path, policy_dest: Path, manifest: dict[str, Any]) -> str:
    source = policy_source.read_bytes()
    new_hash = _sha(source)
    if policy_dest.exists():
        current = policy_dest.read_bytes()
        current_hash = _sha(current)
        allowed = {manifest.get("policy_sha256"), new_hash}
        if current_hash not in allowed:
            raise ProductizationError("foreign RC policy destination")
    _atomic_write(policy_dest, source, mode_from=policy_dest if policy_dest.exists() else None)
    return new_hash


def apply_plan(plan: dict[str, Any], policy_source: Path) -> dict[str, Any]:
    state_dir = Path(plan["state_dir"])
    manifest = _write_manifest_from_plan(plan, policy_source)
    manifest_path, original_hook_path, _ = _manifest_paths(state_dir)
    original = original_hook_path.read_bytes()
    expected = _patch_baseline(original)
    owner = Path(manifest["owner_path"])
    current = owner.read_bytes()
    compat = _compatible_with_expected(current, expected, original)
    if compat == "foreign":
        raise ProductizationError("hook owner changed outside Plugins AD5X ownership")
    if compat in {"original", "duplicate_guard"}:
        _atomic_write(owner, expected, mode_from=owner)

    policy_dest = Path(manifest["policy_dest"])
    manifest["policy_sha256"] = _policy_deploy(policy_source, policy_dest, manifest)
    manifest["expected_patched_hook_sha256"] = _sha(expected)

    variables = Path(plan["variables_file"])
    _set_variable(variables, "mesh_test", 3, True)
    _set_variable(variables, "cc_enabled", 0, True)

    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def uninstall(
    state_dir: Path,
    variables_file: Path,
) -> None:
    manifest = _load_manifest(state_dir)
    if manifest is None:
        return
    manifest_path, original_hook_path, original_policy_path = _manifest_paths(state_dir)
    original = original_hook_path.read_bytes()
    expected = _patch_baseline(original)
    owner = Path(manifest["owner_path"])
    current = owner.read_bytes()
    compat = _compatible_with_expected(current, expected, original)
    if compat == "foreign":
        raise ProductizationError("refusing to overwrite foreign hook during uninstall")

    policy_dest = Path(manifest["policy_dest"])
    if policy_dest.exists():
        current_hash = _sha(policy_dest.read_bytes())
        if current_hash != manifest.get("policy_sha256"):
            raise ProductizationError("refusing to remove foreign RC policy during uninstall")

    if current != original:
        _atomic_write(owner, original, mode_from=owner)

    for key, name in (
        ("original_mesh_test", "mesh_test"),
        ("original_cc_enabled", "cc_enabled"),
    ):
        spec = manifest[key]
        _set_variable(variables_file, name, spec.get("value"), bool(spec.get("present")))

    if manifest.get("policy_original_present"):
        _atomic_write(
            policy_dest,
            original_policy_path.read_bytes(),
            mode_from=policy_dest if policy_dest.exists() else None,
        )
    else:
        policy_dest.unlink(missing_ok=True)

    shutil.rmtree(state_dir)


def _snapshot_one(path: Path, root: Path, name: str) -> None:
    marker = root / f".absent-{name}"
    target = root / name
    if path.exists():
        if path.is_dir():
            shutil.copytree(path, target)
        else:
            shutil.copy2(path, target)
    else:
        marker.write_text("", encoding="ascii")


def _restore_one(path: Path, root: Path, name: str) -> None:
    marker = root / f".absent-{name}"
    target = root / name
    if marker.exists():
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)
        return
    if not target.exists():
        raise ProductizationError(f"transaction snapshot missing {name}")
    if target.is_dir():
        shutil.rmtree(path, ignore_errors=True)
        shutil.copytree(target, path)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, path)


def transaction_snapshot(plan: dict[str, Any], backup: Path) -> None:
    backup.mkdir(parents=True, exist_ok=False)
    _snapshot_one(Path(plan["owner_path"]), backup, "hook-owner")
    _snapshot_one(Path(plan["variables_file"]), backup, "variables.cfg")
    _snapshot_one(Path(plan["policy_dest"]), backup, "policy.cfg")
    _snapshot_one(Path(plan["state_dir"]), backup, "ownership-state")


def transaction_restore(plan: dict[str, Any], backup: Path) -> None:
    _restore_one(Path(plan["owner_path"]), backup, "hook-owner")
    _restore_one(Path(plan["variables_file"]), backup, "variables.cfg")
    _restore_one(Path(plan["policy_dest"]), backup, "policy.cfg")
    _restore_one(Path(plan["state_dir"]), backup, "ownership-state")


def verify_live(live_payload: str, state_dir: Path) -> None:
    manifest = _load_manifest(state_dir)
    if manifest is None:
        raise ProductizationError("productization manifest missing")
    runtime, status = _runtime_payload(live_payload)
    original = (state_dir / "original_hook").read_bytes()
    baseline_kind = _classify(_hook_range_and_commands(original)[1])
    expected_commands = [GUARD] if baseline_kind == "empty" else [CC, GUARD]
    if runtime["commands"] != expected_commands:
        raise ProductizationError(
            f"effective hook mismatch: {runtime['commands']!r} != {expected_commands!r}"
        )
    v = runtime["variables"]
    if int(v.get("mesh_test", -1)) != 3:
        raise ProductizationError("MESH_TEST != 3")
    if int(v.get("cc_enabled", -1)) != 0:
        raise ProductizationError("CC_ENABLED != 0")
    policy = status.get("gcode_macro _AD5X_Z_SAVED_CHECK_POLICY") or {}
    if policy.get("policy_id") != POLICY_ID:
        raise ProductizationError("RC policy identity missing/mismatched")
    if abs(float(policy.get("max_auto_alignment", -1.0)) - POLICY_MAX_AUTO) > 1e-12:
        raise ProductizationError("RC policy Auto-Z limit mismatch")


def _load_plan(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProductizationError(f"invalid plan file: {path}") from exc


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    pre = sub.add_parser("preflight")
    pre.add_argument("--printer-config", required=True, type=Path)
    pre.add_argument("--policy-source", required=True, type=Path)
    pre.add_argument("--policy-dest", required=True, type=Path)
    pre.add_argument("--variables-file", required=True, type=Path)
    pre.add_argument("--state-dir", required=True, type=Path)
    pre.add_argument("--backups-root", required=True, type=Path)

    app = sub.add_parser("apply")
    app.add_argument("--plan", required=True, type=Path)
    app.add_argument("--policy-source", required=True, type=Path)

    uns = sub.add_parser("uninstall")
    uns.add_argument("--state-dir", required=True, type=Path)
    uns.add_argument("--variables-file", required=True, type=Path)

    snap = sub.add_parser("txn-snapshot")
    snap.add_argument("--plan", required=True, type=Path)
    snap.add_argument("--backup", required=True, type=Path)

    restore = sub.add_parser("txn-restore")
    restore.add_argument("--plan", required=True, type=Path)
    restore.add_argument("--backup", required=True, type=Path)

    verify = sub.add_parser("verify-live")
    verify.add_argument("--state-dir", required=True, type=Path)

    args = p.parse_args(argv)
    try:
        if args.cmd == "preflight":
            plan = build_preflight_plan(
                args.printer_config,
                args.policy_source,
                args.policy_dest,
                args.variables_file,
                args.state_dir,
                args.backups_root,
                sys.stdin.read(),
            )
            json.dump(plan, sys.stdout, sort_keys=True)
            sys.stdout.write("\n")
        elif args.cmd == "apply":
            manifest = apply_plan(_load_plan(args.plan), args.policy_source)
            json.dump(manifest, sys.stdout, sort_keys=True)
            sys.stdout.write("\n")
        elif args.cmd == "uninstall":
            uninstall(args.state_dir, args.variables_file)
        elif args.cmd == "txn-snapshot":
            transaction_snapshot(_load_plan(args.plan), args.backup)
        elif args.cmd == "txn-restore":
            transaction_restore(_load_plan(args.plan), args.backup)
        elif args.cmd == "verify-live":
            verify_live(sys.stdin.read(), args.state_dir)
        else:
            raise AssertionError(args.cmd)
    except ProductizationError as exc:
        print(f"ZCAL PRODUCTIZATION ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
