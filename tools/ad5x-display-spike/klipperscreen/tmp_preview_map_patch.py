from pathlib import Path


def replace_once(text, old, new, label):
    count = text.count(old)
    assert count == 1, f"{label}: expected 1 occurrence, found {count}"
    return text.replace(old, new, 1)


bridge = Path("klipper/extras/ad5x_ifs.py")
text = bridge.read_text()
text = replace_once(
    text,
    '            "assignments": [],\n            "auto_assign": {\n',
    '            "assignments": [],\n            "allowed_tool_count": 0,\n            "resolved_tool_map": [],\n            "auto_assign": {\n',
    "empty preview full map",
)
text = replace_once(
    text,
    '                "assignments": assignments,\n                "auto_assign": self._auto_assign_state(flags),\n',
    '                "assignments": assignments,\n                "allowed_tool_count": tool_count,\n                "resolved_tool_map": [int(slot) for slot in tools],\n                "auto_assign": self._auto_assign_state(flags),\n',
    "preview full map",
)
bridge.write_text(text)

model = Path("moonraker/components/plugins_ad5x_ifs_model.py")
text = model.read_text()
text = replace_once(
    text,
    '        "requirements": requirements,\n        "assignments": assignments,\n        "auto_assign": {\n',
    '        "requirements": requirements,\n        "assignments": assignments,\n        "allowed_tool_count": int(preview.get("allowed_tool_count") or 0),\n        "resolved_tool_map": [\n            int(slot) for slot in (preview.get("resolved_tool_map") or [])\n            if isinstance(slot, int) and not isinstance(slot, bool)\n        ],\n        "auto_assign": {\n',
    "token full map",
)
text = replace_once(
    text,
    '    if not preview.get("available", False) or not token:\n        block("preview_unavailable")\n',
    '    if not preview.get("available", False) or not token:\n        block("preview_unavailable")\n\n    allowed_tool_count = preview.get("allowed_tool_count")\n    resolved_tool_map = preview.get("resolved_tool_map")\n    if (\n        isinstance(allowed_tool_count, bool)\n        or not isinstance(allowed_tool_count, int)\n        or allowed_tool_count <= 0\n        or not isinstance(resolved_tool_map, list)\n        or len(resolved_tool_map) != allowed_tool_count\n        or any(\n            isinstance(slot, bool) or not isinstance(slot, int) or slot < 1 or slot > SLOT_COUNT\n            for slot in (resolved_tool_map or [])\n        )\n    ):\n        block("invalid_resolved_tool_map")\n',
    "launch full map validation",
)
model.write_text(text)

bridge_test = Path("tests/test_ad5x_ifs_bridge.py")
text = bridge_test.read_text()
text = replace_once(
    text,
    '        self.assertEqual(\n            preview["assignments"],\n            [{"tool": 0, "slot": 2}, {"tool": 1, "slot": 1}],\n        )\n',
    '        self.assertEqual(\n            preview["assignments"],\n            [{"tool": 0, "slot": 2}, {"tool": 1, "slot": 1}],\n        )\n        self.assertEqual(preview["allowed_tool_count"], 2)\n        self.assertEqual(preview["resolved_tool_map"], [2, 1])\n',
    "bridge preview assertions",
)
bridge_test.write_text(text)

launch_test = Path("tests/test_plugins_ad5x_ifs_launch_contract.py")
text = launch_test.read_text()
text = replace_once(
    text,
    '        "assignments": [\n            {"tool": 0, "slot": 3},\n            {"tool": 1, "slot": 1},\n        ],\n        "auto_assign": {\n',
    '        "assignments": [\n            {"tool": 0, "slot": 3},\n            {"tool": 1, "slot": 1},\n        ],\n        "allowed_tool_count": 2,\n        "resolved_tool_map": [3, 1],\n        "auto_assign": {\n',
    "launch fixture full map",
)
insert = '''\n    def test_invalid_resolved_tool_map_blocks_launch_candidate(self):\n        source = preview()\n        source["resolved_tool_map"] = [3, 9]\n        plan = model.build_preprint_plan(source, slots())\n        gate = model.build_job_launch_gate(\n            source,\n            plan,\n            module_state="ready",\n            print_state="standby",\n            operation_state="idle",\n        )\n        self.assertFalse(gate["candidate"])\n        self.assertIn("invalid_resolved_tool_map", gate["blockers"])\n\n'''
marker = '    def test_capability_keeps_start_and_mapping_write_disabled(self):\n'
assert marker in text
text = text.replace(marker, insert + marker, 1)
launch_test.write_text(text)

backend_preview_test = Path("tests/test_plugins_ad5x_ifs_job_preview.py")
text = backend_preview_test.read_text()
text = replace_once(
    text,
    '    "assignments": [\n        {"tool": 0, "slot": 3},\n        {"tool": 1, "slot": 1},\n    ],\n    "auto_assign": {\n',
    '    "assignments": [\n        {"tool": 0, "slot": 3},\n        {"tool": 1, "slot": 1},\n    ],\n    "allowed_tool_count": 2,\n    "resolved_tool_map": [3, 1],\n    "auto_assign": {\n',
    "backend preview fixture full map",
)
backend_preview_test.write_text(text)
