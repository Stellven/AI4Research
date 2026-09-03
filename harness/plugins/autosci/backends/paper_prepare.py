"""Prepare and parse paper sources for Solar-native AutoSci ingestion."""

from __future__ import annotations

import gzip
import importlib
import json
import os
import re
import shutil
import tarfile
import zipfile
import hashlib
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

try:
    import fitz

    HAS_PYMUPDF = True
except ImportError:  # pragma: no cover - exercised only on minimal envs
    fitz = None
    HAS_PYMUPDF = False

try:
    import requests

    HAS_REQUESTS = True
except ImportError:  # pragma: no cover - requests is expected in AutoSci envs
    requests = None
    HAS_REQUESTS = False


ARXIV_NEW_ID_PATTERN = re.compile(r"(?<!\d)(\d{4}\.\d{4,5})(?:v\d+)?(?!\d)", re.IGNORECASE)
ARXIV_OLD_ID_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])([a-z\-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?(?!\d)",
    re.IGNORECASE,
)
ARXIV_URL_PATTERN = re.compile(
    r"https?://(?:www\.)?arxiv\.org/(?:abs|pdf|e-print)/([^?#\s]+)",
    re.IGNORECASE,
)
ARXIV_DOI_URL_PATTERN = re.compile(
    r"https?://(?:dx\.)?doi\.org/10\.48550/arxiv\.([^?#\s]+)",
    re.IGNORECASE,
)
MAX_SOURCE_ARCHIVE_BYTES = 250_000_000
MAX_PARSED_SECTION_CHARS = 160_000


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")
    return slug or "paper"


def normalize_arxiv_id(arxiv_id: str) -> str:
    arxiv_id = str(arxiv_id or "").strip()
    if not arxiv_id:
        return ""
    arxiv_id = arxiv_id.removeprefix("ARXIV:").removeprefix("arxiv:")
    return re.sub(r"v\d+$", "", arxiv_id, flags=re.IGNORECASE).strip()


def extract_arxiv_id(text: str) -> str:
    url_match = ARXIV_URL_PATTERN.search(str(text or ""))
    if url_match:
        return normalize_arxiv_id(url_match.group(1).removesuffix(".pdf"))
    for pattern in (ARXIV_NEW_ID_PATTERN, ARXIV_OLD_ID_PATTERN):
        match = pattern.search(str(text or ""))
        if match:
            return normalize_arxiv_id(match.group(1))
    return ""


def _display_path(path: Path, roots: list[Path]) -> str:
    resolved = path.resolve()
    for root in roots:
        try:
            return resolved.relative_to(root.resolve()).as_posix()
        except ValueError:
            continue
    return path.as_posix()


def _resolve_source(source: str | Path, roots: list[Path]) -> Path:
    path = Path(str(source))
    if path.is_absolute():
        return path
    for root in roots:
        candidate = root / path
        if candidate.exists():
            return candidate
    return roots[0] / path


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _read_text(path: Path, limit: int = 200_000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")[:limit]
    except OSError:
        return ""


def _file_sha256(path: Path) -> str:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return ""


def _normalize_space(text: str) -> str:
    return " ".join(str(text or "").split())


def _extract_pdf_text(path: Path) -> tuple[str, list[str]]:
    warnings: list[str] = []
    text = ""
    if HAS_PYMUPDF:
        try:
            doc = fitz.open(path)
            try:
                text = "\n".join(page.get_text("text").strip() for page in doc).strip()
            finally:
                doc.close()
        except Exception as exc:  # pragma: no cover - fitz exception shape varies
            warnings.append(f"PyMuPDF PDF decode failed: {exc}")
    else:
        warnings.append("PyMuPDF unavailable; trying pypdf/PyPDF2 fallback")
    if not text:
        pypdf_errors: list[str] = []
        for module_name in ("pypdf", "PyPDF2"):
            try:
                module = importlib.import_module(module_name)
                reader = module.PdfReader(str(path))
                page_text = [
                    str(page.extract_text() or "").strip()
                    for page in getattr(reader, "pages", [])
                ]
                text = "\n".join(item for item in page_text if item).strip()
                if text:
                    if module_name != "pypdf":
                        warnings.append(f"PDF decoded with {module_name} fallback")
                    return text[:160_000], warnings
            except Exception as exc:  # pragma: no cover - dependency-specific exceptions vary
                pypdf_errors.append(f"{module_name}: {exc}")
        if pypdf_errors:
            warnings.append("PDF fallback decode failed: " + "; ".join(pypdf_errors))
    if not text:
        warnings.append("PDF decode produced empty text")
    return text[:160_000], warnings


_TITLE_NOISE = (
    "abstract",
    "introduction",
    "references",
    "proceedings of",
    "published as",
    "arxiv:",
    "doi:",
    "http://",
    "https://",
    "copyright",
)


def _guess_title_from_text(text: str, fallback: str) -> str:
    lines = [_normalize_space(raw_line.strip("# ").strip()) for raw_line in text.splitlines()]
    for index, line in enumerate(lines):
        if len(line) < 8:
            continue
        lower = line.lower()
        if any(noise in lower for noise in _TITLE_NOISE):
            continue
        if re.search(r"\b20\d{2}\b", line) and len(line) < 50:
            continue
        pieces = [line]
        for next_line in lines[index + 1:index + 3]:
            next_lower = next_line.lower()
            if len(next_line) < 3 or any(noise in next_lower for noise in _TITLE_NOISE):
                break
            if re.search(r"[\d@∗*]", next_line):
                break
            if len(next_line) <= 48:
                pieces.append(next_line)
                continue
            break
        return " ".join(pieces)[:300]
    return fallback


def _extract_abstract_excerpt(text: str, limit: int = 1200) -> str:
    text = str(text or "")
    if not text.strip():
        return ""
    match = re.search(
        r"(?is)(?:^|\n)\s*(?:abstract|摘要)\s*[:：]?\s*(.+?)(?:\n\s*(?:1\.?|i\.?|introduction|引言|keywords?|关键词)\b|\Z)",
        text,
    )
    if match:
        return _normalize_space(match.group(1))[:limit]
    paragraphs = re.split(r"\n\s*\n", text.strip())
    for paragraph in paragraphs:
        normalized = _normalize_space(paragraph)
        if len(normalized) >= 40:
            return normalized[:limit]
    return _normalize_space(text)[:limit]


def _latex_escape(text: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
    }
    return "".join(replacements.get(ch, ch) for ch in str(text or ""))


def _build_synthetic_tex(title: str, text: str) -> str:
    abstract = _extract_abstract_excerpt(text, limit=1500)
    body = str(text or "").strip() or title or "Untitled"
    return (
        "\\title{" + _latex_escape(title or "Untitled") + "}\n"
        "\\begin{document}\n"
        "\\maketitle\n\n"
        "\\begin{abstract}\n"
        + _latex_escape(abstract or body[:800])
        + "\n\\end{abstract}\n\n"
        "\\section{Recovered Text}\n"
        + _latex_escape(body[:80_000])
        + "\n\\end{document}\n"
    )


def _safe_extract_tar(archive: Path, dest_dir: Path) -> None:
    dest_root = dest_dir.resolve()
    total_size = 0
    with tarfile.open(archive, mode="r:*") as tar:
        members = tar.getmembers()
        for member in members:
            if member.issym() or member.islnk():
                raise ValueError("archive contains link entries")
            target = (dest_root / member.name).resolve()
            if os.path.commonpath([str(dest_root), str(target)]) != str(dest_root):
                raise ValueError(f"archive entry escapes destination: {member.name}")
            total_size += max(member.size, 0)
            if total_size > MAX_SOURCE_ARCHIVE_BYTES:
                raise ValueError("archive exceeds extraction size limit")
        tar.extractall(dest_dir, members=members)


def _safe_extract_zip(archive: Path, dest_dir: Path) -> None:
    dest_root = dest_dir.resolve()
    total_size = 0
    with zipfile.ZipFile(archive) as zf:
        for member in zf.infolist():
            target = (dest_root / member.filename).resolve()
            if os.path.commonpath([str(dest_root), str(target)]) != str(dest_root):
                raise ValueError(f"archive entry escapes destination: {member.filename}")
            total_size += max(member.file_size, 0)
            if total_size > MAX_SOURCE_ARCHIVE_BYTES:
                raise ValueError("archive exceeds extraction size limit")
        zf.extractall(dest_dir)


def _extract_archive(archive: Path, dest_dir: Path) -> list[str]:
    shutil.rmtree(dest_dir, ignore_errors=True)
    dest_dir.mkdir(parents=True, exist_ok=True)
    try:
        if archive.suffix.lower() == ".zip":
            _safe_extract_zip(archive, dest_dir)
        else:
            _safe_extract_tar(archive, dest_dir)
    except (OSError, ValueError, tarfile.TarError, zipfile.BadZipFile) as exc:
        shutil.rmtree(dest_dir, ignore_errors=True)
        return [f"archive extraction failed: {exc}"]
    return []


def _recover_arxiv_id_by_title(title: str, *, timeout: int = 20) -> str:
    if not HAS_REQUESTS or not title or len(title) < 8:
        return ""
    try:
        response = requests.get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            params={
                "query": title,
                "limit": 5,
                "fields": "title,externalIds",
            },
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()
    except Exception:
        return ""
    normalized_title = _normalize_space(title).lower()
    title_tokens = {token for token in re.split(r"[^a-z0-9]+", normalized_title) if len(token) >= 3}
    for item in data.get("data", []):
        candidate_title = _normalize_space(item.get("title", "")).lower()
        arxiv_id = (item.get("externalIds") or {}).get("ArXiv", "")
        if not arxiv_id or not candidate_title:
            continue
        if candidate_title == normalized_title:
            return normalize_arxiv_id(str(arxiv_id))
        candidate_tokens = {token for token in re.split(r"[^a-z0-9]+", candidate_title) if len(token) >= 3}
        if title_tokens and candidate_tokens:
            overlap = len(title_tokens & candidate_tokens)
            if overlap / max(min(len(title_tokens), len(candidate_tokens)), 1) >= 0.8:
                return normalize_arxiv_id(str(arxiv_id))
    return ""


def _download_arxiv_source(arxiv_id: str, dest_dir: Path, *, timeout: int = 30) -> dict[str, Any]:
    if not HAS_REQUESTS:
        return {"success": False, "format": "", "error": "requests unavailable"}
    arxiv_id = normalize_arxiv_id(arxiv_id)
    headers = {"User-Agent": "Solar-AutoSci-paper-prepare/1.0"}
    try:
        response = requests.get(f"https://arxiv.org/e-print/{arxiv_id}", timeout=timeout, headers=headers)
        response.raise_for_status()
    except Exception as exc:
        return {"success": False, "format": "", "error": str(exc)}
    if not response.content:
        return {"success": False, "format": "", "error": "empty response"}

    shutil.rmtree(dest_dir, ignore_errors=True)
    dest_dir.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(suffix=".tar", delete=False) as tmp:
        tmp.write(response.content)
        tmp_path = Path(tmp.name)
    try:
        try:
            _safe_extract_tar(tmp_path, dest_dir)
        except tarfile.TarError:
            try:
                raw = gzip.decompress(response.content)
            except OSError:
                raw = response.content
            if b"\\begin" not in raw and b"\\documentclass" not in raw and b"\\title" not in raw:
                raise
            _write_text(dest_dir / "main.tex", raw.decode("utf-8", errors="ignore"))
        if not any(path.is_file() for path in dest_dir.rglob("*")):
            raise ValueError("source archive extracted no files")
        return {"success": True, "format": "directory", "error": None}
    except Exception as exc:
        shutil.rmtree(dest_dir, ignore_errors=True)
        return {"success": False, "format": "", "error": str(exc)}
    finally:
        tmp_path.unlink(missing_ok=True)


def _find_main_tex(source_dir: Path) -> Path | None:
    tex_files = sorted(source_dir.rglob("*.tex"))
    ranked: list[tuple[tuple[int, int, int, int, int], Path]] = []
    for tex_file in tex_files:
        text = _read_text(tex_file, limit=40_000)
        has_documentclass = int(bool(re.search(r"\\documentclass(?:\[[^\]]*\])?\{", text)))
        has_document = int("\\begin{document}" in text)
        main_name = int(tex_file.stem.lower() in {"main", "paper", "manuscript", "article"})
        has_title = int(bool(re.search(r"\\(?:title|papertitle)\s*\{", text)))
        ranked.append(((has_documentclass, has_document, main_name, has_title, len(text)), tex_file))
    document_roots = [item for item in ranked if item[0][0] or item[0][1]]
    if document_roots:
        return max(document_roots, key=lambda item: (item[0], str(item[1])))[1]
    titled = [item for item in ranked if item[0][3]]
    if titled:
        return max(titled, key=lambda item: (item[0], str(item[1])))[1]
    return tex_files[0] if tex_files else None


_LATEX_INPUT_RE = re.compile(r"\\(?:input|include)\s*\{([^{}]+)\}")


def _read_latex_with_inputs(
    tex_file: Path,
    *,
    source_root: Path,
    seen: set[Path] | None = None,
    depth: int = 0,
) -> str:
    """Read a source tree's main document with bounded, in-root includes expanded.

    arXiv packages commonly keep the abstract and paper body in separate files.
    Parsing only the root file turns ``\\input{abstract}`` into the literal word
    ``abstract`` and silently discards the scientific content used by downstream
    relevance and evidence extraction.
    """

    if depth > 8:
        return ""
    root = source_root.resolve()
    current = tex_file.resolve()
    try:
        current.relative_to(root)
    except ValueError:
        return ""
    visited = seen if seen is not None else set()
    if current in visited or not current.is_file():
        return ""
    visited.add(current)
    text = _read_text(current)

    def expand(match: re.Match[str]) -> str:
        raw = match.group(1).strip()
        if not raw or "\\" in raw:
            return match.group(0)
        candidate = current.parent / raw
        if not candidate.suffix:
            candidate = candidate.with_suffix(".tex")
        try:
            resolved = candidate.resolve()
            resolved.relative_to(root)
        except (OSError, ValueError):
            return match.group(0)
        if not resolved.is_file():
            return match.group(0)
        expanded = _read_latex_with_inputs(
            resolved,
            source_root=root,
            seen=visited,
            depth=depth + 1,
        )
        return f"\n{expanded}\n" if expanded else match.group(0)

    return _LATEX_INPUT_RE.sub(expand, text)[:200_000]


def _strip_latex_comments(text: str) -> str:
    return "\n".join(re.sub(r"(?<!\\)%.*$", "", line) for line in str(text or "").splitlines())


def _extract_braced_after_command(text: str, pattern: str) -> str:
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return ""
    idx = match.end()
    depth = 1
    chars: list[str] = []
    while idx < len(text) and depth > 0:
        ch = text[idx]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        if depth > 0:
            chars.append(ch)
        idx += 1
    return "".join(chars)


def _latex_to_text(text: str) -> str:
    cleaned = _strip_latex_comments(text)
    cleaned = re.sub(r"\\(?:cite|citep|citet|ref|label|url)\*?(?:\[[^\]]*\])?\{[^{}]*\}", " ", cleaned)
    for command in ("emph", "textbf", "textit", "texttt", "mathbf", "mathrm", "mathit"):
        cleaned = re.sub(rf"\\{command}\*?(?:\[[^\]]*\])?\{{([^{{}}]*)\}}", r"\1", cleaned)
    cleaned = re.sub(r"\\(?:begin|end)\{[^{}]*\}", " ", cleaned)
    cleaned = re.sub(r"\\[A-Za-z@]+\*?(?:\[[^\]]*\])?", " ", cleaned)
    cleaned = cleaned.replace("\\\\", " ")
    cleaned = cleaned.replace("~", " ")
    cleaned = cleaned.replace("$", " ")
    cleaned = cleaned.replace("{", " ").replace("}", " ")
    return _normalize_space(cleaned)


def _parse_latex_file(
    tex_file: Path,
    roots: list[Path],
    *,
    source_root: Path | None = None,
) -> dict[str, Any]:
    source_text = _read_latex_with_inputs(
        tex_file,
        source_root=source_root or tex_file.parent,
    )
    clean_source = _strip_latex_comments(source_text)
    fallback_title = tex_file.stem.replace("_", " ").replace("-", " ").strip() or "Untitled"
    raw_title = _extract_braced_after_command(clean_source, r"\\[A-Za-z@]*title[A-Za-z@]*\{")
    title = _latex_to_text(raw_title) or fallback_title
    abstract_match = re.search(r"\\begin\{abstract\}(.+?)\\end\{abstract\}", clean_source, re.DOTALL | re.IGNORECASE)
    abstract = _latex_to_text(abstract_match.group(1))[:1200] if abstract_match else ""
    sections: list[dict[str, str]] = []
    if abstract:
        sections.append({
            "section_id": "abstract",
            "title": "Abstract",
            "text": abstract,
            "source_anchor": f"{tex_file.name}#abstract",
        })
    matches = list(re.finditer(r"\\(?:section|subsection)\*?\{([^{}]+)\}", clean_source))
    for idx, match in enumerate(matches):
        title_text = _latex_to_text(match.group(1)) or f"Section {len(sections) + 1}"
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(clean_source)
        section_id = slugify(title_text)
        sections.append({
            "section_id": section_id,
            "title": title_text,
            "text": _latex_to_text(clean_source[start:end])[:MAX_PARSED_SECTION_CHARS],
            "source_anchor": f"{tex_file.name}#{section_id}",
        })
    if not sections:
        body = _latex_to_text(clean_source)
        sections.append({
            "section_id": "body",
            "title": "Body",
            "text": body[:MAX_PARSED_SECTION_CHARS],
            "source_anchor": f"{tex_file.name}#body",
        })
    return {
        "title": title,
        "abstract": abstract or _extract_abstract_excerpt(" ".join(section.get("text", "") for section in sections)),
        "sections": sections,
        "source_ref": _display_path(tex_file, roots),
    }


def _parse_markdown_file(path: Path, roots: list[Path]) -> dict[str, Any]:
    text = _read_text(path)
    title = path.stem.replace("_", " ").replace("-", " ").strip() or "Untitled"
    for line in text.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            break
    sections: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    body: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if current:
                current["text"] = "\n".join(body).strip()
                sections.append(current)
            heading = line[3:].strip()
            section_id = slugify(heading)
            current = {
                "section_id": section_id,
                "title": heading,
                "source_anchor": f"{path.name}#{section_id}",
            }
            body = []
        elif current:
            body.append(line)
    if current:
        current["text"] = "\n".join(body).strip()
        sections.append(current)
    if not sections:
        sections.append({
            "section_id": "body",
            "title": "Body",
            "text": text.strip(),
            "source_anchor": f"{path.name}#body",
        })
    abstract = next((section.get("text", "") for section in sections if section.get("section_id") == "abstract"), "")
    return {
        "title": title,
        "abstract": abstract or _extract_abstract_excerpt(text),
        "sections": sections,
        "source_ref": _display_path(path, roots),
    }


def _parse_plain_file(path: Path, roots: list[Path]) -> dict[str, Any]:
    text = _read_text(path)
    title = _guess_title_from_text(text, path.stem.replace("_", " ").replace("-", " "))
    return {
        "title": title,
        "abstract": _extract_abstract_excerpt(text),
        "sections": [{
            "section_id": "body",
            "title": "Body",
            "text": text.strip()[:12_000],
            "source_anchor": f"{path.name}#body",
        }],
        "source_ref": _display_path(path, roots),
    }


def _source_type_for(path: Path, source_is_arxiv: bool = False) -> str:
    if source_is_arxiv:
        return "arxiv"
    suffix = path.suffix.lower()
    if path.is_dir() or suffix in {".tex", ".latex"}:
        return "latex"
    if suffix == ".pdf":
        return "pdf"
    if suffix in {".md", ".markdown"}:
        return "markdown"
    if suffix in {".html", ".htm"}:
        return "html"
    return "unknown"


def prepare_paper_source(
    source: str | Path,
    *,
    raw_root: Path,
    workspace_root: Path,
    repository_root: Path | None = None,
    title: str = "",
    arxiv_id: str = "",
    allow_network_fetch: bool = True,
) -> dict[str, Any]:
    roots = [workspace_root]
    if repository_root is not None:
        roots.append(repository_root)
    raw_root = raw_root.resolve()
    raw_tmp = raw_root / "tmp" / "papers"
    raw_tmp.mkdir(parents=True, exist_ok=True)
    source_text = str(source)
    arxiv_doi = ARXIV_DOI_URL_PATTERN.search(source_text)
    if arxiv_doi:
        source_text = (
            "https://arxiv.org/abs/"
            + normalize_arxiv_id(arxiv_doi.group(1))
        )
    source_is_arxiv = bool(ARXIV_URL_PATTERN.search(source_text))
    source_path = _resolve_source(source_text, roots) if not source_is_arxiv else Path(source_text)
    source_display = source_text if source_is_arxiv else _display_path(source_path, roots)
    source_slug = slugify(arxiv_id or title or source_path.name)
    warnings: list[str] = []
    artifacts: list[dict[str, str]] = []
    prepared_path = ""
    canonical_path = source_display
    extracted_text_path = ""
    source_fetch_status = "not_applicable"
    original_format = "arxiv" if source_is_arxiv else (source_path.suffix.lower().lstrip(".") or "directory")

    arxiv_id = normalize_arxiv_id(arxiv_id) or extract_arxiv_id(source_text)
    pdf_text = ""
    if source_is_arxiv:
        source_slug = slugify(arxiv_id or title or "arxiv-paper")
    elif source_path.exists():
        source_slug = slugify(arxiv_id or title or source_path.stem)
    else:
        return {
            "status": "failed",
            "source_path": source_display,
            "canonical_ingest_path": source_display,
            "prepared_path": None,
            "original_format": original_format,
            "ingest_format": "unknown",
            "title": title or "Missing paper source",
            "arxiv_id": arxiv_id,
            "abstract_excerpt": "",
            "warnings": [f"Paper source not found: {source}"],
            "artifacts": artifacts,
        }

    working_entry = source_path
    if not source_is_arxiv and source_path.is_file() and (
        source_path.name.lower().endswith((".tar.gz", ".tgz")) or source_path.suffix.lower() == ".zip"
    ):
        extract_dir = raw_tmp / f"{source_slug}-src"
        warnings.extend(_extract_archive(source_path, extract_dir))
        if extract_dir.exists():
            working_entry = extract_dir
            prepared_path = _display_path(extract_dir, [workspace_root])
            canonical_path = prepared_path
            artifacts.append({"type": "prepared_archive_source", "path": prepared_path})

    if not source_is_arxiv and working_entry.is_dir():
        main_tex = _find_main_tex(working_entry)
        if main_tex is not None:
            canonical_path = _display_path(working_entry, [workspace_root])
            prepared_path = canonical_path if str(working_entry).startswith(str(raw_root)) else ""
        return {
            "status": "completed",
            "source_path": source_display,
            "canonical_ingest_path": canonical_path,
            "prepared_path": prepared_path or None,
            "original_format": original_format,
            "ingest_format": "directory",
            "title": title,
            "arxiv_id": arxiv_id or extract_arxiv_id(source_display),
            "abstract_excerpt": "",
            "warnings": warnings,
            "artifacts": artifacts,
            "source_fetch_status": source_fetch_status,
        }

    candidate_path = working_entry
    if source_is_arxiv:
        candidate_path = Path("")
    elif candidate_path.suffix.lower() == ".pdf":
        pdf_text, pdf_warnings = _extract_pdf_text(candidate_path)
        warnings.extend(pdf_warnings)
        if pdf_text:
            extracted = raw_tmp / f"{source_slug}.txt"
            _write_text(extracted, pdf_text)
            extracted_text_path = _display_path(extracted, [workspace_root])
            artifacts.append({"type": "extracted_pdf_text", "path": extracted_text_path})
        title = _normalize_space(title) or _guess_title_from_text(pdf_text, candidate_path.stem.replace("_", " ").replace("-", " "))
        arxiv_id = arxiv_id or extract_arxiv_id(f"{candidate_path.name} {source_display} {pdf_text[:4000]}")
        if not arxiv_id and title and allow_network_fetch:
            arxiv_id = _recover_arxiv_id_by_title(title)

    if source_is_arxiv:
        title = _normalize_space(title) or arxiv_id or "arXiv paper"

    if (source_is_arxiv or (not source_is_arxiv and candidate_path.suffix.lower() == ".pdf")) and arxiv_id:
        arxiv_dir = raw_tmp / f"{source_slug}-arxiv-src"
        if allow_network_fetch:
            source_result = _download_arxiv_source(arxiv_id, arxiv_dir)
            if source_result.get("success"):
                prepared_path = _display_path(arxiv_dir, [workspace_root])
                canonical_path = prepared_path
                source_fetch_status = "downloaded_source"
                artifacts.append({"type": "arxiv_source", "path": prepared_path})
            else:
                source_fetch_status = "failed"
                warnings.append(f"arXiv source fetch failed for {arxiv_id}: {source_result.get('error') or 'unknown error'}")
        else:
            source_fetch_status = "skipped_network_disabled"
            warnings.append(f"arXiv source fetch skipped for {arxiv_id}: network fetch disabled")

    if not prepared_path and not source_is_arxiv and candidate_path.suffix.lower() == ".pdf":
        if pdf_text:
            synthetic = raw_tmp / f"{source_slug}.tex"
            _write_text(synthetic, _build_synthetic_tex(title, pdf_text))
            prepared_path = _display_path(synthetic, [workspace_root])
            canonical_path = prepared_path
            artifacts.append({"type": "synthetic_latex", "path": prepared_path})
        else:
            warnings.append("PDF source could not be prepared because no text was extracted")

    if not prepared_path and source_is_arxiv:
        warnings.append("arXiv source could not be prepared and no local PDF fallback was available")

    if not source_is_arxiv and candidate_path.suffix.lower() in {".tex", ".latex", ".md", ".markdown", ".html", ".htm", ".txt"}:
        canonical_path = _display_path(candidate_path, roots)

    ingest_path = _resolve_source(canonical_path, roots) if not source_is_arxiv else Path(canonical_path)
    ingest_format = "directory" if ingest_path.is_dir() else ingest_path.suffix.lower().lstrip(".") or "unknown"
    if ingest_format in {"tex", "latex"}:
        ingest_format = "tex"
    return {
        "status": "completed" if canonical_path and (source_is_arxiv or source_path.exists()) else "failed",
        "source_path": source_display,
        "canonical_ingest_path": canonical_path,
        "prepared_path": prepared_path or None,
        "extracted_text_path": extracted_text_path or None,
        "original_format": original_format,
        "ingest_format": ingest_format,
        "title": title,
        "arxiv_id": arxiv_id,
        "abstract_excerpt": _extract_abstract_excerpt(pdf_text),
        "warnings": warnings,
        "artifacts": artifacts,
        "source_fetch_status": source_fetch_status,
    }


def read_paper_source(
    source: str | Path,
    *,
    raw_root: Path,
    workspace_root: Path,
    repository_root: Path | None = None,
    paper_id: str = "",
    title: str = "",
    arxiv_id: str = "",
    allow_network_fetch: bool = True,
    analyzed: bool = False,
) -> dict[str, Any]:
    roots = [workspace_root]
    if repository_root is not None:
        roots.append(repository_root)
    prepared = prepare_paper_source(
        source,
        raw_root=raw_root,
        workspace_root=workspace_root,
        repository_root=repository_root,
        title=title,
        arxiv_id=arxiv_id,
        allow_network_fetch=allow_network_fetch,
    )
    canonical_raw = str(prepared.get("canonical_ingest_path") or prepared.get("source_path") or source)
    canonical = _resolve_source(canonical_raw, roots)
    source_is_arxiv = bool(ARXIV_URL_PATTERN.search(str(source)))
    parsed: dict[str, Any] = {
        "title": prepared.get("title") or "Missing paper source",
        "abstract": prepared.get("abstract_excerpt") or "",
        "sections": [],
        "source_ref": canonical_raw,
    }
    parse_status = "parsed"
    status = "completed"
    limitations = list(prepared.get("warnings") or [])

    if canonical.exists() and canonical.is_dir():
        main_tex = _find_main_tex(canonical)
        if main_tex is not None:
            parsed = _parse_latex_file(main_tex, roots, source_root=canonical)
        else:
            parse_status = "failed"
            status = "failed"
            limitations.append(f"No .tex file found in prepared source directory: {canonical_raw}")
    elif canonical.exists():
        suffix = canonical.suffix.lower()
        if suffix in {".tex", ".latex"}:
            parsed = _parse_latex_file(canonical, roots, source_root=canonical.parent)
        elif suffix in {".md", ".markdown"}:
            parsed = _parse_markdown_file(canonical, roots)
        elif suffix == ".pdf":
            text, warnings = _extract_pdf_text(canonical)
            limitations.extend(warnings)
            if text:
                parsed = {
                    "title": _guess_title_from_text(text, prepared.get("title") or canonical.stem),
                    "abstract": _extract_abstract_excerpt(text),
                    "sections": [{
                        "section_id": "body",
                        "title": "Body",
                        "text": text[:MAX_PARSED_SECTION_CHARS],
                        "source_anchor": f"{canonical.name}#body",
                    }],
                    "source_ref": _display_path(canonical, roots),
                }
                parse_status = "partial"
            else:
                parse_status = "failed"
                status = "failed"
        else:
            parsed = _parse_plain_file(canonical, roots)
    else:
        parse_status = "failed"
        status = "failed"
        limitations.append(f"Canonical paper source not found: {canonical_raw}")

    final_title = str(prepared.get("title") or parsed.get("title") or "Untitled")
    if prepared.get("prepared_path") and not prepared.get("title"):
        final_title = str(parsed.get("title") or final_title)
    identifiers = {"source_prepare_status": str(prepared.get("status") or "unknown")}
    if prepared.get("arxiv_id"):
        identifiers["arxiv"] = str(prepared["arxiv_id"])
    if prepared.get("source_fetch_status"):
        identifiers["source_fetch_status"] = str(prepared["source_fetch_status"])
    raw: dict[str, Any] = {
        "paper_id": paper_id or f"paper-{slugify(final_title)}",
        "title": final_title,
        "source_type": _source_type_for(canonical, source_is_arxiv=source_is_arxiv),
        "source_ref": str(parsed.get("source_ref") or canonical_raw),
        "identifiers": identifiers,
        "abstract": str(parsed.get("abstract") or prepared.get("abstract_excerpt") or ""),
        "parse_status": parse_status,
        "sections": list(parsed.get("sections") or []),
        "status": status,
        "preparation": prepared,
        "artifacts": list(prepared.get("artifacts") or []),
        "limitations": limitations or ["Solar AutoSci prepared the source without warnings."],
    }
    if analyzed:
        raw["analysis"] = {
            "summary": (
                f"Prepared and parsed {final_title} through the Solar AutoSci paper preparation backend "
                "and emitted Solar Evidence ABI paper evidence."
            ),
            "key_concepts": ["paper source preparation", "arXiv source recovery", "Solar Evidence ABI"],
            "evidence_ids": [raw["paper_id"], str(raw["source_ref"])],
        }
    source_contract = _source_contract_for_paper(
        raw,
        canonical=canonical,
        canonical_raw=canonical_raw,
        prepared=prepared,
        limitations=limitations,
    )
    raw["source_contract"] = source_contract
    raw["provenance"] = source_contract["provenance"]
    raw["final_source_registration_boundary"] = _source_registration_boundary(raw, source_contract)
    return raw


def _source_contract_for_paper(
    paper: dict[str, Any],
    *,
    canonical: Path,
    canonical_raw: str,
    prepared: dict[str, Any],
    limitations: list[str],
) -> dict[str, Any]:
    source_id = str(paper.get("paper_id") or f"paper-{slugify(str(paper.get('title') or canonical_raw))}")
    content_hash = stable_hash = ""
    if canonical.exists() and canonical.is_file():
        content_hash = _file_sha256(canonical)
        stable_hash = content_hash
    else:
        stable_hash = hashlib.sha256(json.dumps({
            "source_id": source_id,
            "source_ref": paper.get("source_ref"),
            "title": paper.get("title"),
            "sections": paper.get("sections"),
        }, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    evidence_ids = [
        source_id,
        str(paper.get("source_ref") or canonical_raw),
        *[
            str(section.get("source_anchor"))
            for section in paper.get("sections") or []
            if isinstance(section, dict) and str(section.get("source_anchor") or "").strip()
        ],
    ]
    return {
        "schema": "autosci_seed_source_contract.v1",
        "source_id": source_id,
        "seed_kind": str(paper.get("source_type") or prepared.get("original_format") or "unknown"),
        "source_kind": str(paper.get("source_type") or "unknown"),
        "source_ref": str(paper.get("source_ref") or canonical_raw),
        "canonical_path": canonical_raw,
        "content_sha256": stable_hash,
        "raw_file_sha256": content_hash,
        "title": str(paper.get("title") or ""),
        "parse_status": str(paper.get("parse_status") or "unknown"),
        "content_proof": {
            "abstract_present": bool(str(paper.get("abstract") or "").strip()),
            "section_count": len([section for section in paper.get("sections") or [] if isinstance(section, dict)]),
            "non_empty_section_count": len([
                section
                for section in paper.get("sections") or []
                if isinstance(section, dict) and str(section.get("text") or "").strip()
            ]),
        },
        "provenance": {
            "provider": "local_paper_prepare",
            "source_prepare_status": str((paper.get("identifiers") or {}).get("source_prepare_status") or "unknown"),
            "source_fetch_status": str((paper.get("identifiers") or {}).get("source_fetch_status") or "not_applicable"),
            "prepared_path": prepared.get("prepared_path"),
            "extracted_text_path": prepared.get("extracted_text_path"),
            "artifacts": list(prepared.get("artifacts") or []),
        },
        "limitations": list(dict.fromkeys(str(item) for item in limitations if str(item).strip())),
        "evidence_ids": list(dict.fromkeys(evidence_ids)),
    }


def _source_registration_boundary(paper: dict[str, Any], source_contract: dict[str, Any]) -> dict[str, Any]:
    proof = source_contract.get("content_proof") if isinstance(source_contract.get("content_proof"), dict) else {}
    source_preparation_verified = str((paper.get("identifiers") or {}).get("source_prepare_status") or "") == "completed"
    parse_quality_ready = (
        str(paper.get("parse_status") or "") in {"parsed", "partial"}
        and int(proof.get("non_empty_section_count") or 0) > 0
    )
    source_contract_ready = (
        bool(source_contract.get("source_id"))
        and bool(source_contract.get("source_ref"))
        and bool(source_contract.get("content_sha256"))
    )
    memory_sidecar_ready = True
    graph_sidecar_ready = True
    wiki_registration_ready = source_contract_ready and parse_quality_ready
    checks = {
        "source_preparation_verified": source_preparation_verified,
        "parse_quality_ready": parse_quality_ready,
        "source_contract_ready": source_contract_ready,
        "wiki_registration_ready": wiki_registration_ready,
        "memory_sidecar_ready": memory_sidecar_ready,
        "graph_sidecar_ready": graph_sidecar_ready,
    }
    missing = [key for key, value in checks.items() if not value]
    return {
        "schema": "autosci_source_registration_boundary.v1",
        "paper_id": str(paper.get("paper_id") or ""),
        "source_contract": source_contract,
        "sidecar_evidence_paths": [],
        "final_registration_ready": not missing,
        "missing": missing,
        **checks,
    }


def dump_prepare_manifest(path: Path, prepared: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(prepared, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
