#!/usr/bin/env python3
"""Hide the legacy FLOOK32 temperature sensor from Fluidd without losing it."""
from pathlib import Path
import sys

VISIBLE = b"[temperature_sensor chamber]"
HIDDEN = b"[temperature_sensor _flook32_chamber]"
SENSOR_TYPE = b"sensor_type: flook32"


def section_bounds(lines, index):
    end = len(lines)
    for pos in range(index + 1, len(lines)):
        if lines[pos].lstrip().startswith(b"["):
            end = pos
            break
    return index, end


def migrate(path):
    p = Path(path)
    data = p.read_bytes()
    lines = data.splitlines(keepends=True)
    visible = [i for i, line in enumerate(lines) if line.strip() == VISIBLE]
    hidden = [i for i, line in enumerate(lines) if line.strip() == HIDDEN]

    if hidden:
        if len(hidden) != 1 or visible:
            raise RuntimeError("ambiguous FLOOK32 chamber sensor sections")
        return "already-hidden"

    if not visible:
        return "not-applicable"
    if len(visible) != 1:
        raise RuntimeError("multiple [temperature_sensor chamber] sections")

    start, end = section_bounds(lines, visible[0])
    body = [line.strip() for line in lines[start + 1:end]]
    if SENSOR_TYPE not in body:
        return "not-applicable"

    line = lines[start]
    newline = b"\r\n" if line.endswith(b"\r\n") else (b"\n" if line.endswith(b"\n") else b"")
    lines[start] = HIDDEN + newline
    p.write_bytes(b"".join(lines))
    return "migrated"


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: migrate_cfg.py PATH")
    try:
        result = migrate(sys.argv[1])
    except Exception as exc:
        print("ERROR: {}".format(exc), file=sys.stderr)
        raise SystemExit(1)
    print(result)
