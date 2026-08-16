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

    Existing Flashforge/Z-Mod metadata exposes one RGB value.  It is preserved as
    the first color of a solid appearance.  Richer sources may provide multiple
    colors plus a finish.  Unknown/invalid values fail soft to a neutral object.
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

    spoolman_id = metadata.get("spoolman_id")
    if not isinstance(spoolman_id, int) or spoolman_id <= 0:
        spoolman_id = None

    remaining_g = metadata.get("remaining_g")
    if not isinstance(remaining_g, (int, float)) or remaining_g < 0:
        remaining_g = None

    return {
        "source": source,
        "brand": text("brand"),
        "series": text("series"),
        "name": text("name"),
        "material": text("material"),
        "variant": text("variant"),
        "spoolman_id": spoolman_id,
        "remaining_g": remaining_g,
    }


def get_ifs_capabilities() -> Dict[str, Any]:
    """Capabilities describe implementation support, not current permission."""

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
        },
        "metadata": {
            "multi_color": True,
            "finish": True,
            "spoolman": True,
            "slicer": True,
            "rfid": False,
        },
        "mapping": {
            "tool_to_slot": True,
            "endless_spool": False,
        },
    }


def _global_write_block_reason(
    module_state: str,
    print_state: str,
    operation_state: str,
) -> str:
    if module_state != "ready":
        return "ifs_not_ready"
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
) -> Dict[str, Any]:
    """Centralize per-slot action permission so frontends do not own safety logic."""

    blocked = _global_write_block_reason(module_state, print_state, operation_state)
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
) -> Dict[str, Any]:
    raw_slot = raw_slot if isinstance(raw_slot, dict) else {}
    metadata = metadata if isinstance(metadata, dict) else {}

    slot = raw_slot.get("slot", 0)
    if not isinstance(slot, int):
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
    )

    result = dict(raw_slot)
    result["slot"] = slot
    result["present"] = present
    result["stall"] = stall

    # Legacy flat keys are retained during migration for existing frontends.
    if isinstance(legacy_material, str) and legacy_material:
        result["material"] = legacy_material
    if _normalize_hex_color(legacy_color):
        result["color"] = _normalize_hex_color(legacy_color)

    result["spool"] = spool
    result["appearance"] = appearance
    result["metadata_status"] = (
        "assigned" if present and has_metadata else "stale" if has_metadata else "none"
    )
    result["active"] = slot == active_slot and active_slot > 0
    result["permissions"] = compute_slot_permissions(
        slot=slot,
        present=present,
        active_slot=active_slot,
        filament_at_toolhead=filament_at_toolhead,
        module_state=module_state,
        print_state=print_state,
        operation_state=operation_state,
    )
    return result
