# Plugins AD5X - frontend-neutral IFS interoperability projections.

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Iterable, List, Optional

ARCHITECTURE_VERSION = "2.0"
UI_EXPERTISE_LEVELS = ("auto", "hybrid", "expert")
CANONICAL_EXPERTISE_LEVEL = "expert"
ORCA_LANE_NAMESPACE = "lane_data"
IFS_SLOT_COUNT = 4

ORCA_SAFE_WIRE_MATERIALS = {"PLA", "PETG", "ABS", "ASA", "TPU"}
ORCA_OWNED_FIELDS = (
    "lane", "material", "color", "bed_temp", "nozzle_temp",
    "vendor", "vendor_name", "name", "spool_name", "spool_id",
    "filament_id", "orca_setting_id", "helix_material",
)


def get_architecture_profile() -> Dict[str, Any]:
    return {
        "architecture_version": ARCHITECTURE_VERSION,
        "ui": {
            "expertise_levels": list(UI_EXPERTISE_LEVELS),
            "canonical_expertise": CANONICAL_EXPERTISE_LEVEL,
            "progressive_disclosure": True,
        },
        "topology": {
            "kind": "selector_single_extruder",
            "ifs_slot_count": IFS_SLOT_COUNT,
            "external_source": {
                "id": "external:bypass",
                "kind": "manual_bypass",
                "modeled": True,
                "runtime_supported": False,
                "control_supported": False,
            },
        },
        "interoperability": {
            "orca_lane_data": {
                "namespace": ORCA_LANE_NAMESPACE,
                "direction": "printer_to_orca",
                "requires_moonraker_agent": True,
                "target_version": "2.4.2",
            }
        },
    }


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _positive_int(value: Any) -> Optional[int]:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


def _temperature(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    if value <= 0 or value > 500:
        return None
    return int(value) if value.is_integer() else value


def _primary_color(appearance: Dict[str, Any]) -> Optional[str]:
    colors = appearance.get("colors")
    if not isinstance(colors, list) or not colors or not isinstance(colors[0], str):
        return None
    color = colors[0].strip().upper()
    if len(color) != 7 or not color.startswith("#"):
        return None
    try:
        int(color[1:], 16)
    except ValueError:
        return None
    return color


def project_orca_material(spool: Dict[str, Any]) -> Optional[str]:
    explicit = _text(spool.get("orca_material"))
    if explicit:
        return explicit.upper()
    precise = _text(spool.get("material")).upper()
    return precise if precise in ORCA_SAFE_WIRE_MATERIALS else None


def _spoolman_spool_id(spool: Dict[str, Any]) -> Optional[int]:
    explicit = _positive_int(spool.get("spoolman_spool_id"))
    return explicit if explicit is not None else _positive_int(spool.get("spoolman_id"))


def build_orca_lane_record(slot_data: Dict[str, Any]) -> Dict[str, Any]:
    slot = slot_data.get("slot")
    if isinstance(slot, bool) or not isinstance(slot, int) or not 1 <= slot <= IFS_SLOT_COUNT:
        raise ValueError("invalid IFS slot for Orca lane projection")

    record: Dict[str, Any] = {
        "lane": str(slot - 1),
        "material": None,
        "color": None,
        "bed_temp": None,
        "nozzle_temp": None,
        "vendor": None,
        "vendor_name": None,
        "name": None,
        "spool_name": None,
        "spool_id": None,
        "filament_id": None,
        "orca_setting_id": None,
        "helix_material": None,
    }
    if not bool(slot_data.get("present", False)):
        return record

    spool = slot_data.get("spool")
    spool = spool if isinstance(spool, dict) else {}
    appearance = slot_data.get("appearance")
    appearance = appearance if isinstance(appearance, dict) else {}
    precise_material = _text(spool.get("material"))
    vendor = _text(spool.get("brand"))
    name = _text(spool.get("name")) or _text(spool.get("series"))

    record.update({
        "material": project_orca_material(spool),
        "color": _primary_color(appearance),
        "bed_temp": _temperature(spool.get("bed_temp")),
        "nozzle_temp": _temperature(spool.get("nozzle_temp")),
        "vendor": vendor or None,
        "vendor_name": vendor or None,
        "name": name or None,
        "spool_name": name or None,
        "spool_id": _spoolman_spool_id(spool),
        "filament_id": _text(spool.get("orca_filament_id")) or None,
        "orca_setting_id": _text(spool.get("orca_setting_id")) or None,
        "helix_material": precise_material or None,
    })
    return record


def _slot_map(slots: Iterable[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    result: Dict[int, Dict[str, Any]] = {}
    for slot_data in slots:
        if not isinstance(slot_data, dict):
            continue
        slot = slot_data.get("slot")
        if isinstance(slot, int) and not isinstance(slot, bool) and 1 <= slot <= IFS_SLOT_COUNT:
            result[slot] = slot_data
    return result


def find_duplicate_lane_keys(existing: Dict[str, Any]) -> List[Dict[str, str]]:
    conflicts: List[Dict[str, str]] = []
    for key, raw_record in existing.items():
        if not isinstance(key, str) or not isinstance(raw_record, dict):
            continue
        lane = raw_record.get("lane")
        if not isinstance(lane, str) or lane not in {"0", "1", "2", "3"}:
            continue
        expected_key = "lane%d" % (int(lane) + 1)
        if key != expected_key:
            conflicts.append({
                "lane": lane,
                "expected_key": expected_key,
                "conflicting_key": key,
            })
    conflicts.sort(key=lambda item: (item["lane"], item["conflicting_key"]))
    return conflicts


def build_orca_lane_data_projection(
    slots: Iterable[Dict[str, Any]],
    existing: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    existing = existing if isinstance(existing, dict) else {}
    by_slot = _slot_map(slots)
    records: Dict[str, Dict[str, Any]] = {}
    for slot in range(1, IFS_SLOT_COUNT + 1):
        desired = build_orca_lane_record(by_slot.get(slot, {"slot": slot, "present": False}))
        key = "lane%d" % slot
        current = existing.get(key)
        merged = dict(current) if isinstance(current, dict) else {}
        for field in ORCA_OWNED_FIELDS:
            merged[field] = desired[field]
        records[key] = merged
    conflicts = find_duplicate_lane_keys(existing)
    return {
        "namespace": ORCA_LANE_NAMESPACE,
        "records": records,
        "conflicts": conflicts,
        "publishable": not conflicts,
    }


def lane_data_fingerprint(records: Dict[str, Any]) -> str:
    encoded = json.dumps(records, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def summarize_orca_projection(projection: Dict[str, Any]) -> Dict[str, Any]:
    records = projection.get("records") if isinstance(projection.get("records"), dict) else {}
    conflicts = projection.get("conflicts") if isinstance(projection.get("conflicts"), list) else []
    return {
        "namespace": ORCA_LANE_NAMESPACE,
        "enabled": True,
        "direction": "printer_to_orca",
        "publishable": bool(projection.get("publishable", False)),
        "record_count": len(records),
        "conflicts": [dict(item) for item in conflicts if isinstance(item, dict)],
        "fingerprint": lane_data_fingerprint(records),
        "requires_moonraker_agent": True,
        "target_version": "2.4.2",
    }
