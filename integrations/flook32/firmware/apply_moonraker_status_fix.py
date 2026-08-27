#!/usr/bin/env python3
"""Apply the AD5X Moonraker-status fix to an upstream FLOOK32 firmware source.

The upstream .ino currently uses CRLF.  This patcher works on bytes so it does
not rewrite line endings or generate a whole-file diff.  It intentionally
fails if either expected upstream anchor changes.
"""
from pathlib import Path
import argparse

OLD_COMMENT = (
    "    // 1.1. Функция автоотключения выключена в настройках — не тратим ресурсы"
).encode("utf-8")
OLD_GATE = b"    if (!config.autoShutdownEnabled) return false;"
NEW_COMMENT = (
    "    // 1.1. Статус Moonraker отслеживается независимо от функции автоотключения"
).encode("utf-8")
NEW_LINE = (
    "    // Автоотключение по-прежнему проверяется отдельно в checkAutoShutdown()."
).encode("utf-8")


def patch_bytes(data: bytes) -> bytes:
    if data.count(OLD_COMMENT) != 1:
        raise ValueError("FLOOK32 firmware comment anchor changed upstream")
    if data.count(OLD_GATE) != 1:
        raise ValueError("FLOOK32 auto-shutdown gate anchor changed upstream")
    return data.replace(OLD_COMMENT, NEW_COMMENT, 1).replace(OLD_GATE, NEW_LINE, 1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    original = args.source.read_bytes()
    patched = patch_bytes(original)
    if not args.check:
        args.source.write_bytes(patched)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
