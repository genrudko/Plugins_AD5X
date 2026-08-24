# Plugins AD5X - frontend-neutral IFS Manager model helpers

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

IFS_SCHEMA_VERSION = "1.0"
SLOT_COUNT = 4

SAFE_FILAMENT_OP_PRINT_STATES = {"standby", "complete", "cancelled", "error"}

COLOR_MODES = {"solid", "dual", "tricolor", "gradient", "rainbow", "special"}
FINISHES = {
    "standard",
    "matte",
    "silk",
    "satin",
    "metallic",
    "transparent",
    "translucent",
    "glitter",
    "glow",
    "wood",
    "carbon_fiber",
    "other",
}
METADATA_SOURCES = {"manual", "flashforge", "spoolman", "slicer", "rfid", "unknown"}
ZMOD_COMPAT_MATERIALS = ("PLA", "ABS", "PETG", "TPU", "PLA-CF", "PETG-CF", "SILK")


def _normalize_hex_color(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    color = value.strip().upper()
    if len(color) != 7 or not color.startswith("#"):
        return None
    try:
        int(color[1:], 16)
    except ValueError:
        return None
    return color


def _dedupe_colors(values: Iterable[Any]) -> List[str]:
    colors: List[str] = []
    for value in values:
        color = _normalize_hex_color(value)
        if color and color not in colors:
            colors.append(color)
    return colors


def _infer_color_mode(requested: Any, color_count: int) -> str:
    mode = requested if isinstance(requested, str) else ""
    mode = mode.strip().lower()

    if mode in ("gradient", "rainbow") and color_count >= 2:
        return mode
    if mode == "dual" and color_count >= 2:
        return "dual"
    if mode == "tricolor" and color_count >= 3:
        return "tricolor"
    if mode == "special" and color_count >= 1:
        return "special"
    if mode == "solid" and color_count >= 1:
        return "solid"

    if color_count <= 1:
        return "solid"
    if color_count == 2:
        return "dual"
    if color_count == 3:
        return "tricolor"
    return "special"


def normalize_appearance(
    legacy_color: Any = None,
    appearance: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return a stable appearance object without making color an identifier.

    Existing Flashforge/Z-Mod metadata exposes one RGB value. It is preserved as
    the first color of a solid appearance. Richer sources may provide multiple
    colors plus a finish. Unknown/invalid values fail soft to a neutral object.
    """

    appearance = appearance if isinstance(appearance, dict) else {}

    raw_colors = appearance.get("colors")
    if isinstance(raw_colors, list):
        colors = _dedupe_colors(raw_colors)
    else:
        colors = []

    legacy = _normalize_hex_color(legacy_color)
    if not colors and legacy:
        colors = [legacy]

    finish = appearance.get("finish")
    if not isinstance(finish, str) or finish.strip().lower() not in FINISHES:
        finish = "standard"
    else:
        finish = finish.strip().lower()

    return {
        "color_mode": _infer_color_mode(appearance.get("color_mode"), len(colors)),
        "colors": colors,
        "finish": finish,
    }


def normalize_spool_metadata(metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    metadata = metadata if isinstance(metadata, dict) else {}

    source = metadata.get("source", "unknown")
    if not isinstance(source, str) or source.strip().lower() not in METADATA_SOURCES:
        source = "unknown"
    else:
        source = source.strip().lower()

    def text(name: str) -> str:
        value = metadata.get(name)
        return value.strip() if isinstance(value, str) else ""

    def positive_int(name: str) -> Optional[int]:
        value = metadata.get(name)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            return None
        return value

    def non_negative(name: str) -> Optional[float]:
        value = metadata.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            return None
        return float(value)

    def non_negative_int(name: str) -> Optional[int]:
        value = metadata.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            return None
        return int(value)

    legacy_spoolman_id = positive_int("spoolman_id")
    spoolman_spool_id = positive_int("spoolman_spool_id") or legacy_spoolman_id

    return {
        "source": source,
        "brand": text("brand"),
        "series": text("series"),
        "name": text("name"),
        "material": text("material"),
        "variant": text("variant"),
        # Legacy alias is retained during schema-1.0 migration.
        "spoolman_id": spoolman_spool_id,
        "spoolman_spool_id": spoolman_spool_id,
        "spoolman_filament_id": positive_int("spoolman_filament_id"),
        "remaining_g": non_negative("remaining_g"),
        "remaining_length_mm": non_negative("remaining_length_mm"),
        "initial_g": non_negative("initial_g"),
        "used_g": non_negative("used_g"),
        "used_length_mm": non_negative("used_length_mm"),
        "location": text("location"),
        "archived": bool(metadata.get("archived", False)),
        "nozzle_temp": non_negative_int("nozzle_temp"),
        "bed_temp": non_negative_int("bed_temp"),
        # Orca preset identity is independent of Spoolman entity IDs.
        "orca_material": text("orca_material"),
        "orca_filament_id": text("orca_filament_id"),
        "orca_setting_id": text("orca_setting_id"),
    }


def get_ifs_capabilities() -> Dict[str, Any]:
    """Describe implemented schema/features separately from integrations.

    A field being representable in the schema does not mean that the matching
    external integration (Spoolman, slicer, RFID) is already implemented.
    """

    metadata_schema = {
        "spool_fields": True,
        "multi_color": True,
        "finish": True,
    }
    integrations = {
        "flashforge": True,
        "manual_store": True,
        "spoolman": False,
        "slicer": True,
        "rfid": False,
    }
    return {
        "schema_version": IFS_SCHEMA_VERSION,
        "slot_count": SLOT_COUNT,
        "actions": {
            "select_slot": True,
            "load_slot": True,
            "unload_slot": True,
            "eject_slot": False,
            "recovery": False,
            "manage": True,
            "preview_job": True,
            "prepare_job_launch": True,
            "start_job": False,
        },
        "metadata_schema": metadata_schema,
        "integrations": integrations,
        # Transitional compatibility for early IFS consumers. New frontends
        # must use metadata_schema + integrations so a representable field is
        # never confused with an implemented external integration.
        "metadata": {
            "multi_color": metadata_schema["multi_color"],
            "finish": metadata_schema["finish"],
            "spoolman": integrations["spoolman"],
            "slicer": integrations["slicer"],
            "rfid": integrations["rfid"],
        },
        "mapping": {
            "tool_to_slot": True,
            "preprint_preview": True,
            "draft_preprint_mapping": True,
            "apply_preprint_mapping": False,
            "equivalent_spool_preview": True,
            "endless_spool": False,
        },
        "compatibility": {
            "zmod_projection_preview": True,
            "zmod_projection_write": False,
        },
    }


def global_write_block_reason(
    module_state: str,
    print_state: str,
    operation_state: str,
    provider_mode: str = "display_off",
) -> str:
    if provider_mode == "native_display":
        return "maintenance_suspended"
    if module_state != "ready":
        return "ifs_not_ready"
    if provider_mode not in ("", "display_off"):
        return "provider_mode_unknown"
    if operation_state != "idle":
        return "operation_in_progress"
    if print_state not in SAFE_FILAMENT_OP_PRINT_STATES:
        return "unsafe_print_state"
    return ""


def compute_slot_permissions(
    slot: int,
    present: bool,
    active_slot: int,
    filament_at_toolhead: Optional[bool],
    module_state: str,
    print_state: str,
    operation_state: str,
    provider_mode: str = "display_off",
) -> Dict[str, Any]:
    """Centralize per-slot action permission so frontends do not own safety logic."""

    blocked = global_write_block_reason(
        module_state, print_state, operation_state, provider_mode
    )
    if blocked:
        return {
            "select_slot": False,
            "load_slot": False,
            "unload_slot": False,
            "blocked_reason": blocked,
        }

    if not present:
        return {
            "select_slot": False,
            "load_slot": False,
            "unload_slot": False,
            "blocked_reason": "slot_empty",
        }

    return {
        "select_slot": slot != active_slot,
        "load_slot": not (slot == active_slot and filament_at_toolhead is True),
        "unload_slot": slot == active_slot and filament_at_toolhead is True,
        "blocked_reason": "",
    }


def normalize_slot(
    raw_slot: Dict[str, Any],
    metadata: Optional[Dict[str, Any]],
    active_slot: int,
    filament_at_toolhead: Optional[bool],
    module_state: str,
    print_state: str,
    operation_state: str,
    identity_invalidated: bool = False,
    provider_mode: str = "display_off",
) -> Dict[str, Any]:
    raw_slot = raw_slot if isinstance(raw_slot, dict) else {}
    metadata = metadata if isinstance(metadata, dict) else {}

    slot = raw_slot.get("slot", 0)
    if isinstance(slot, bool) or not isinstance(slot, int):
        slot = 0
    present = bool(raw_slot.get("present", False))
    stall = bool(raw_slot.get("stall", False))

    legacy_material = metadata.get("material")
    legacy_color = metadata.get("color")

    spool_input = metadata.get("spool")
    if not isinstance(spool_input, dict):
        spool_input = {}
    spool_input = dict(spool_input)
    if isinstance(legacy_material, str) and legacy_material and not spool_input.get("material"):
        spool_input["material"] = legacy_material
    if "source" not in spool_input and (legacy_material or legacy_color):
        spool_input["source"] = "flashforge"

    spool = normalize_spool_metadata(spool_input)
    appearance = normalize_appearance(legacy_color, metadata.get("appearance"))
    has_metadata = bool(
        spool["brand"]
        or spool["series"]
        or spool["name"]
        or spool["material"]
        or spool["variant"]
        or spool["spoolman_id"]
        or spool["remaining_g"] is not None
        or appearance["colors"]
        or appearance["finish"] != "standard"
    )

    result = dict(raw_slot)
    result["slot"] = slot
    result["present"] = present
    result["stall"] = stall

    # Physical absence always outranks cached/provider metadata.  Preserve only
    # a stale-availability signal; never expose the old spool as currently
    # installed in an empty lane.
    normalized_legacy_color = _normalize_hex_color(legacy_color)
    if present:
        if isinstance(legacy_material, str) and legacy_material:
            result["material"] = legacy_material
        if normalized_legacy_color:
            result["color"] = normalized_legacy_color
        result["spool"] = spool
        result["appearance"] = appearance
    else:
        result.pop("material", None)
        result.pop("color", None)
        result["spool"] = normalize_spool_metadata({})
        result["appearance"] = normalize_appearance()

    result["metadata_status"] = (
        "assigned" if present and has_metadata else "stale" if has_metadata else "none"
    )
    result["current_identity_status"] = (
        "empty"
        if not present
        else "unassigned"
        if identity_invalidated
        else "assigned"
        if spool.get("spoolman_spool_id")
        else "observed"
        if has_metadata
        else "unknown"
    )
    result["stale_metadata_available"] = bool(not present and has_metadata)
    result["active"] = slot == active_slot and active_slot > 0
    result["permissions"] = compute_slot_permissions(
        slot=slot,
        present=present,
        active_slot=active_slot,
        filament_at_toolhead=filament_at_toolhead,
        module_state=module_state,
        print_state=print_state,
        operation_state=operation_state,
        provider_mode=provider_mode,
    )
    result["compatibility"] = {
        "zmod": build_zmod_compat_projection(
            slot=slot,
            spool=result["spool"],
            appearance=result["appearance"],
            current=metadata.get("zmod_compat") if present else None,
        )
    }
    return result


def build_equivalent_spool_preview(slots, active_slot, provider_metadata, provider_material_types, provider_mode='display_off'):
    """Mirror Z-Mod ANALOG_PRUTOK eligibility without performing its transition."""
    meta = provider_metadata if isinstance(provider_metadata, dict) else {}
    sm = meta.get('slots') if isinstance(meta.get('slots'), dict) else {}
    valid = {x for x in provider_material_types or [] if isinstance(x, str) and x}
    by_slot = {x.get('slot'): x for x in slots or [] if isinstance(x, dict) and isinstance(x.get('slot'), int)}

    def ident(n):
        r = sm.get(n, sm.get(str(n), {}))
        r = r if isinstance(r, dict) else {}
        z = r.get('zmod_compat') if isinstance(r.get('zmod_compat'), dict) else {}
        m = z.get('material') if isinstance(z.get('material'), str) else ''
        c = z.get('color') if isinstance(z.get('color'), str) else ''
        return {'material': m.strip(), 'color': c.strip()}
    source_slot = active_slot if isinstance(active_slot, int) and (not isinstance(active_slot, bool)) and (1 <= active_slot <= SLOT_COUNT) else 0
    base = {'provider': 'zmod', 'provider_command': 'ANALOG_PRUTOK', 'automatic_transition_enabled': False, 'transition_hardware_accepted': False, 'matching': {'material': 'exact_provider_value', 'color': 'exact_provider_value', 'presence_required': True, 'priority': 'ascending_physical_slot'}, 'source_slot': source_slot, 'candidates': [], 'eligible_slots': [], 'next_slot': 0}
    if provider_mode != 'display_off':
        return {**base, 'status': 'suspended', 'reason': 'provider_mode_not_supported'}
    src = by_slot.get(source_slot)
    if not src or not src.get('present', False):
        return {**base, 'status': 'unknown', 'reason': 'source_slot_unavailable'}
    si = ident(source_slot)
    material = si['material']
    color = si['color']
    if not material or not color or (not valid):
        return {**base, 'source': si, 'status': 'unknown', 'reason': 'provider_identity_incomplete'}
    effective = material if material in valid else 'PLA'
    source = {**si, 'effective_material': effective, 'material_normalized_to_pla': effective != material}
    candidates = []
    eligible = []
    for n in sorted(by_slot):
        if n == source_slot:
            continue
        item = by_slot[n]
        ob = ident(n)
        blockers = []
        if not item.get('present', False):
            blockers.append('slot_empty')
        if not ob['material']:
            blockers.append('provider_material_unknown')
        elif ob['material'] != effective:
            blockers.append('material_mismatch')
        if not ob['color']:
            blockers.append('provider_color_unknown')
        elif ob['color'] != color:
            blockers.append('color_mismatch')
        ok = not blockers
        if ok:
            eligible.append(n)
        candidates.append({'slot': n, 'present': bool(item.get('present', False)), 'material': ob['material'], 'color': ob['color'], 'eligible': ok, 'blockers': blockers})
    return {**base, 'source': source, 'candidates': candidates, 'eligible_slots': eligible, 'next_slot': eligible[0] if eligible else 0, 'status': 'available' if eligible else 'no_candidate', 'reason': ''}


def normalize_module(
    raw_module: Dict[str, Any],
    metadata: Optional[Dict[str, Any]],
    print_state: str,
    filament_at_toolhead: Optional[bool],
    operation: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build the additive IFS Manager module while preserving legacy fields."""

    module = dict(raw_module) if isinstance(raw_module, dict) else {}
    metadata = metadata if isinstance(metadata, dict) else {}
    operation = dict(operation) if isinstance(operation, dict) else {
        "state": "idle",
        "action": "",
        "slot": 0,
        "error": "",
    }

    configured_active_slot = metadata.get("active_slot")
    runtime_active_slot = module.get("active_slot", 0)
    if (
        isinstance(configured_active_slot, int)
        and not isinstance(configured_active_slot, bool)
        and 1 <= configured_active_slot <= SLOT_COUNT
    ):
        module["runtime_active_slot"] = runtime_active_slot
        module["active_slot"] = configured_active_slot

    active_slot = module.get("active_slot", 0)
    if isinstance(active_slot, bool) or not isinstance(active_slot, int):
        active_slot = 0

    module_state = module.get("state") if isinstance(module.get("state"), str) else "unknown"
    provider_mode = module.get("provider_mode")
    if not isinstance(provider_mode, str) or not provider_mode:
        provider_mode = "display_off" if module.get("available", False) else "unknown"
    maintenance_suspended = bool(
        module.get("maintenance_suspended", False) or provider_mode == "native_display"
    )
    module["provider_mode"] = provider_mode
    module["maintenance_suspended"] = maintenance_suspended
    module["provider"] = {
        "name": "zmod",
        "mode": provider_mode,
        "supported_modes": ["display_off"],
        "ifs_manager_supported": provider_mode == "display_off",
        "maintenance_suspended": maintenance_suspended,
    }
    operation_state = (
        operation.get("state") if isinstance(operation.get("state"), str) else "idle"
    )

    slot_meta = metadata.get("slots", {})
    if not isinstance(slot_meta, dict):
        slot_meta = {}
    invalidated_slots = metadata.get("identity_invalidated_slots", [])
    invalidated_slots = {
        value for value in invalidated_slots
        if isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= SLOT_COUNT
    } if isinstance(invalidated_slots, list) else set()
    normalized_slots: List[Dict[str, Any]] = []
    for raw_slot in module.get("slots") or []:
        if not isinstance(raw_slot, dict):
            continue
        slot_number = raw_slot.get("slot")
        normalized_slots.append(
            normalize_slot(
                raw_slot=raw_slot,
                metadata=slot_meta.get(slot_number),
                active_slot=active_slot,
                filament_at_toolhead=filament_at_toolhead,
                module_state=module_state,
                print_state=print_state,
                operation_state=operation_state,
                identity_invalidated=slot_number in invalidated_slots,
                provider_mode=provider_mode,
            )
        )
    module["slots"] = normalized_slots
    module["equivalent_spool"] = build_equivalent_spool_preview(
        normalized_slots, active_slot, metadata, module.get("provider_material_types"), provider_mode
    )
    module["preprint_plan"] = build_preprint_plan(
        module.get("job_preview"), normalized_slots
    )
    module["launch_gate"] = build_job_launch_gate(
        module.get("job_preview"),
        module["preprint_plan"],
        module_state=module_state,
        print_state=print_state,
        operation_state=operation_state,
    )

    mapping = metadata.get("tool_mapping")
    if isinstance(mapping, list):
        module["tool_mapping"] = list(mapping)

    module["print_state"] = print_state
    module["filament_at_toolhead"] = filament_at_toolhead
    module["operation"] = operation
    module["capabilities"] = get_ifs_capabilities()
    module["write_blocked_reason"] = global_write_block_reason(
        module_state, print_state, operation_state, provider_mode
    )

    # Compatibility bridge for the already hardware-proven KlipperScreen proof.
    # New frontends should consume capabilities + slot.permissions instead.
    provider_allows_ifs = provider_mode == "display_off"
    module["operations"] = {
        "select_slot": provider_allows_ifs,
        "load_slot": provider_allows_ifs,
        "unload_slot": provider_allows_ifs,
        "manage": True,
        "preview_job": provider_allows_ifs,
    }

    module["diagnostics"] = {
        "silk_mask": module.get("silk_mask", 0),
        "raw_channel": module.get("raw_channel", 0),
        "insert_slot": module.get("insert_slot", 0),
        "need_insert": bool(module.get("need_insert", False)),
        "stall_mask": module.get("stall_mask", 0),
        "runtime_active_slot": module.get("runtime_active_slot", runtime_active_slot),
    }
    return module




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
        "allowed_tool_count": int(preview.get("allowed_tool_count") or 0),
        "resolved_tool_map": [
            int(slot) for slot in (preview.get("resolved_tool_map") or [])
            if isinstance(slot, int) and not isinstance(slot, bool)
        ],
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


def build_job_mapping_draft(
    job_preview: Optional[Dict[str, Any]],
    resolved_tool_map: Any,
    expected_preview_token: Optional[str] = None,
) -> Dict[str, Any]:
    """Validate a complete manual T->slot draft without mutating Z-Mod."""
    import hashlib
    import json

    preview = job_preview if isinstance(job_preview, dict) else {}
    token = build_job_preview_token(preview)
    blockers: List[str] = []
    warnings: List[str] = []

    def block(code: str) -> None:
        if code not in blockers:
            blockers.append(code)

    if not preview.get("available", False) or not token:
        block("preview_unavailable")
    if expected_preview_token is not None and expected_preview_token != token:
        block("stale_preview")

    allowed = preview.get("allowed_tool_count")
    valid_count = (
        isinstance(allowed, int)
        and not isinstance(allowed, bool)
        and allowed > 0
    )
    if not valid_count:
        block("invalid_allowed_tool_count")

    normalized: List[int] = []
    if (
        not isinstance(resolved_tool_map, list)
        or not valid_count
        or len(resolved_tool_map) != allowed
        or any(
            isinstance(slot, bool)
            or not isinstance(slot, int)
            or slot < 1
            or slot > SLOT_COUNT
            for slot in (resolved_tool_map if isinstance(resolved_tool_map, list) else [])
        )
    ):
        block("invalid_resolved_tool_map")
    else:
        normalized = [int(slot) for slot in resolved_tool_map]

    requirements = []
    for item in preview.get("requirements") or []:
        if not isinstance(item, dict):
            continue
        tool = item.get("tool")
        if isinstance(tool, bool) or not isinstance(tool, int) or tool < 0:
            continue
        if valid_count and tool >= allowed:
            block("invalid_requirement_tool")
            continue
        requirements.append(tool)

    assignments = []
    if normalized:
        assignments = [
            {"tool": tool, "slot": normalized[tool]}
            for tool in sorted(set(requirements))
        ]
        used = [item["slot"] for item in assignments]
        if len(used) != len(set(used)):
            warnings.append("manual_duplicate_slot")

    provider_map = preview.get("resolved_tool_map")
    if not isinstance(provider_map, list):
        provider_map = []
    canonical = json.dumps(
        {"preview_token": token, "resolved_tool_map": normalized},
        sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")
    draft_token = hashlib.sha256(canonical).hexdigest() if not blockers and normalized else ""
    return {
        "available": bool(preview.get("available", False) and token),
        "status": "ready" if not blockers else "blocked",
        "mapping_source": "manual",
        "filename": preview.get("filename") if isinstance(preview.get("filename"), str) else "",
        "preview_token": token,
        "draft_token": draft_token,
        "allowed_tool_count": allowed if valid_count else 0,
        "resolved_tool_map": normalized,
        "provider_resolved_tool_map": list(provider_map),
        "assignments": assignments,
        "modified": bool(normalized and normalized != provider_map),
        "blockers": blockers,
        "warnings": warnings,
    }


def build_zmod_print_zcolor_plan(job_preview: Optional[Dict[str, Any]], leveling: Optional[int] = None) -> Dict[str, Any]:
    """Describe the provider-owned PRINT_ZCOLOR invocation without executing it."""
    preview = job_preview if isinstance(job_preview, dict) else {}
    blockers: List[str] = []
    missing: List[str] = []
    filename = preview.get("filename") if isinstance(preview.get("filename"), str) else ""
    allowed = preview.get("allowed_tool_count")
    mapping = preview.get("resolved_tool_map")
    if not preview.get("available", False): blockers.append("preview_unavailable")
    if not filename: blockers.append("missing_filename")
    valid_count = isinstance(allowed, int) and not isinstance(allowed, bool) and allowed > 0
    valid_map = valid_count and isinstance(mapping, list) and len(mapping) == allowed and all(isinstance(x, int) and not isinstance(x, bool) and 1 <= x <= SLOT_COUNT for x in mapping)
    if not valid_map: blockers.append("invalid_resolved_tool_map")
    if leveling is None:
        missing.append("LEVELING")
    elif isinstance(leveling, bool) or not isinstance(leveling, int) or leveling not in (0, 1):
        blockers.append("invalid_leveling")
    params: Dict[str, Any] = {}
    if filename: params["FILENAME"] = filename
    if leveling in (0, 1) and not isinstance(leveling, bool): params["LEVELING"] = leveling
    if valid_count: params["ALLOWED_TOOL_COUNT"] = allowed
    if valid_map:
        for i, slot in enumerate(mapping): params[f"T{i}"] = slot
    return {"provider": "zmod", "command": "PRINT_ZCOLOR", "parameters": params, "missing_parameters": missing, "blockers": blockers, "ready": not blockers and not missing, "execution_enabled": False}


def build_job_launch_gate(
    job_preview: Optional[Dict[str, Any]],
    preprint_plan: Optional[Dict[str, Any]],
    module_state: str,
    print_state: str,
    operation_state: str,
    expected_preview_token: Optional[str] = None,
    provider_leveling: Optional[int] = None,
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

    allowed_tool_count = preview.get("allowed_tool_count")
    resolved_tool_map = preview.get("resolved_tool_map")
    if (
        isinstance(allowed_tool_count, bool)
        or not isinstance(allowed_tool_count, int)
        or allowed_tool_count <= 0
        or not isinstance(resolved_tool_map, list)
        or len(resolved_tool_map) != allowed_tool_count
        or any(
            isinstance(slot, bool) or not isinstance(slot, int) or slot < 1 or slot > SLOT_COUNT
            for slot in (resolved_tool_map or [])
        )
    ):
        block("invalid_resolved_tool_map")
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

    provider_launch_plan = build_zmod_print_zcolor_plan(preview, leveling=provider_leveling)
    if provider_leveling is not None:
        for code in provider_launch_plan["blockers"]:
            block(code)
        if provider_launch_plan["missing_parameters"]:
            block("provider_launch_plan_incomplete")

    candidate = not blockers
    hardware_acceptance = {
        "required": True,
        "accepted": False,
        "reason": "hardware_acceptance_required",
        "exact_sha_required": True,
    }
    block(hardware_acceptance["reason"])
    block("launch_write_not_enabled")
    return {
        "candidate": candidate,
        "write_enabled": False,
        "preview_token": token,
        "strict_policy": True,
        "plan_status": plan_status,
        "blockers": blockers,
        "warnings": warnings,
        "hardware_acceptance": hardware_acceptance,
        "provider_launch_plan": provider_launch_plan,
    }


def build_preprint_plan(
    job_preview: Optional[Dict[str, Any]],
    slots: Optional[List[Dict[str, Any]]],
) -> Dict[str, Any]:
    # Join Z-Mod job requirements/assignments with normalized physical slots.
    # Z-Mod exposes aggregate quality flags, so per-tool match quality is never invented.
    preview = job_preview if isinstance(job_preview, dict) else {}
    source = preview.get("source") if isinstance(preview.get("source"), str) else "zmod"
    filename = preview.get("filename") if isinstance(preview.get("filename"), str) else ""
    error = preview.get("error") if isinstance(preview.get("error"), str) else ""
    auto_assign = preview.get("auto_assign")
    auto_assign = dict(auto_assign) if isinstance(auto_assign, dict) else {}
    messages = [str(item) for item in (preview.get("messages") or [])][-32:]
    if not preview.get("available", False):
        return {
            "available": False,
            "source": source or "zmod",
            "filename": filename,
            "status": "unavailable",
            "rows": [],
            "warnings": [],
            "summary": {"required_tools": 0, "assigned_tools": 0, "ready_tools": 0},
            "auto_assign": auto_assign,
            "messages": messages,
            "error": error or "not_scanned",
        }

    normalized_slots = [item for item in (slots or []) if isinstance(item, dict)]
    slot_map = {
        item.get("slot"): item
        for item in normalized_slots
        if isinstance(item.get("slot"), int) and not isinstance(item.get("slot"), bool)
    }

    assignments = {}
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
            assignments[tool] = slot

    requirements = []
    for item in preview.get("requirements") or []:
        if not isinstance(item, dict):
            continue
        tool = item.get("tool")
        if isinstance(tool, bool) or not isinstance(tool, int) or tool < 0:
            continue
        color = _normalize_hex_color(item.get("color")) or ""
        material = item.get("material")
        material = material.strip().upper() if isinstance(material, str) else ""
        requirements.append({"tool": tool, "color": color, "material": material})
    requirements.sort(key=lambda item: item["tool"])

    warnings: List[str] = []
    def warn(code: str) -> None:
        if code not in warnings:
            warnings.append(code)

    if auto_assign.get("material_failure"):
        warn("material_failure")
    if auto_assign.get("color_failure"):
        warn("color_failure")
    if auto_assign.get("weak_color"):
        warn("weak_color")
    if auto_assign.get("duplicate_slot"):
        warn("duplicate_slot")

    rows = []
    assigned_count = 0
    ready_count = 0
    for requirement in requirements:
        tool = requirement["tool"]
        slot_number = assignments.get(tool)
        assignment = None
        state = "unassigned"
        if slot_number is None:
            warn("unassigned_tool")
        else:
            assigned_count += 1
            slot_data = slot_map.get(slot_number)
            if slot_data is None:
                state = "slot_missing"
                warn("assigned_slot_missing")
                assignment = {
                    "slot": slot_number,
                    "present": False,
                    "metadata_status": "none",
                    "spool": {},
                    "appearance": {},
                }
            else:
                present = bool(slot_data.get("present", False))
                state = "ready" if present else "slot_empty"
                if present:
                    ready_count += 1
                else:
                    warn("assigned_slot_empty")
                spool = slot_data.get("spool")
                appearance = slot_data.get("appearance")
                assignment = {
                    "slot": slot_number,
                    "present": present,
                    "metadata_status": slot_data.get("metadata_status") or "none",
                    "spool": dict(spool) if isinstance(spool, dict) else {},
                    "appearance": dict(appearance) if isinstance(appearance, dict) else {},
                }
        rows.append({
            "tool": tool,
            "requirement": {
                "material": requirement["material"],
                "color": requirement["color"],
            },
            "assignment": assignment,
            "state": state,
        })

    if not requirements:
        warn("no_requirements")

    blocking_warnings = {
        "material_failure",
        "color_failure",
        "unassigned_tool",
        "assigned_slot_missing",
        "assigned_slot_empty",
        "no_requirements",
    }
    if any(code in blocking_warnings for code in warnings):
        status = "blocked"
    elif warnings:
        status = "warning"
    else:
        status = "ready"

    return {
        "available": True,
        "source": source or "zmod",
        "filename": filename,
        "status": status,
        "rows": rows,
        "warnings": warnings,
        "summary": {
            "required_tools": len(requirements),
            "assigned_tools": assigned_count,
            "ready_tools": ready_count,
        },
        "auto_assign": auto_assign,
        "messages": messages,
        "error": error,
    }

def build_zmod_compat_projection(
    slot: int,
    spool: Optional[Dict[str, Any]],
    appearance: Optional[Dict[str, Any]],
    current: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a read-only lossy projection into Z-Mod's TYPE + primary RGB model.

    This function deliberately does not emit G-code or infer rich finish semantics.
    In particular PLA+Silk stays TYPE=PLA unless the rich material is explicitly SILK.
    """

    spool = normalize_spool_metadata(spool)
    appearance = normalize_appearance(None, appearance)
    current = current if isinstance(current, dict) else {}

    material = spool.get("material", "").strip().upper()
    desired_material = material if material in ZMOD_COMPAT_MATERIALS else ""
    colors = appearance.get("colors") if isinstance(appearance.get("colors"), list) else []
    primary = _normalize_hex_color(colors[0]) if colors else None
    desired_color = primary or ""

    current_material = current.get("material")
    if not isinstance(current_material, str):
        current_material = ""
    current_material = current_material.strip().upper()
    current_color = _normalize_hex_color(current.get("color")) or ""

    blockers = []
    if not material:
        blockers.append("missing_material")
    elif not desired_material:
        blockers.append("unsupported_material")
    if not desired_color:
        blockers.append("missing_primary_color")

    omitted = []
    for key in ("brand", "series", "name", "variant"):
        if spool.get(key):
            omitted.append(f"spool.{key}")
    if spool.get("spoolman_id") is not None:
        omitted.append("spool.spoolman_id")
    if spool.get("remaining_g") is not None:
        omitted.append("spool.remaining_g")
    if len(colors) > 1:
        omitted.append("appearance.colors[1:]")
    if appearance.get("finish") not in (None, "", "standard"):
        omitted.append("appearance.finish")
    if appearance.get("color_mode") not in (None, "", "solid"):
        omitted.append("appearance.color_mode")

    write_ready = not blockers
    if not write_ready:
        sync_state = "unsupported"
    elif not current_material and not current_color:
        sync_state = "unknown"
    elif current_material == desired_material and current_color == desired_color:
        sync_state = "in_sync"
    else:
        sync_state = "diverged"

    return {
        "slot": int(slot) if isinstance(slot, int) and not isinstance(slot, bool) else 0,
        "write_ready": write_ready,
        "sync_state": sync_state,
        "desired": {
            "material": desired_material,
            "color": desired_color,
        },
        "current": {
            "material": current_material,
            "color": current_color,
        },
        "lossy": bool(omitted),
        "omitted_fields": omitted,
        "write_blockers": blockers,
    }
