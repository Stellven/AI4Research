"""Compile a LaTeX snippet to a cropped PNG via pdflatex + pdftoppm.

Used by tools/wiki2dag.py to rasterize TikZ figures that have no
\\includegraphics counterpart, so they can flow into the poster as
regular visual nodes via the existing inject-figures pipeline.

The snippet is wrapped in a \\documentclass{standalone} document, which
auto-crops to content extent — no manual cropping needed.

CLI (for standalone testing):
    python3 tools/rasterize_latex.py \\
        --snippet-file path/to/tikz_body.tex \\
        --tikz-from paper/main.tex \\
        --preamble-file paper/math_commands.tex \\
        --out-dir /tmp/rasterize-test \\
        --out-name tikz_chain
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

try:
    from PIL import Image
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False


class RasterizeError(Exception):
    """pdflatex or pdftoppm failed. Caller (wiki2dag) typically catches
    and skips the snippet with a stderr warning, leaving the rest of the
    pipeline intact."""


# Packages that are nearly always needed for TikZ + booktabs + math.
# Extra preamble (math_commands, \usetikzlibrary, pgfplots) is appended
# by the caller via the `preamble` argument.
_DEFAULT_PREAMBLE_PACKAGES = (
    r"\usepackage{tikz}"               "\n"
    r"\usepackage{amsmath,amssymb}"    "\n"
    r"\usepackage{booktabs}"           "\n"
    r"\usepackage{multirow}"           "\n"
    r"\usepackage{array}"              "\n"
    r"\usepackage{xcolor}"             "\n"
)

_TIKZ_LIBRARY_PATTERN = re.compile(r"\\usetikzlibrary\{[^}]+\}")
_USEPACKAGE_PGFPLOTS = re.compile(r"\\usepackage(?:\[[^\]]*\])?\{pgfplots\}")


def extract_tikz_setup(main_tex_path: Path) -> str:
    """Pull `\\usetikzlibrary{...}` lines and `\\usepackage{pgfplots}` (if
    present) out of a paper's main.tex. Returns them joined by newlines
    so the caller can append to the standalone preamble."""
    if not main_tex_path.is_file():
        return ""
    text = main_tex_path.read_text(encoding="utf-8")
    parts = list(_TIKZ_LIBRARY_PATTERN.findall(text))
    if _USEPACKAGE_PGFPLOTS.search(text):
        parts.append(r"\usepackage{pgfplots}")
    return "\n".join(parts)


def rasterize_latex_snippet(
    snippet: str,
    out_dir: Path,
    out_name: str,
    preamble: str = "",
    dpi: int = 200,
    timeout_sec: int = 60,
    paper_dir: Optional[Path] = None,
) -> tuple[Path, str]:
    """Compile `snippet` to `out_dir/out_name.png` at the given DPI.

    snippet     — the body content (env contents; the function wraps it
                  in \\documentclass{standalone} ... \\begin{document} ...
                  \\end{document}).
    preamble    — extra `\\usepackage{...}`, `\\usetikzlibrary{...}`,
                  `\\newcommand{...}` lines to inject before \\begin{document}.
                  Typical caller: `extract_tikz_setup(main.tex) + "\\n" +
                  math_commands.tex content`.
    dpi         — pdftoppm render DPI (200 gives ~poster-print quality).
    timeout_sec — wall clock per pdflatex/pdftoppm call.
    paper_dir   — optional path to the source paper directory. When
                  provided, TEXINPUTS is set so pdflatex can resolve
                  `\\input{figures/data/foo.tex}` and pgfplots `.dat`
                  files that live relative to the paper (rather than
                  relative to the per-snippet tempdir).

    Returns (png_path, "WxH"). Resolution is empty string if Pillow is
    not installed.

    Raises RasterizeError on compile failure; preserves the failed .tex
    + .log under `out_dir/_failed/out_name/` for debugging.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    full_doc = (
        r"\documentclass[border=2pt]{standalone}" "\n"
        + _DEFAULT_PREAMBLE_PACKAGES
        + (preamble + "\n" if preamble else "")
        + r"\begin{document}" "\n"
        + snippet + "\n"
        + r"\end{document}" "\n"
    )

    # If the caller passed paper_dir, prepend it to TEXINPUTS so
    # `\input{}` / pgfplots data file references in the snippet resolve
    # against the source paper. TEXINPUTS uses `:` separator on Unix and
    # `;` on Windows; trailing separator means "also search the default
    # paths" (so we don't replace system TeX Live paths).
    pdflatex_env: Optional[dict] = None
    if paper_dir is not None:
        import os as _os
        sep = ";" if _os.name == "nt" else ":"
        pdflatex_env = _os.environ.copy()
        prev = pdflatex_env.get("TEXINPUTS", "")
        pdflatex_env["TEXINPUTS"] = (
            f"{Path(paper_dir).resolve()}{sep}{prev}{sep}"
        )

    with tempfile.TemporaryDirectory(prefix="rasterize_latex_") as tmp_str:
        tmp = Path(tmp_str)
        tex_path = tmp / f"{out_name}.tex"
        tex_path.write_text(full_doc, encoding="utf-8")

        try:
            result = subprocess.run(
                [
                    "pdflatex",
                    "-interaction=nonstopmode",
                    "-halt-on-error",
                    f"-output-directory={tmp}",
                    str(tex_path),
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout_sec,
                env=pdflatex_env,
            )
        except FileNotFoundError as e:
            raise RasterizeError(
                "pdflatex not found on PATH. Install TeX Live "
                "(brew install --cask mactex on macOS, "
                "apt install texlive-full on Debian/Ubuntu)."
            ) from e
        except subprocess.TimeoutExpired as e:
            raise RasterizeError(
                f"pdflatex timed out after {timeout_sec}s on {out_name}"
            ) from e

        pdf_path = tmp / f"{out_name}.pdf"
        if result.returncode != 0 or not pdf_path.is_file():
            log_path = tmp / f"{out_name}.log"
            log_tail = ""
            if log_path.is_file():
                log_lines = log_path.read_text(
                    encoding="utf-8", errors="replace"
                ).splitlines()
                log_tail = "\n".join(log_lines[-12:])
            fail_dir = out_dir / "_failed" / out_name
            fail_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy(tex_path, fail_dir / tex_path.name)
            if log_path.is_file():
                shutil.copy(log_path, fail_dir / log_path.name)
            raise RasterizeError(
                f"pdflatex failed on {out_name} "
                f"(exit {result.returncode}). Tail of log:\n{log_tail}\n"
                f"Saved to {fail_dir}/ for inspection."
            )

        # pdf → png. pdftoppm with -singlefile writes to {stem}.png.
        png_stem = out_dir / out_name
        try:
            subprocess.run(
                [
                    "pdftoppm",
                    "-r", str(dpi),
                    "-png",
                    "-singlefile",
                    str(pdf_path),
                    str(png_stem),
                ],
                check=True,
                capture_output=True,
                timeout=timeout_sec,
            )
        except FileNotFoundError as e:
            raise RasterizeError(
                "pdftoppm not found on PATH. Install poppler "
                "(brew install poppler / apt install poppler-utils)."
            ) from e
        except subprocess.CalledProcessError as e:
            stderr_tail = (e.stderr or b"").decode(errors="replace")[-300:]
            raise RasterizeError(
                f"pdftoppm failed on {out_name}: {stderr_tail}"
            ) from e

    png_path = out_dir / f"{out_name}.png"
    if not png_path.is_file():
        raise RasterizeError(
            f"pdftoppm reported success but {png_path} is missing"
        )

    if _HAS_PIL:
        try:
            with Image.open(png_path) as img:
                resolution = f"{img.width}x{img.height}"
        except Exception:
            resolution = ""
    else:
        resolution = ""

    return png_path, resolution


def _cli() -> int:
    p = argparse.ArgumentParser(
        description="Compile a LaTeX snippet to a cropped PNG."
    )
    p.add_argument("--snippet", help="LaTeX snippet body (env contents)")
    p.add_argument(
        "--snippet-file",
        help="File containing the snippet body (alternative to --snippet)",
    )
    p.add_argument(
        "--preamble-file",
        help="File whose content is inlined into the preamble "
             "(e.g. paper/math_commands.tex)",
    )
    p.add_argument(
        "--tikz-from",
        help="Path to a main.tex; \\usetikzlibrary{...} lines are extracted "
             "from it and prepended to the preamble.",
    )
    p.add_argument("--out-dir", required=True)
    p.add_argument("--out-name", required=True)
    p.add_argument("--dpi", type=int, default=200)
    args = p.parse_args()

    if not args.snippet and not args.snippet_file:
        p.error("provide --snippet or --snippet-file")

    snippet = args.snippet or Path(args.snippet_file).read_text(encoding="utf-8")

    preamble_parts: list[str] = []
    if args.tikz_from:
        preamble_parts.append(extract_tikz_setup(Path(args.tikz_from)))
    if args.preamble_file:
        preamble_parts.append(
            Path(args.preamble_file).read_text(encoding="utf-8")
        )
    preamble = "\n".join(part for part in preamble_parts if part.strip())

    try:
        png, res = rasterize_latex_snippet(
            snippet=snippet,
            out_dir=Path(args.out_dir),
            out_name=args.out_name,
            preamble=preamble,
            dpi=args.dpi,
        )
    except RasterizeError as e:
        print(f"[error] {e}", file=sys.stderr)
        return 1

    print(f"[ok] {png} ({res or 'no resolution'})")
    return 0


def _emit_compat(command: str, status: str, payload: dict, *, ok: bool = False) -> int:
    print(json.dumps({
        "schema": "autosci_rasterize_latex_cli.v1",
        "command": command,
        "status": status,
        "ok": ok,
        **payload,
    }, indent=2, sort_keys=True))
    return 1 if status == "failed" else 0


def _compat_cli(argv: list[str]) -> int | None:
    if not argv or argv[0] not in {"diagnose", "check-pdf", "rasterize"}:
        return None
    command = argv[0]
    if command == "diagnose":
        tools = {name: shutil.which(name) for name in ("latexmk", "pdflatex", "pdftoppm", "gs")}
        return _emit_compat("diagnose", "completed", {"tools": tools}, ok=True)
    if command == "check-pdf":
        p = argparse.ArgumentParser(description="Check a PDF exists.")
        p.add_argument("pdf")
        args = p.parse_args(argv[1:])
        pdf = Path(args.pdf).expanduser()
        if not pdf.exists():
            return _emit_compat("check-pdf", "failed", {"pdf": str(pdf), "limitations": ["PDF file does not exist."]})
        return _emit_compat("check-pdf", "completed", {"pdf": str(pdf.resolve()), "bytes": pdf.stat().st_size}, ok=True)
    p = argparse.ArgumentParser(description="Rasterize a PDF with pdftoppm.")
    p.add_argument("pdf")
    p.add_argument("--out-dir", default="artifacts/autosci/workspace/paper/rasterized")
    args = p.parse_args(argv[1:])
    pdf = Path(args.pdf).expanduser()
    out_dir = Path(args.out_dir).expanduser()
    pdftoppm = shutil.which("pdftoppm")
    if not pdf.exists():
        return _emit_compat("rasterize", "failed", {"pdf": str(pdf), "limitations": ["PDF file does not exist."]})
    if not pdftoppm:
        return _emit_compat("rasterize", "inconclusive", {"pdf": str(pdf.resolve()), "limitations": ["pdftoppm is unavailable."]})
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = out_dir / pdf.stem
    proc = subprocess.run([pdftoppm, "-png", str(pdf), str(prefix)], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if proc.returncode != 0:
        return _emit_compat("rasterize", "failed", {"stderr": proc.stderr, "stdout": proc.stdout})
    files = [str(path.resolve()) for path in sorted(out_dir.glob(f"{pdf.stem}-*.png"))]
    return _emit_compat("rasterize", "completed", {"files": files, "count": len(files)}, ok=bool(files))


if __name__ == "__main__":
    compat_result = _compat_cli(sys.argv[1:])
    sys.exit(_cli() if compat_result is None else compat_result)
