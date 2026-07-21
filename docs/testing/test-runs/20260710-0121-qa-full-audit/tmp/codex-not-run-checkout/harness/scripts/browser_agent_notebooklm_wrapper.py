#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "lib"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

import browser_job_runtime as bjrt
from browser_use.browser.profile import BrowserProfile
from browser_use.browser.session import BrowserSession
from playwright.async_api import async_playwright


DEFAULT_URL = "https://notebooklm.google.com/?pli=1"
DEFAULT_USER_DATA_DIR = Path.home() / "Library" / "Application Support" / "Google" / "Chrome"
DEFAULT_PROFILE_DIRECTORY = "Default"
DEFAULT_ALLOWED_DOMAINS = [
    "notebooklm.google.com",
    "accounts.google.com",
    "google.com",
    "google.ca",
]

CAPTURE_JS = r"""() => {
  const clean = (value) => String(value || "")
    .replace(/\u00a0/g, " ")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
  const body = clean(document.body && (document.body.innerText || document.body.textContent || ""));
  const match = body.match(/(\d+)\s*个来源/);
  const notebookTitle = document.querySelector(".title-input, input.title-input, .title-label-inner")?.value
    || document.querySelector(".title-label-inner")?.innerText
    || document.querySelector(".title-label")?.innerText
    || document.title || "";
  return JSON.stringify({
    title: document.title || "",
    url: location.href,
    notebook_title: clean(notebookTitle),
    body,
    source_count: match ? Number(match[1]) : 0,
  });
}"""

CLICK_TEXT_JS = r"""(targetText) => {
  const clean = (value) => String(value || "").replace(/\s+/g, " ").trim();
  const visible = (el) => {
    if (!el) return false;
    const rect = el.getBoundingClientRect();
    const style = window.getComputedStyle(el);
    return rect.width > 0 && rect.height > 0 && style.visibility !== "hidden" && style.display !== "none";
  };
  const wanted = clean(targetText);
  const nodes = Array.from(document.querySelectorAll("button,a,div,[role='button'],[role='menuitem'],span"));
  let node = nodes.find((el) => {
    if (!visible(el)) return false;
    const text = clean(el.innerText || el.textContent || "");
    const aria = clean(el.getAttribute("aria-label") || "");
    return text === wanted || aria === wanted;
  });
  if (!node) {
    node = nodes.find((el) => {
      if (!visible(el)) return false;
      const text = clean(el.innerText || el.textContent || "");
      const aria = clean(el.getAttribute("aria-label") || "");
      return text.includes(wanted) || aria.includes(wanted);
    });
  }
  if (!node) {
    return JSON.stringify({ ok: false, error: "not_found", targetText: wanted });
  }
  node.click();
  return JSON.stringify({ ok: true, targetText: wanted, text: clean(node.innerText || node.textContent || "") });
}"""

CLICK_NOTEBOOK_BY_NAME_JS = r"""(targetName) => {
  const clean = (value) => String(value || "").replace(/\s+/g, " ").trim();
  const visible = (el) => {
    if (!el) return false;
    const rect = el.getBoundingClientRect();
    const style = window.getComputedStyle(el);
    return rect.width > 0 && rect.height > 0 && style.visibility !== "hidden" && style.display !== "none";
  };
  const wanted = clean(targetName);
  const nodes = Array.from(document.querySelectorAll("a,div,span,[role='button']"));
  let node = nodes.find((el) => visible(el) && clean(el.innerText || el.textContent || "") === wanted);
  if (!node) {
    node = nodes.find((el) => visible(el) && clean(el.innerText || el.textContent || "").includes(wanted));
  }
  if (!node) {
    return JSON.stringify({ ok: false, error: "not_found", notebook_name: wanted });
  }
  node.click();
  return JSON.stringify({ ok: true, notebook_name: wanted, text: clean(node.innerText || node.textContent || "") });
}"""

