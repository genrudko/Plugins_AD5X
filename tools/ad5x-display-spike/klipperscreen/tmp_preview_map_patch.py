from pathlib import Path


def edit_scope(text, start_marker, end_marker, transform):
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    scope = text[start:end]
    updated = transform(scope)
    assert updated != scope, f"no change inside {start_marker!r} scope"
    return text[:start] + updated + text[end:]


def replace_required(text, old, new, label):
    if new in text:
        return text
    assert old in text, f"{label}: anchor missing"
    return text.replace(old, new, 1)


# 1. Bridge: preserve the complete Z-Mod tool vector, not only tools that
# appeared in requirements. PRINT_ZCOLOR/file.json semantics need the complete
# resolved vector later, while assignments remain the normalized per-required-tool
# presentation used by current frontends.
bridge = Path("klipper/extras/ad5x_ifs.py")
text = bridge.read_text()
text = replace_required(
    text,
    '            "assignments": [],\n            "auto_assign": {\n',
    '            "assignments": [],\n            "allowed_tool_count": 0,\n            "resolved_tool_map": [],\n            "auto_assign": {\n',
    "empty preview full map",
)
text = replace_required(
    text,
    '                "assignments": assignments,\n                "auto_assign": self._auto_assign_state(flags),\n',
    '                "assignments": assignments,\n                "allowed_tool_count": tool_count,\n                "resolved_tool_map": [int(slot) for slot in tools],\n                "auto_assign": self._auto_assign_state(flags),\n',
    "preview full map",
)
assert '"allowed_tool_count": tool_count' in text
assert '"resolved_tool_map": [int(slot) for slot in tools]' in text
bridge.write_text(text)


# 2. Model: include the complete map in the semantic preview token and fail
# closed if it cannot represent the exact vector expected by the Z-Mod launch
# lifecycle. The write path remains disabled.
model = Path("moonraker/components/plugins_ad5x_ifs_model.py")
text = model.read_text()


def patch_token(scope):
    return replace_required(
        scope,
        '        "requirements": requirements,\n        "assignments": assignments,\n        "auto_assign": {\n',
        '        "requirements": requirements,\n        "assignments": assignments,\n        "allowed_tool_count": int(preview.get("allowed_tool_count") or 0),\n        "resolved_tool_map": [\n            int(slot) for slot in (preview.get("resolved_tool_map") or [])\n            if isinstance(slot, int) and not isinstance(slot, bool)\n        ],\n        "auto_assign": {\n',
        "token full map",
    )


if '"allowed_tool_count": int(preview.get("allowed_tool_count") or 0)' not in text:
    text = edit_scope(
        text,
        "def build_job_preview_token(",
        "def build_job_launch_gate(",
        patch_token,
    )

validation = '''    allowed_tool_count = preview.get("allowed_tool_count")
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
'''

if 'block("invalid_resolved_tool_map")' not in text:
    anchor = '    if not preview.get("available", False) or not token:\n        block("preview_unavailable")\n'
    insertion = anchor + "\n" + validation
    text = edit_scope(
        text,
        "def build_job_launch_gate(",
        "def build_preprint_plan(",
        lambda scope: replace_required(scope, anchor, insertion, "launch full map validation"),
    )

assert '"allowed_tool_count": int(preview.get("allowed_tool_count") or 0)' in text
assert 'block("invalid_resolved_tool_map")' in text
model.write_text(text)


# 3. Tests: prove bridge preservation, token stability and launch fail-closed
# behavior. The second semantically-identical preview must carry the same full
# vector, otherwise token equality would correctly fail.
bridge_test = Path("tests/test_ad5x_ifs_bridge.py")
text = bridge_test.read_text()
if 'self.assertEqual(preview["resolved_tool_map"], [2, 1])' not in text:
    anchor = '''        self.assertEqual(
            preview["assignments"],
            [{"tool": 0, "slot": 2}, {"tool": 1, "slot": 1}],
        )
'''
    addition = anchor + '''        self.assertEqual(preview["allowed_tool_count"], 2)
        self.assertEqual(preview["resolved_tool_map"], [2, 1])
'''
    text = replace_required(text, anchor, addition, "bridge preview assertions")
bridge_test.write_text(text)

launch_test = Path("tests/test_plugins_ad5x_ifs_launch_contract.py")
text = launch_test.read_text()
if '"allowed_tool_count": 2' not in text:
    anchor = '''        "assignments": [
            {"tool": 0, "slot": 3},
            {"tool": 1, "slot": 1},
        ],
        "auto_assign": {
'''
    addition = '''        "assignments": [
            {"tool": 0, "slot": 3},
            {"tool": 1, "slot": 1},
        ],
        "allowed_tool_count": 2,
        "resolved_tool_map": [3, 1],
        "auto_assign": {
'''
    text = replace_required(text, anchor, addition, "launch fixture full map")

if '"resolved_tool_map": list(first["resolved_tool_map"]),' not in text:
    anchor = '            "assignments": list(first["assignments"]),\n'
    addition = anchor + '            "allowed_tool_count": first["allowed_tool_count"],\n            "resolved_tool_map": list(first["resolved_tool_map"]),\n'
    text = replace_required(text, anchor, addition, "stable-token equivalent preview")

if 'def test_invalid_resolved_tool_map_blocks_launch_candidate' not in text:
    marker = '    def test_capability_keeps_start_and_mapping_write_disabled(self):\n'
    insert = '''    def test_invalid_resolved_tool_map_blocks_launch_candidate(self):
        source = preview()
        source["resolved_tool_map"] = [3, 9]
        plan = model.build_preprint_plan(source, slots())
        gate = model.build_job_launch_gate(
            source,
            plan,
            module_state="ready",
            print_state="standby",
            operation_state="idle",
        )
        self.assertFalse(gate["candidate"])
        self.assertIn("invalid_resolved_tool_map", gate["blockers"])

'''
    text = replace_required(text, marker, insert + marker, "invalid full map test")
launch_test.write_text(text)

backend_preview_test = Path("tests/test_plugins_ad5x_ifs_job_preview.py")
text = backend_preview_test.read_text()
if '"resolved_tool_map": [3, 1]' not in text:
    anchor = '''    "assignments": [
        {"tool": 0, "slot": 3},
        {"tool": 1, "slot": 1},
    ],
    "auto_assign": {
'''
    addition = '''    "assignments": [
        {"tool": 0, "slot": 3},
        {"tool": 1, "slot": 1},
    ],
    "allowed_tool_count": 2,
    "resolved_tool_map": [3, 1],
    "auto_assign": {
'''
    text = replace_required(text, anchor, addition, "backend preview fixture full map")
backend_preview_test.write_text(text)
