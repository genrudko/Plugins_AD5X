# Plugins AD5X - optional Spoolman interoperability helpers

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional


def _positive_int(value: Any) -> Optional[int]:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


def _non_negative_float(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        return None
    return float(value)


def _non_negative_int(value: Any) -> Optional[int]:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        return None
    return int(value)


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _hex_color(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    value = value.strip().upper().lstrip("#")
    if len(value) not in (6, 8):
        return None
    try:
        int(value, 16)
    except ValueError:
        return None
    # Plugins AD5X canonical appearance is RGB. Ignore Spoolman's optional alpha.
    return f"#{value[:6]}"


def _dedupe(values: Iterable[Any]) -> List[str]:
    result: List[str] = []
    for value in values:
        color = _hex_color(value)
        if color and color not in result:
            result.append(color)
    return result


def _appearance_from_filament(filament: Dict[str, Any]) -> Dict[str, Any]:
    multi = filament.get("multi_color_hexes")
    if isinstance(multi, str):
        colors = _dedupe(part for part in multi.split(","))
    else:
        colors = []
    single = _hex_color(filament.get("color_hex"))
    if not colors and single:
        colors = [single]

    if len(colors) <= 1:
        mode = "solid"
    elif len(colors) == 2:
        mode = "dual"
    elif len(colors) == 3:
        mode = "tricolor"
    else:
        mode = "special"
    return {
        "color_mode": mode,
        "colors": colors,
        # Spoolman has no canonical equivalent for Plugins AD5X finish.
        "finish": "standard",
    }


def normalize_spoolman_spool(payload: Any) -> Dict[str, Any]:
    """Normalize one Spoolman v1 Spool response into the Plugins AD5X model.

    This intentionally keeps Spoolman spool and filament identifiers distinct.
    It also does not manufacture Orca preset identity from either identifier.
    """

    item = payload if isinstance(payload, dict) else {}
    filament = item.get("filament")
    filament = filament if isinstance(filament, dict) else {}
    vendor = filament.get("vendor")
    vendor = vendor if isinstance(vendor, dict) else {}

    spool_id = _positive_int(item.get("id"))
    filament_id = _positive_int(filament.get("id"))
    remaining_g = _non_negative_float(item.get("remaining_weight"))
    remaining_length_mm = _non_negative_float(item.get("remaining_length"))
    initial_g = _non_negative_float(item.get("initial_weight"))
    used_g = _non_negative_float(item.get("used_weight"))
    used_length_mm = _non_negative_float(item.get("used_length"))

    spool = {
        "source": "spoolman",
        "brand": _text(vendor.get("name")),
        "series": "",
        "name": _text(filament.get("name")),
        "material": _text(filament.get("material")),
        "variant": "",
        # Legacy alias remains the concrete spool entity ID.
        "spoolman_id": spool_id,
        "spoolman_spool_id": spool_id,
        "spoolman_filament_id": filament_id,
        "remaining_g": remaining_g,
        "remaining_length_mm": remaining_length_mm,
        "initial_g": initial_g,
        "used_g": used_g,
        "used_length_mm": used_length_mm,
        "location": _text(item.get("location")),
        "archived": bool(item.get("archived", False)),
        "nozzle_temp": _non_negative_int(filament.get("settings_extruder_temp")),
        "bed_temp": _non_negative_int(filament.get("settings_bed_temp")),
        # These are separate identity domains and stay unknown unless explicitly
        # provided by a future verified Orca integration.
        "orca_material": "",
        "orca_filament_id": "",
        "orca_setting_id": "",
    }

    return {
        "spoolman_spool_id": spool_id,
        "spoolman_filament_id": filament_id,
        "spool": spool,
        "appearance": _appearance_from_filament(filament),
        "inventory": {
            "remaining_g": remaining_g,
            "remaining_length_mm": remaining_length_mm,
            "initial_g": initial_g,
            "used_g": used_g,
            "used_length_mm": used_length_mm,
            "location": _text(item.get("location")),
            "archived": bool(item.get("archived", False)),
        },
        "raw_identity": {
            "spool_id": spool_id,
            "filament_id": filament_id,
            "vendor_id": _positive_int(vendor.get("id")),
        },
    }


def merge_spoolman_binding(
    existing: Optional[Dict[str, Any]],
    normalized_spoolman: Dict[str, Any],
) -> Dict[str, Any]:
    """Merge a bound Spoolman spool into a slot without destroying richer data."""

    existing = existing if isinstance(existing, dict) else {}
    existing_spool = existing.get("spool")
    existing_spool = dict(existing_spool) if isinstance(existing_spool, dict) else {}
    existing_appearance = existing.get("appearance")
    existing_appearance = (
        dict(existing_appearance) if isinstance(existing_appearance, dict) else {}
    )

    imported_spool = normalized_spoolman.get("spool")
    imported_spool = imported_spool if isinstance(imported_spool, dict) else {}
    merged_spool = dict(existing_spool)

    # Spoolman is authoritative for the external spool identity and its current
    # inventory values. Exact material/vendor/name replace copied local values
    # when Spoolman actually provides them.
    for key in (
        "brand",
        "name",
        "material",
        "spoolman_id",
        "spoolman_spool_id",
        "spoolman_filament_id",
        "remaining_g",
        "remaining_length_mm",
        "initial_g",
        "used_g",
        "used_length_mm",
        "location",
        "archived",
        "nozzle_temp",
        "bed_temp",
    ):
        value = imported_spool.get(key)
        if value not in (None, "") or key in {
            "remaining_g",
            "remaining_length_mm",
            "initial_g",
            "used_g",
            "used_length_mm",
            "archived",
            "nozzle_temp",
            "bed_temp",
        }:
            merged_spool[key] = value

    # Preserve local rich-only values unless Spoolman has a verified equivalent.
    for key in ("series", "variant", "orca_material", "orca_filament_id", "orca_setting_id"):
        if key not in merged_spool:
            merged_spool[key] = existing_spool.get(key, "")
    merged_spool["source"] = "spoolman"

    imported_appearance = normalized_spoolman.get("appearance")
    imported_appearance = (
        imported_appearance if isinstance(imported_appearance, dict) else {}
    )
    colors = imported_appearance.get("colors")
    colors = list(colors) if isinstance(colors, list) else []
    merged_appearance = dict(existing_appearance)
    if colors:
        merged_appearance["colors"] = colors
        merged_appearance["color_mode"] = imported_appearance.get("color_mode", "solid")
    # Spoolman cannot represent the Plugins AD5X finish taxonomy, so preserve it.
    if not merged_appearance.get("finish"):
        merged_appearance["finish"] = "standard"

    return {
        "spool": merged_spool,
        "appearance": merged_appearance,
    }


def unbind_spoolman_record(
    existing: Optional[Dict[str, Any]],
    keep_metadata: bool = True,
) -> Optional[Dict[str, Any]]:
    """Detach external Spoolman identity without deleting the Spoolman entity."""

    if not keep_metadata:
        return None
    existing = existing if isinstance(existing, dict) else {}
    spool = existing.get("spool")
    spool = dict(spool) if isinstance(spool, dict) else {}
    appearance = existing.get("appearance")
    appearance = dict(appearance) if isinstance(appearance, dict) else {}

    for key in (
        "spoolman_id",
        "spoolman_spool_id",
        "spoolman_filament_id",
        # Dynamic inventory becomes stale after unbinding.
        "remaining_g",
        "remaining_length_mm",
        "initial_g",
        "used_g",
        "used_length_mm",
        "location",
        "archived",
    ):
        spool.pop(key, None)

    if spool.get("source") == "spoolman":
        spool["source"] = "manual"

    useful = any(
        spool.get(key)
        for key in (
            "brand",
            "series",
            "name",
            "material",
            "variant",
            "orca_material",
            "orca_filament_id",
            "orca_setting_id",
        )
    ) or bool(appearance.get("colors")) or appearance.get("finish") not in (
        None,
        "",
        "standard",
    )
    if not useful:
        return None
    return {"spool": spool, "appearance": appearance}


def spoolman_binding_id(slot: Dict[str, Any]) -> Optional[int]:
    spool = slot.get("spool") if isinstance(slot, dict) else None
    spool = spool if isinstance(spool, dict) else {}
    explicit = _positive_int(spool.get("spoolman_spool_id"))
    if explicit is not None:
        return explicit
    return _positive_int(spool.get("spoolman_id"))


def summarize_bindings(slots: Any) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    for slot in slots if isinstance(slots, list) else []:
        if not isinstance(slot, dict):
            continue
        number = slot.get("slot")
        if isinstance(number, bool) or not isinstance(number, int) or number < 1:
            continue
        spool = slot.get("spool")
        spool = spool if isinstance(spool, dict) else {}
        spool_id = spoolman_binding_id(slot)
        filament_id = _positive_int(spool.get("spoolman_filament_id"))
        result.append(
            {
                "slot": number,
                "present": bool(slot.get("present", False)),
                "active": bool(slot.get("active", False)),
                "spool_id": spool_id,
                "filament_id": filament_id,
            }
        )
    return result


def fallback_filter_library(items: Any, query: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Compatibility fallback when an older Spoolman lacks /v1/search."""

    needle = query.strip().casefold()
    if not needle:
        candidates = items if isinstance(items, list) else []
    else:
        candidates = []
        for raw in items if isinstance(items, list) else []:
            if not isinstance(raw, dict):
                continue
            normalized = normalize_spoolman_spool(raw)
            spool = normalized["spool"]
            haystack = " ".join(
                str(value)
                for value in (
                    raw.get("id"),
                    spool.get("brand"),
                    spool.get("name"),
                    spool.get("material"),
                    spool.get("location"),
                )
                if value not in (None, "")
            ).casefold()
            if needle in haystack:
                candidates.append(raw)
    result = []
    for raw in candidates[: max(1, min(int(limit), 100))]:
        result.append(normalize_spoolman_spool(raw))
    return result