SET_TEXTAREA_JS = r"""(payload) => {
  const clean = (value) => String(value || "").replace(/\s+/g, " ").trim();
  const selectors = [
    "textarea[aria-label*='粘贴']",
    "textarea[placeholder*='粘贴']",
    "textarea.copied-text-input-textarea",
    "textarea[aria-label*='文字']",
    "textarea",
    "input[type='text']",
    "div[contenteditable='true'][role='textbox']",
    "[role='textbox'][contenteditable='true']",
  ];
  const visible = (el) => {
    if (!el) return false;
    const rect = el.getBoundingClientRect();
    const style = window.getComputedStyle(el);
    return rect.width > 0 && rect.height > 0 && style.visibility !== "hidden" && style.display !== "none";
  };
  for (const selector of selectors) {
    const nodes = Array.from(document.querySelectorAll(selector)).filter(visible);
    for (const node of nodes) {
      const text = String(payload || "");
      node.focus();
      if (node.tagName === "TEXTAREA" || node.tagName === "INPUT") {
        node.value = text;
        node.dispatchEvent(new Event("input", { bubbles: true }));
        node.dispatchEvent(new Event("change", { bubbles: true }));
        return JSON.stringify({
          ok: true,
          selector,
          mode: node.tagName.toLowerCase(),
          aria: clean(node.getAttribute("aria-label") || ""),
          placeholder: clean(node.getAttribute("placeholder") || ""),
          id: clean(node.id || ""),
        });
      }
      node.innerHTML = "";
      node.textContent = text;
      node.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: text }));
      return JSON.stringify({ ok: true, selector, mode: "contenteditable" });
    }
  }
  return JSON.stringify({ ok: false, error: "textarea_not_found" });
}"""

LIST_TEXT_INPUTS_JS = r"""() => {
  const clean = (value) => String(value || "").replace(/\s+/g, " ").trim();
  const visible = (el) => {
    if (!el) return false;
    const rect = el.getBoundingClientRect();
    const style = window.getComputedStyle(el);
    return rect.width > 0 && rect.height > 0 && style.visibility !== "hidden" && style.display !== "none";
  };
  const nodes = Array.from(document.querySelectorAll("textarea,input,[contenteditable='true'],[role='textbox']"));
  return JSON.stringify(nodes.filter(visible).map((node) => ({
    tag: (node.tagName || "").toLowerCase(),
    type: clean(node.getAttribute("type") || ""),
    id: clean(node.id || ""),
    cls: clean(node.className || ""),
    role: clean(node.getAttribute("role") || ""),
    aria: clean(node.getAttribute("aria-label") || ""),
    placeholder: clean(node.getAttribute("placeholder") || ""),
    text: clean(node.innerText || node.textContent || ""),
  })));
}"""

MODAL_STATE_JS = r"""() => {
  const clean = (value) => String(value || "").replace(/\s+/g, " ").trim();
  const body = clean(document.body && (document.body.innerText || document.body.textContent || ""));
  const modalOpen = body.includes("粘贴复制的文字") && body.includes("在下方粘贴复制的文字");
  const buttons = Array.from(document.querySelectorAll("button,[role='button']")).map((node) => ({
    text: clean(node.innerText || node.textContent || ""),
    aria: clean(node.getAttribute("aria-label") || ""),
    disabled: !!node.disabled || node.getAttribute("aria-disabled") === "true",
  }));
  const insert = buttons.find((item) => item.text === "插入" || item.aria === "插入") || {};
  return JSON.stringify({
    modal_open: modalOpen,
    insert_disabled: !!insert.disabled,
    insert_text: insert.text || insert.aria || "",
  });
}"""

SOURCE_ACTION_BUTTONS_JS = r"""() => {
  const clean = (value) => String(value || "").replace(/\s+/g, " ").trim();
  const visible = (el) => {
    if (!el) return false;
    const rect = el.getBoundingClientRect();
    const style = window.getComputedStyle(el);
    return rect.width > 0 && rect.height > 0 && style.visibility !== "hidden" && style.display !== "none";
  };
  const wanted = ["上传文件", "网站", "云端硬盘", "复制的文字"];
  const nodes = Array.from(document.querySelectorAll("button,[role='button'],div,span"));
  const rows = [];
  for (const node of nodes) {
    if (!visible(node)) continue;
    const text = clean(node.innerText || node.textContent || "");
    if (!wanted.includes(text)) continue;
    const rect = node.getBoundingClientRect();
    rows.push({
      text,
      aria: clean(node.getAttribute("aria-label") || ""),
      disabled: !!node.disabled || node.getAttribute("aria-disabled") === "true",
      x: Math.round(rect.x),
      y: Math.round(rect.y),
      w: Math.round(rect.width),
      h: Math.round(rect.height),
    });
  }
  rows.sort((a, b) => (a.y - b.y) || (a.x - b.x));
  return JSON.stringify(rows);
}"""

