"""Log messages use loguru's {} placeholders: a %s is printed as it stands ("Using real Orthanc adapter at %s")."""

from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "radiarch"
CALL = re.compile(r"logger\.(?:trace|debug|info|success|warning|error|critical|exception)\(\s*((?:\"(?:[^\"\\]|\\.)*\"\s*)+)", re.S)
PERCENT = re.compile(r"%(?:\([^)]*\))?[-+ 0#]*\d*(?:\.\d+)?[sdfrgxe]")


def test_no_percent_placeholders_in_log_messages():
    found = []
    for path in sorted(SRC.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for m in CALL.finditer(text):
            if PERCENT.search(m.group(1)):
                found.append(f"{path.relative_to(SRC)}:{text.count(chr(10), 0, m.start()) + 1}")
    assert not found, found
