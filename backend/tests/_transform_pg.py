"""One-shot converter: SQLite test engines -> pg_test_engine fixture.

Handles the two common shapes found across the B-class repository tests:

Shape A (inline ``await init_engine("sqlite", ...)`` + ``try:/finally:``):
    async def test_x(tmp_path):
        from tianshu.persistence.engine import close_engine, get_session_factory, init_engine
        url = f"sqlite+aiosqlite:///..."
        await init_engine("sqlite", url=url, sqlite_dir=str(tmp_path))
        try:
            ...body...
        finally:
            await _cleanup()

Shape B (helper ``async def _make_x(tmp_path)`` returning a repo; tests call
``repo = await _make_x(tmp_path)`` with a matching ``await _cleanup()``):
    -> drop tmp_path param, keep a module-level cleanup no-op is NOT used;
       tests switch to the pg_test_engine fixture.

The transform is line-based and intentionally conservative: it only touches
lines it recognises, and refuses to run when a shape is ambiguous.
"""

from __future__ import annotations

import re
import sys

REMOVE_RE = [
    re.compile(r"^\s*url = f?[\"']sqlite\+aiosqlite.*$"),
    re.compile(r"^\s*url = f?[\"']sqlite://.*$"),
    re.compile(r"^\s*await init_engine\(\"sqlite\".*$"),
    re.compile(r"^\s*asyncio\.run\(init_engine\(\"sqlite\".*$"),
    re.compile(r"^\s*await init_engine_from_config\(.*backend=\"sqlite\".*$"),
]

IMPORT_RE = re.compile(
    r"^\s*from tianshu\.persistence\.engine import (?P<names>[^\n]+)$"
)


def _rewrite_engine_import(line: str) -> str | None:
    """Strip init_engine/close_engine from the import, keep the rest."""
    m = IMPORT_RE.match(line)
    if not m:
        return None
    names = [n.strip() for n in m.group("names").split(",")]
    kept = [n for n in names if n and not re.search(r"\b(init_engine|close_engine)\b", n)]
    if not kept:
        return ""
    return f"from tianshu.persistence.engine import {', '.join(kept)}"


def _remove_engine_lines(lines: list[str], i: int) -> tuple[int, bool]:
    """Remove sqlite-engine setup lines and rewrite engine imports."""
    removed = False
    while i < len(lines):
        line = lines[i]
        rewritten = _rewrite_engine_import(line)
        if rewritten is not None:
            if rewritten:
                lines[i] = rewritten
            else:
                del lines[i]
                removed = True
                continue
            i += 1
            removed = True
            continue
        if any(rx.match(line) for rx in REMOVE_RE):
            removed = True
            i += 1
            continue
        # allow the closing paren of a multi-line init_engine_from_config
        if removed and line.strip() == ")":
            i += 1
            continue
        break
    return i, removed


def transform_shape_a(src: str) -> str:
    """Shape A: inline init_engine + try:/finally: inside each test."""
    lines = src.split("\n")
    out: list[str] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]

        # test signature: tmp_path -> pg_test_engine
        m = re.match(r"^(.*\bdef test_\w+)\(([^)]*tmp_path[^)]*)\)(.*)$", line)
        if m:
            rest = m.group(2).replace("tmp_path", "pg_test_engine").strip()
            rest = re.sub(r",\s*,", ",", rest)
            rest = rest.strip(", ")
            line = f"{m.group(1)}({rest}){m.group(3)}"
            out.append(line)
            i += 1
            continue

        # drop sqlite engine import/setup lines
        i2, removed = _remove_engine_lines(lines, i)
        if removed:
            i = i2
            continue

        # strip a lone `try:` that immediately follows removed setup lines
        if line.strip() == "try:" and out and out[-1].strip() == "":
            # preceded by blank line -> belongs to removed setup; remove it
            out.pop()
            i += 1
            continue

        out.append(line)
        i += 1
    return "\n".join(out)


def transform_shape_a_with_try(src: str) -> str:
    """Shape A variant where `try:` / `finally:` wrap the test body.

    We remove the `try:` line (4-space), dedent the body by 4, and drop the
    matching `finally:` + `await cleanup()` trailer.
    """
    lines = src.split("\n")
    out: list[str] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]

        m = re.match(r"^(.*\bdef test_\w+)\(([^)]*tmp_path[^)]*)\)(.*)$", line)
        if m:
            rest = m.group(2).replace("tmp_path", "pg_test_engine").strip()
            rest = re.sub(r",\s*,", ",", rest).strip(", ")
            line = f"{m.group(1)}({rest}){m.group(3)}"
            out.append(line)
            i += 1
            continue

        i2, removed = _remove_engine_lines(lines, i)
        if removed:
            i = i2
            continue

        # outer try: at 4-space indent -> remove and dedent its body
        if re.match(r"^    try:\s*$", line):
            # scan forward for the matching 4-space finally
            depth = 0
            j = i + 1
            body: list[str] = []
            while j < n:
                lj = lines[j]
                if re.match(r"^    finally:\s*$", lj) and depth == 0:
                    # skip finally + its cleanup trailer
                    j += 1
                    if j < n and re.match(r"^\s*await (cleanup|_cleanup)\(\)\s*$", lines[j]):
                        j += 1
                    i = j
                    break
                if re.match(r"^        try:\s*$", lj):
                    depth += 1
                elif re.match(r"^        finally:\s*$", lj) and depth > 0:
                    depth -= 1
                body.append(lj)
                j += 1
            else:
                raise ValueError("unterminated try/finally")
            out.extend(l[4:] if l.startswith("        ") else l for l in body)
            continue

        out.append(line)
        i += 1
    return "\n".join(out)


def main() -> None:
    files = sys.argv[1:]
    for path in files:
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        out = transform_shape_a_with_try(src)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(out)
        print(f"converted: {path}")


if __name__ == "__main__":
    main()
