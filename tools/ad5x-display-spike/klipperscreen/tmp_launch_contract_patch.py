from pathlib import Path


def replace_once(text, old, new, label):
    count = text.count(old)
    assert count == 1, f"{label}: expected 1 occurrence, found {count}"
    return text.replace(old, new, 1)


path = Path("moonraker/components/plugins_ad5x_ifs_model.py")
text = path.read_text()
text = replace_once(
    text,
    '            "preview_job": True,\n',
    '            "preview_job": True,\n            "start_job": False,\n',
    "start capability",
)
text = replace_once(
    text,
    '    module["preprint_plan"] = build_preprint_plan(\n        module.get("job_preview"), normalized_slots\n    )\n\n    mapping = metadata.get("tool_mapping")\n',
    '    module["preprint_plan"] = build_preprint_plan(\n        module.get("job_preview"), normalized_slots\n    )\n    module["launch_gate"] = build_job_launch_gate(\n        module.get("job_preview"),\n        module["preprint_plan"],\n        module_state=module_state,\n        print_state=print_state,\n        operation_state=operation_state,\n    )\n\n    mapping = metadata.get("tool_mapping")\n',
    "attach launch gate",
)

marker = "\n\ndef build_preprint_plan(\n"
assert marker in text
helper = r'''
def build_job_preview_token(job_preview: Optional[Dict[str, Any]]) -> str:
    """Return a stable token for the semantic Z-Mod preview inputs/results.

    Physical slot state is intentionally excluded: it is revalidated separately
    immediately before any future mutation. Messages are diagnostic text and do
    not invalidate an otherwise identical preview.
    """
    import hashlib
    import json

    preview = job_preview if isinstance(job_preview, dict) else {}
    if not preview.get("available", False):
        return ""

    requirements = []
    for item in preview.get("requirements") or []:
        if not isinstance(item, dict):
            continue
        tool = item.get("tool")
        if isinstance(tool, bool) or not isinstance(tool, int) or tool < 0:
            continue
        requirements.append({
            "tool": tool,
            "material": (item.get("material") or "").strip().upper()
            if isinstance(item.get("material"), str)
            else "",
            "color": _normalize_hex_color(item.get("color")) or "",
        })
    requirements.sort(key=lambda item: item["tool"])

    assignments = []
    for item in preview.get("assignments") or []:
        if not isinstance(item, dict):
            continue
        tool = item.get("tool")
        slot = item.get("slot")
        if (
            isinstance(tool, int)
            and not isinstance(tool, bool)
            and tool >= 0
            and isinstance(slot, int)
            and not isinstance(slot, bool)
            and slot > 0
        ):
            assignments.append({"tool": tool, "slot": slot})
    assignments.sort(key=lambda item: item["tool"])

    auto = preview.get("auto_assign")
    auto = auto if isinstance(auto, dict) else {}
    canonical = {
        "source": preview.get("source") if isinstance(preview.get("source"), str) else "zmod",
        "filename": preview.get("filename") if isinstance(preview.get("filename"), str) else "",
        "requirements": requirements,
        "assignments": assignments,
        "auto_assign": {
            "flags": int(auto.get("flags") or 0),
            "any_success": bool(auto.get("any_success", False)),
            "material_failure": bool(auto.get("material_failure", False)),
            "color_failure": bool(auto.get("color_failure", False)),
            "weak_color": bool(auto.get("weak_color", False)),
            "duplicate_slot": bool(auto.get("duplicate_slot", False)),
        },
    }
    encoded = json.dumps(
        canonical,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_job_launch_gate(
    job_preview: Optional[Dict[str, Any]],
    preprint_plan: Optional[Dict[str, Any]],
    module_state: str,
    print_state: str,
    operation_state: str,
    expected_preview_token: Optional[str] = None,
) -> Dict[str, Any]:
    """Describe launch eligibility without enabling or performing the write."""
    preview = job_preview if isinstance(job_preview, dict) else {}
    plan = preprint_plan if isinstance(preprint_plan, dict) else {}
    token = build_job_preview_token(preview)
    blockers: List[str] = []
    warnings: List[str] = []

    def block(code: str) -> None:
        if code not in blockers:
            blockers.append(code)

    def warn(code: str) -> None:
        if code not in warnings:
            warnings.append(code)

    if not preview.get("available", False) or not token:
        block("preview_unavailable")
    if expected_preview_token is not None and expected_preview_token != token:
        block("stale_preview")
    if module_state != "ready":
        block("ifs_not_ready")
    if operation_state != "idle":
        block("operation_in_progress")
    if print_state not in SAFE_FILAMENT_OP_PRINT_STATES:
        block("unsafe_print_state")

    plan_status = plan.get("status") if isinstance(plan.get("status"), str) else "unavailable"
    plan_warnings = plan.get("warnings")
    plan_warnings = plan_warnings if isinstance(plan_warnings, list) else []
    warning_only = {"weak_color", "duplicate_slot"}
    blocking_plan = {
        "material_failure",
        "color_failure",
        "unassigned_tool",
        "assigned_slot_missing",
        "assigned_slot_empty",
        "no_requirements",
    }
    for code in plan_warnings:
        if code in warning_only:
            warn(code)
        if code in blocking_plan:
            block(code)

    if plan_status == "warning":
        block("plan_not_strict_ready")
    elif plan_status not in ("ready", "warning"):
        block("plan_not_ready")

    candidate = not blockers
    block("launch_write_not_enabled")
    return {
        "candidate": candidate,
        "write_enabled": False,
        "preview_token": token,
        "strict_policy": True,
        "plan_status": plan_status,
        "blockers": blockers,
        "warnings": warnings,
    }
'''
text = text.replace(marker, "\n\n" + helper + marker, 1)
path.write_text(text)
