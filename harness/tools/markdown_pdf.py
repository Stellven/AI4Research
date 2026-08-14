#!/usr/bin/env python3
"""Dependency-free Markdown text to auditable PDF deliverable constructor."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


def _plain_lines(markdown: str) -> list[str]:
    lines = []
    for raw in markdown.splitlines():
        line = re.sub(r"!\[[^]]*]\([^)]*\)", "[image]", raw)
        line = re.sub(r"\[([^]]+)]\([^)]*\)", r"\1", line)
        line = re.sub(r"^\s{0,3}(?:#{1,6}|[-*+]\s+|\d+[.)]\s+|>\s*)", "", line)
        line = re.sub(r"[*_`~]", "", line).strip()
        if not line:
            lines.append("")
            continue
        while len(line) > 92:
            split = line.rfind(" ", 0, 92)
            split = split if split > 20 else 92
            lines.append(line[:split].strip())
            line = line[split:].strip()
        lines.append(line)
    return lines or [""]


def _pdf_escape(value: str) -> str:
    ascii_value = value.encode("ascii", "replace").decode("ascii")
    return ascii_value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_pdf(markdown_path: Path, output_path: Path) -> dict[str, object]:
    source = markdown_path.read_text(encoding="utf-8-sig")
    lines = _plain_lines(source)
    per_page = 48
    pages = [lines[index:index + per_page] for index in range(0, len(lines), per_page)]
    objects: list[bytes] = []
    page_ids = [4 + index * 2 for index in range(len(pages))]
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{item} 0 R" for item in page_ids)
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode())
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for page_index, page_lines in enumerate(pages):
        page_id = page_ids[page_index]
        content_id = page_id + 1
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>".encode()
        )
        commands = ["BT", "/F1 10 Tf", "12 TL", "54 738 Td"]
        for line in page_lines:
            commands.append(f"({_pdf_escape(line)}) Tj")
            commands.append("T*")
        commands.append("ET")
        stream = "\n".join(commands).encode("ascii")
        objects.append(f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream")
    payload = bytearray(b"%PDF-1.4\n%Solar\n")
    offsets = [0]
    for object_id, obj in enumerate(objects, 1):
        offsets.append(len(payload))
        payload.extend(f"{object_id} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(payload)
    payload.extend(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        payload.extend(f"{offset:010d} 00000 n \n".encode())
    payload.extend(f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(payload)
    return verify_pdf(output_path, expected_text=source)


def verify_pdf(path: Path, *, expected_text: str | None = None) -> dict[str, object]:
    data = path.read_bytes()
    text = data.decode("ascii", "replace")
    pages = len(re.findall(r"/Type /Page\b", text))
    expected_markers = []
    if expected_text is not None:
        expected_markers = [line for line in _plain_lines(expected_text) if len(line) >= 8][:3]
    result = {
        "schema_version": "solar.markdown_pdf_verification.v1",
        "path": str(path),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "page_count": pages,
        "header_valid": data.startswith(b"%PDF-1.4"),
        "eof_valid": data.rstrip().endswith(b"%%EOF"),
        "xref_present": "\nxref\n" in text and "\nstartxref\n" in text,
        "expected_markers_present": all(_pdf_escape(marker) in text for marker in expected_markers),
    }
    result["valid"] = all(result[key] for key in ("header_valid", "eof_valid", "xref_present", "expected_markers_present")) and pages > 0
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("--input", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = build_pdf(args.input, args.output) if args.command == "build" else verify_pdf(args.input)
    except (OSError, UnicodeError) as exc:
        print(json.dumps({"valid": False, "error": str(exc)}))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("valid") else 2


if __name__ == "__main__":
    raise SystemExit(main())