FILE_INPUTS_DEEP_JS = r"""() => {
  const clean = (value) => String(value || "").replace(/\s+/g, " ").trim();
  const visible = (el) => {
    if (!el) return false;
    const rect = el.getBoundingClientRect();
    const style = window.getComputedStyle(el);
    return rect.width > 0 && rect.height > 0 && style.visibility !== "hidden" && style.display !== "none";
  };
  const out = [];
  const walk = (root, path) => {
    if (!root) return;
    const inputs = root.querySelectorAll ? root.querySelectorAll("input[type='file'], input[accept]") : [];
    for (const node of inputs) {
      const rect = node.getBoundingClientRect ? node.getBoundingClientRect() : {x:0,y:0,width:0,height:0};
      out.push({
        path,
        tag: (node.tagName || "").toLowerCase(),
        type: clean(node.getAttribute("type") || ""),
        accept: clean(node.getAttribute("accept") || ""),
        multiple: !!node.multiple,
        visible: visible(node),
        x: Math.round(rect.x || 0),
        y: Math.round(rect.y || 0),
        w: Math.round(rect.width || 0),
        h: Math.round(rect.height || 0),
      });
    }
    const all = root.querySelectorAll ? root.querySelectorAll("*") : [];
    for (const el of all) {
      if (el.shadowRoot) walk(el.shadowRoot, path + " > " + ((el.tagName || "").toLowerCase()));
    }
  };
  walk(document, "document");
  return JSON.stringify(out);
}"""

SET_NOTEBOOK_TITLE_JS = r"""(targetTitle) => {
  const text = String(targetTitle || "").trim();
  const node = document.querySelector(".title-input, input.title-input");
  if (!node) return JSON.stringify({ ok: false, error: "title_input_not_found" });
  node.focus();
  node.value = text;
  node.dispatchEvent(new Event("input", { bubbles: true }));
  node.dispatchEvent(new Event("change", { bubbles: true }));
  return JSON.stringify({ ok: true, title: text });
}"""


def _quiet_browser_logs() -> None:
    logging.getLogger().setLevel(logging.ERROR)
    for name in (
        "BrowserSession",
        "cdp_use.client",
        "browser_use",
        "browser_use.browser.session",
        "browser_use.browser.profile",
    ):
        logging.getLogger(name).setLevel(logging.ERROR)


def _request_dir() -> Path:
    out = Path(os.environ.get("BROWSER_AGENT_REQUEST_DIR") or f"/tmp/notebooklm-wrapper-{int(time.time())}").expanduser()
    out.mkdir(parents=True, exist_ok=True)
    return out


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _mark_progress(request_dir: Path, step: str, **extra: object) -> None:
    payload = {"step": step, "ts": bjrt._now(), **extra}
    _write_json(request_dir / "progress.json", payload)


def _read_request() -> dict:
    raw = sys.stdin.read()
    if not raw.strip():
        raise SystemExit("stdin request is empty")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise SystemExit("stdin request must be JSON object")
    return payload


async def _capture(page) -> dict:
    return json.loads(await page.evaluate(CAPTURE_JS))


async def _click_text(page, target: str) -> dict:
    return json.loads(await page.evaluate(CLICK_TEXT_JS, target))


async def _click_notebook(page, notebook_name: str) -> dict:
    return json.loads(await page.evaluate(CLICK_NOTEBOOK_BY_NAME_JS, notebook_name))


async def _set_textbox(page, text: str) -> dict:
    return json.loads(await page.evaluate(SET_TEXTAREA_JS, text))


async def _list_text_inputs(page) -> list[dict]:
    return json.loads(await page.evaluate(LIST_TEXT_INPUTS_JS))


async def _set_notebook_title(page, title: str) -> dict:
    return json.loads(await page.evaluate(SET_NOTEBOOK_TITLE_JS, title))


async def _modal_state(page) -> dict:
    return json.loads(await page.evaluate(MODAL_STATE_JS))


async def _source_action_buttons(page) -> list[dict]:
    return json.loads(await page.evaluate(SOURCE_ACTION_BUTTONS_JS))


async def _file_inputs_deep(page) -> list[dict]:
    return json.loads(await page.evaluate(FILE_INPUTS_DEEP_JS))


async def _wait_for_source_count(page, minimum: int, timeout_s: int = 120) -> dict:
    deadline = time.time() + timeout_s
    last = {}
    while time.time() < deadline:
        last = await _capture(page)
        if int(last.get("source_count") or 0) >= minimum:
            return last
        await asyncio.sleep(2)
    return last


async def _upload_local_files(
    page,
    files: list[str],
    request_dir: Path | None = None,
    allow_text_fallback: bool = False,
    playwright_page=None,
) -> dict:
    if not files:
        return {"ok": True, "mode": "noop", "count": 0}
    current = await _capture(page)
    current_body = str(current.get("body") or "")
    source_modal_open = all(
        marker in current_body for marker in ("上传文件", "网站", "云端硬盘", "复制的文字")
    )
    clicked = {"ok": True, "skipped": True, "reason": "source_modal_already_open"} if source_modal_open else await _click_text(page, "添加来源")
    await asyncio.sleep(1.2)
    if playwright_page is None:
        playwright_page = getattr(page, "_page", None)
    upload_button = {"ok": False, "error": "not_attempted"}
    if request_dir is not None:
        try:
            _write_json(request_dir / "source-action-buttons.json", await _source_action_buttons(page))
        except Exception:
            pass
    if playwright_page is not None:
        source_buttons = []
        try:
            source_buttons = await _source_action_buttons(page)
        except Exception:
            source_buttons = []
        upload_candidates = []
        if source_buttons:
            upload_candidates = [item for item in source_buttons if item.get("text") == "上传文件"]
            upload_candidates.sort(key=lambda item: (int(item.get("y") or 0), int(item.get("x") or 0)))
        for item in upload_candidates:
            try:
                cx = int(item.get("x") or 0) + max(4, int(item.get("w") or 0) // 2)
                cy = int(item.get("y") or 0) + max(4, int(item.get("h") or 0) // 2)
                async with playwright_page.expect_file_chooser(timeout=2500) as chooser_info:
                    await playwright_page.mouse.click(cx, cy)
                chooser = await chooser_info.value
                await chooser.set_files(files)
                await asyncio.sleep(1.5)
                return {
                    "ok": True,
                    "mode": "file_chooser_coordinates",
                    "count": len(files),
                    "open_source_click": clicked,
                    "upload_button": {"ok": True, "coordinates": {"x": cx, "y": cy}, "source": item},
                }
            except Exception:
                continue
        for selector in (
            "button:has-text('上传文件')",
            "[role='button']:has-text('上传文件')",
            "text=上传文件",
        ):
            try:
                async with playwright_page.expect_file_chooser(timeout=2500) as chooser_info:
                    await playwright_page.locator(selector).first.click(timeout=2000)
                chooser = await chooser_info.value
                await chooser.set_files(files)
                await asyncio.sleep(1.5)
                return {
                    "ok": True,
                    "mode": "file_chooser",
                    "count": len(files),
                    "open_source_click": clicked,
                    "upload_button": {"ok": True, "selector": selector},
                }
            except Exception:
                continue
        upload_button = await _click_text(page, "上传文件")
        await asyncio.sleep(0.5)
        if request_dir is not None:
            try:
                _write_json(request_dir / "file-inputs-after-upload-click.json", await _file_inputs_deep(page))
            except Exception:
                pass
        try:
            async with playwright_page.expect_file_chooser(timeout=2000) as chooser_info:
                await playwright_page.get_by_text("上传文件", exact=False).click()
            chooser = await chooser_info.value
            await chooser.set_files(files)
            await asyncio.sleep(1.5)
            return {"ok": True, "mode": "file_chooser", "count": len(files), "open_source_click": clicked, "upload_button": upload_button}
        except Exception:
            pass
        for selector in ("input[type='file']", "input[accept]", "input[type='file'][multiple]"):
            locator = playwright_page.locator(selector)
            count = await locator.count()
            if count:
                await locator.first.set_input_files(files)
                await asyncio.sleep(1.5)
                return {
                    "ok": True,
                    "mode": "playwright_locator",
                    "count": len(files),
                    "open_source_click": clicked,
                    "upload_button": upload_button,
                    "selector": selector,
                }
        try:
            async with playwright_page.expect_file_chooser(timeout=15000) as chooser_info:
                await playwright_page.get_by_text("上传文件", exact=True).first.click(timeout=10000)
            chooser = await chooser_info.value
            await chooser.set_files(files)
            await asyncio.sleep(2.0)
            return {
                "ok": True,
                "mode": "playwright_cdp_file_chooser",
                "count": len(files),
                "open_source_click": clicked,
                "upload_button": {"ok": True, "selector": "get_by_text(exact=True)"},
            }
        except Exception as exc:
            upload_button = {
                "ok": False,
                "error": "playwright_cdp_file_chooser_failed",
                "detail": repr(exc),
            }
    else:
        upload_button = await _click_text(page, "上传文件")
        await asyncio.sleep(0.5)
    inputs = []
    try:
        inputs = await page.get_elements_by_css_selector("input[type='file']")
    except Exception:
        inputs = []
    for item in inputs:
        setter = getattr(item, "set_input_files", None)
        if setter:
            maybe = setter(files)
            if asyncio.iscoroutine(maybe):
                await maybe
            await asyncio.sleep(1.5)
            return {"ok": True, "mode": "element_set_input_files", "count": len(files), "open_source_click": clicked, "upload_button": upload_button}
    text_button = {"ok": False, "skipped": True, "reason": "text_fallback_disabled"}
    if allow_text_fallback:
        text_button = await _click_text(page, "复制的文字")
    if allow_text_fallback and text_button.get("ok"):
        await asyncio.sleep(0.8)
        if request_dir is not None:
            _write_json(request_dir / "copied-text-page.json", await _capture(page))
            try:
                _write_json(request_dir / "copied-text-inputs.json", await _list_text_inputs(page))
                _write_json(request_dir / "copied-text-modal-state.json", await _modal_state(page))
            except Exception:
                pass
        pasted_parts = []
        for path in files:
            try:
                pasted_parts.append(Path(path).read_text(encoding="utf-8", errors="replace"))
            except Exception:
                continue
        pasted_text = "\n\n".join(part.strip() for part in pasted_parts if part.strip())[:180000]
        if pasted_text:
            fill = {"ok": False}
            playwright_fill = {"ok": False}
            playwright_submit = {"ok": False}
            if playwright_page is not None:
                preferred = playwright_page.locator("#mat-input-2")
                try:
                    if await preferred.count():
                        await preferred.first.click(timeout=1500)
                        await preferred.first.fill(pasted_text, timeout=5000)
                        playwright_fill = {"ok": True, "selector": "#mat-input-2", "mode": "playwright_fill"}
                except Exception:
                    playwright_fill = {"ok": False}
            if not playwright_fill.get("ok"):
                fill = await _set_textbox(page, pasted_text)
            if (not fill.get("ok")) and (not playwright_fill.get("ok")) and playwright_page is not None:
                selectors = [
                    "#mat-input-2",
                    "textarea[aria-label*='文字']",
                    "textarea[placeholder*='粘贴']",
                    "textarea",
                    "input[aria-label*='文字']",
                    "input[placeholder*='粘贴']",
                    "div[contenteditable='true'][role='textbox']",
                    "[role='textbox'][contenteditable='true']",
                ]
                for selector in selectors:
                    locator = playwright_page.locator(selector)
                    try:
                        count = await locator.count()
                    except Exception:
                        count = 0
                    if not count:
                        continue
                    try:
                        await locator.first.click(timeout=1500)
                        await locator.first.fill(pasted_text, timeout=2500)
                        playwright_fill = {"ok": True, "selector": selector}
                        break
                    except Exception:
                        try:
                            await locator.first.evaluate(
                                """(node, value) => {
                                  node.focus();
                                  if ('value' in node) {
                                    node.value = value;
                                    node.dispatchEvent(new Event('input', { bubbles: true }));
                                    node.dispatchEvent(new Event('change', { bubbles: true }));
                                  } else {
                                    node.textContent = value;
                                    node.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: value }));
                                  }
                                }""",
                                pasted_text,
                            )
                            playwright_fill = {"ok": True, "selector": selector, "mode": "evaluate"}
                            break
                        except Exception:
                            continue
            await asyncio.sleep(0.6)
            modal_state_before_insert = await _modal_state(page)
            if playwright_page is not None and not modal_state_before_insert.get("insert_disabled"):
                for selector in (
                    "button:has-text('插入')",
                    "[role='button']:has-text('插入')",
                    "button:has-text('添加')",
                    "button:has-text('保存')",
                ):
                    locator = playwright_page.locator(selector)
                    try:
                        count = await locator.count()
                    except Exception:
                        count = 0
                    if not count:
                        continue
                    try:
                        await locator.first.click(timeout=1500)
                        playwright_submit = {"ok": True, "selector": selector}
                        break
                    except Exception:
                        continue
            await asyncio.sleep(0.6)
            insert = {"ok": False}
            if modal_state_before_insert.get("insert_disabled"):
                insert = {"ok": False, "error": "insert_disabled"}
            else:
                for label in ("插入", "添加", "保存"):
                    insert = await _click_text(page, label)
                    if insert.get("ok"):
                        break
            await asyncio.sleep(1.5)
            if request_dir is not None:
                try:
                    _write_json(request_dir / "copied-text-post-fill-page.json", await _capture(page))
                    _write_json(request_dir / "copied-text-post-fill-modal-state.json", await _modal_state(page))
                except Exception:
                    pass
            fill_ok = fill.get("ok") or playwright_fill.get("ok")
            insert_ok = insert.get("ok") or playwright_submit.get("ok")
            if fill_ok and insert_ok:
                return {
                    "ok": True,
                    "mode": "copied_text",
                    "count": len(files),
                    "chars": len(pasted_text),
                    "open_source_click": clicked,
                    "upload_button": upload_button,
                    "text_button": text_button,
                    "fill_result": fill,
                    "playwright_fill": playwright_fill,
                    "insert_button": insert,
                    "playwright_submit": playwright_submit,
                }
    return {
        "ok": False,
        "error": "upload_file_only_mode_failed" if not allow_text_fallback else "file_input_not_found",
        "open_source_click": clicked,
        "upload_button": upload_button,
        "text_button": text_button if 'text_button' in locals() else {"ok": False},
        "copied_text_inputs_path": str(request_dir / "copied-text-inputs.json") if request_dir is not None else "",
        "fill_result": fill if 'fill' in locals() else {"ok": False},
        "playwright_fill": playwright_fill if 'playwright_fill' in locals() else {"ok": False},
        "insert_button": insert if 'insert' in locals() else {"ok": False},
        "playwright_submit": playwright_submit if 'playwright_submit' in locals() else {"ok": False},
        "allow_text_fallback": allow_text_fallback,
    }


async def _ensure_notebook(page, notebook_name: str) -> dict:
    opened = await _click_notebook(page, notebook_name)
    if opened.get("ok"):
        await asyncio.sleep(2.0)
        current = await _capture(page)
        current_url = str(current.get("url") or "")
        body = str(current.get("body") or "")
        if "/notebook/" in current_url or "添加来源" in body or "Studio 输出将保存在此处" in body:
            return {"ok": True, "mode": "existing", **current}
    create = {"ok": False}
    for label in ("创建笔记本", "创建新笔记本", "新建笔记本", "新建"):
        create = await _click_text(page, label)
        if create.get("ok"):
            break
    if not create.get("ok"):
        return {"ok": False, "error": "create_notebook_button_not_found"}
    await asyncio.sleep(3.0)
    title_result = await _set_notebook_title(page, notebook_name)
    await asyncio.sleep(1.0)
    current = await _capture(page)
    return {"ok": True, "mode": "created", "title_result": title_result, **current}


async def _generate_artifact(page, artifact_label: str, title: str, prompt_text: str | None,
                             output_path: Path) -> dict:
    click = await _click_text(page, artifact_label)
    await asyncio.sleep(1.2)
    prompt_used = False
    if prompt_text:
        filled = await _set_textbox(page, prompt_text)
        prompt_used = bool(filled.get("ok"))
        await asyncio.sleep(0.6)
    generate = await _click_text(page, "生成")
    await asyncio.sleep(4.0)
    final = await _capture(page)
    screenshot_b64 = await page.screenshot(format="png")
    output_path.write_bytes(base64.b64decode(screenshot_b64))
    body = str(final.get("body") or "")
    ready = title in body or (artifact_label in body and "正在生成" not in body)
    return {
        "ok": True,
        "label": artifact_label,
        "title": title,
        "prompt_text": prompt_text or "",
        "prompt_used": prompt_used,
        "click_result": click,
        "generate_result": generate,
        "status": "ready" if ready else "pending",
        "image_path": str(output_path),
    }


async def _run(payload: dict) -> int:
    request_dir = _request_dir()
    notebook_name = str(payload.get("notebook_name") or "").strip() or "AI Influence"
    output_dir = Path(str(payload.get("output_dir") or request_dir)).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    profile_directory = str(os.environ.get("BROWSER_AGENT_NOTEBOOKLM_PROFILE_DIRECTORY") or DEFAULT_PROFILE_DIRECTORY)
    user_data_dir = Path(os.environ.get("BROWSER_AGENT_NOTEBOOKLM_USER_DATA_DIR") or str(DEFAULT_USER_DATA_DIR)).expanduser()
    target_url = str(os.environ.get("BROWSER_AGENT_NOTEBOOKLM_URL") or DEFAULT_URL)
    timeout_s = int(os.environ.get("BROWSER_AGENT_NOTEBOOKLM_TIMEOUT") or "1800")

    staged_dir, cleanup_dir = bjrt._stage_browser_profile(user_data_dir, profile_directory)
    if user_data_dir and not staged_dir:
        raise RuntimeError("protected_browser_profile_cache_missing")

    meta = {
        "provider": "browser_agent_notebooklm",
        "notebook_name": notebook_name,
        "profile_directory": profile_directory,
        "target_url": target_url,
        "source_files": payload.get("source_files") or [],
        "started_at": bjrt._now(),
    }
    _write_json(request_dir / "wrapper-meta.json", meta)
    _mark_progress(request_dir, "wrapper_started", notebook_name=notebook_name)

    browser = BrowserSession(
        browser_profile=BrowserProfile(
            headless=str(os.environ.get("BROWSER_AGENT_HEADLESS") or "false").strip().lower() in {"1", "true", "yes", "on"},
            user_data_dir=staged_dir,
            profile_directory=profile_directory,
            allowed_domains=DEFAULT_ALLOWED_DOMAINS,
        )
    )
    try:
        _mark_progress(request_dir, "browser_starting")
        await asyncio.wait_for(browser.start(), timeout=40)
        _mark_progress(request_dir, "browser_started")
        page = await asyncio.wait_for(browser.get_current_page(), timeout=15)
        if page is None:
            page = await asyncio.wait_for(browser.new_page(), timeout=15)
        _mark_progress(request_dir, "page_ready")
        try:
            await asyncio.wait_for(page.goto(target_url), timeout=30)
        except Exception:
            await asyncio.wait_for(page.navigate(target_url), timeout=30)
        await asyncio.sleep(3.0)
        _mark_progress(request_dir, "page_loaded", url=target_url)
        notebook_state = await _ensure_notebook(page, notebook_name)
        _write_json(request_dir / "notebook-state.json", notebook_state)
        _mark_progress(request_dir, "notebook_ensured", mode=notebook_state.get("mode"))
        initial = await _capture(page)
        _write_json(request_dir / "initial-page.json", initial)
        allow_text_fallback = bool(payload.get("allow_text_fallback")) or (
            str(os.environ.get("BROWSER_AGENT_NOTEBOOKLM_ALLOW_TEXT_FALLBACK") or "false").strip().lower()
            in {"1", "true", "yes", "on"}
        )
        async with async_playwright() as pw:
            playwright_page = None
            try:
                pw_browser = await pw.chromium.connect_over_cdp(browser.cdp_url)
                pw_context = pw_browser.contexts[0] if pw_browser.contexts else None
                if pw_context is not None:
                    if pw_context.pages:
                        playwright_page = pw_context.pages[0]
                    else:
                        playwright_page = await pw_context.new_page()
                    await playwright_page.goto(str(initial.get("url") or target_url), wait_until="domcontentloaded")
                    await playwright_page.wait_for_timeout(2000)
            except Exception as exc:
                _write_json(request_dir / "playwright-cdp-connect.json", {"ok": False, "error": repr(exc)})
                playwright_page = None
            else:
                _write_json(
                    request_dir / "playwright-cdp-connect.json",
                    {"ok": True, "url": playwright_page.url if playwright_page is not None else ""},
                )
            upload_result = await _upload_local_files(
                page,
                [str(Path(p).expanduser()) for p in (payload.get("source_files") or [])],
                request_dir=request_dir,
                allow_text_fallback=allow_text_fallback,
                playwright_page=playwright_page,
            )
        _write_json(request_dir / "upload-result.json", upload_result)
        _mark_progress(request_dir, "sources_uploaded", upload_ok=upload_result.get("ok"))
        final_sources = await _wait_for_source_count(page, max(1, int(initial.get("source_count") or 0) + 1), timeout_s=120)
        _write_json(request_dir / "final-sources.json", final_sources)
        _mark_progress(request_dir, "sources_ready", source_count=final_sources.get("source_count"))
        source_summary = ""
        body = str(final_sources.get("body") or "")
        if body:
            source_summary = body[:1200]

        mindmap_spec = payload.get("mindmap") or {}
        mindmap_result = {}
        if mindmap_spec.get("enabled"):
            _mark_progress(request_dir, "mindmap_generating")
            mindmap_result = await _generate_artifact(
                page,
                "思维导图",
                str(mindmap_spec.get("title") or "思维导图"),
                str(mindmap_spec.get("prompt_text") or ""),
                output_dir / "mindmap.png",
            )
            _write_json(request_dir / "mindmap-result.json", mindmap_result)
            _mark_progress(request_dir, "mindmap_done", status=mindmap_result.get("status"))

        infographics = []
        for slot in payload.get("infographics") or []:
            if not isinstance(slot, dict):
                continue
            _mark_progress(request_dir, "infographic_generating", figure_id=slot.get("figure_id"))
            result = await _generate_artifact(
                page,
                "信息图",
                str(slot.get("title") or "信息图"),
                str(slot.get("prompt_text") or ""),
                output_dir / f"{slugify(str(slot.get('figure_id') or slot.get('title') or 'figure'))[:80]}.png",
            )
            result.update({
                "figure_id": slot.get("figure_id"),
                "placement_section": slot.get("placement_section"),
                "placement_heading": slot.get("placement_heading"),
                "material_video_refs": slot.get("material_video_refs") or [],
            })
            infographics.append(result)
            _mark_progress(request_dir, "infographic_done", figure_id=slot.get("figure_id"), status=result.get("status"))

        final = await _capture(page)
        _mark_progress(request_dir, "final_capture")
        screenshot_b64 = await page.screenshot(format="png")
        (request_dir / "page.json").write_text(json.dumps(final, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if screenshot_b64:
            (request_dir / "screenshot.png").write_bytes(base64.b64decode(screenshot_b64))

        response = {
            "ok": True,
            "provider": "browser_agent_notebooklm",
            "notebook_name": notebook_name,
            "notebook_title": final.get("notebook_title") or notebook_state.get("notebook_title") or notebook_name,
            "notebook_url": final.get("url"),
            "source_count": final_sources.get("source_count"),
            "source_summary": source_summary,
            "mindmap": mindmap_result,
            "infographics": infographics,
            "upload_result": upload_result,
            "request_dir": str(request_dir),
        }
        _mark_progress(request_dir, "completed", source_count=final_sources.get("source_count"))
        print(json.dumps(response, ensure_ascii=False))
        return 0
    finally:
        try:
            await asyncio.wait_for(browser.stop(), timeout=20)
        except Exception:
            pass
        if cleanup_dir is not None:
            shutil.rmtree(cleanup_dir, ignore_errors=True)


def main() -> int:
    _quiet_browser_logs()
    payload = _read_request()
    try:
        return asyncio.run(_run(payload))
    except Exception as exc:
        request_dir = _request_dir()
        _write_json(request_dir / "wrapper-error.json", {
            "error_type": type(exc).__name__,
            "error": str(exc),
            "failed_at": bjrt._now(),
        })
        print(f"browser_agent_notebooklm_wrapper failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
