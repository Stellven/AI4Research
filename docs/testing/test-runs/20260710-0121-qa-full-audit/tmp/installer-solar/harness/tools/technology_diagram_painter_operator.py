#!/usr/bin/env python3
"""Command backend adapter for Technology Diagram Painter browser-agent logical operator tasks.

Follows the same pattern as youtube_transcript_operator.py:
  main() → _load_envelope() → build_request() → _rate_control_settings() → run_request() → flow_control
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "lib") not in sys.path:
    sys.path.insert(0, str(ROOT / "lib"))

import operator_flow_control as ofc  # noqa: E402

DEFAULT_OPERATOR_ID = "technology-diagram-painter"
DEFAULT_WRAPPER = ROOT / "scripts" / "browser_agent_technology_diagram_painter_wrapper.py"
DEFAULT_BROWSER_USE_PYTHON = Path.home() / ".claude" / "mcp-servers" / "browser-use" / ".venv" / "bin" / "python"
OPERATOR_RESULTS_DIR = Path(os.environ.get("SOLAR_OPERATOR_RESULTS_DIR", ROOT / "run" / "operator-results"))
OPERATOR_HEALTH_DIR = Path(os.environ.get("SOLAR_OPERATOR_HEALTH_DIR", ROOT / "run" / "operator-health"))


def _load_envelope() -> dict[str, Any]:
    path = str(os.environ.get("SOLAR_OPERATOR_ENVELOPE_JSON") or "").strip()
    if not path:
        raise RuntimeError("SOLAR_OPERATOR_ENVELOPE_JSON missing")
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("operator envelope must be a JSON object")
    return payload


def _task_dir() -> Path:
    raw = str(os.environ.get("TASK_DIR") or "").strip()
    if raw:
        path = Path(raw).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        return path
    return Path.cwd()


def _wrapper_cmd() -> list[str]:
    raw = (
        os.environ.get("BROWSER_AGENT_TECH_DIAGRAM_CMD")
        or ""
    ).strip()
    if raw:
        return shlex.split(raw)
    if DEFAULT_WRAPPER.exists() and DEFAULT_BROWSER_USE_PYTHON.exists():
        return [str(DEFAULT_BROWSER_USE_PYTHON), str(DEFAULT_WRAPPER)]
    if DEFAULT_WRAPPER.exists():
        return [sys.executable, str(DEFAULT_WRAPPER)]
    return []


def _operator_id(envelope: dict[str, Any]) -> str:
    return str(envelope.get("operator_id") or "").strip() or DEFAULT_OPERATOR_ID


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _task_id_from_env(task_dir: Path) -> str:
    raw = str(os.environ.get("TASK_ID") or os.environ.get("SOLAR_TASK_ID") or "").strip()
    return raw or task_dir.name or "technology-diagram-task"


def _is_original_image_response(response: dict[str, Any]) -> bool:
    source = str(response.get("source") or "").strip()
    url = str(response.get("url") or "").strip()
    image_path = str(response.get("image_path") or "").strip()
    return (
        source in {"network-image-response", "dom-original-asset"}
        or "/backend-api/estuary/content" in url
        or "generated_original_candidate" in image_path
    )


def _canonical_result(
    response: dict[str, Any],
    *,
    operator_id: str,
    task_dir: Path,
    task_id: str,
    status: str = "success",
    error: str = "",
) -> dict[str, Any]:
    original_image = _is_original_image_response(response)
    return {
        "schema_version": "solar.operator_result.v1",
        "operator_id": operator_id,
        "task_id": task_id,
        "status": status,
        "result_kind": "technology_diagram",
        "source": str(response.get("source") or ""),
        "original_image_response": bool(original_image),
        "original_image_ok": bool(status == "success" and original_image),
        "image_path": str(response.get("image_path") or ""),
        "url": str(response.get("url") or ""),
        "width": response.get("width"),
        "height": response.get("height"),
        "bytes": response.get("bytes"),
        "request_dir": str(response.get("request_dir") or ""),
        "task_dir": str(task_dir),
        "finished_at": _utc_now(),
        "error": error,
    }


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def record_operator_result(
    response: dict[str, Any],
    *,
    operator_id: str,
    task_dir: Path,
    task_id: str | None = None,
    status: str = "success",
    error: str = "",
) -> dict[str, Any]:
    """Persist canonical operator result and latest health projection.

    The status page intentionally reads this durable projection instead of
    scraping terminal text or browser output.
    """
    resolved_task_id = task_id or _task_id_from_env(task_dir)
    result = _canonical_result(
        response,
        operator_id=operator_id,
        task_dir=task_dir,
        task_id=resolved_task_id,
        status=status,
        error=error,
    )
    _write_json_atomic(task_dir / "operator-results" / "result.json", result)
    _write_json_atomic(OPERATOR_RESULTS_DIR / operator_id / resolved_task_id / "result.json", result)
    health = {
        **result,
        "health_status": "ok" if result.get("original_image_ok") else ("warn" if status == "success" else "error"),
        "health_summary": (
            "last run captured original image response"
            if result.get("original_image_ok")
            else "last run fell back to screenshot or failed before original image capture"
        ),
        "updated_at": result["finished_at"],
    }
    _write_json_atomic(OPERATOR_HEALTH_DIR / f"{operator_id}.json", health)
    return result


def build_request(envelope: dict[str, Any], *, task_dir: Path | None = None) -> dict[str, Any]:
    """Build a diagram generation request from the operator envelope.

    Envelope may contain:
      - input_text: the base text to draw
      - prompt: custom prompt (optional)
      - timeout_seconds: overall timeout (default: 600s)
      - max_retries: retry count (default: 1)
    """
    raw = envelope.get("technology_diagram_request")
    if isinstance(raw, dict):
        request = deepcopy(raw)
    else:
        request = {}
        for key in (
            "input_text",
            "prompt",
            "timeout_seconds",
            "max_retries",
        ):
            if key in envelope:
                request[key] = deepcopy(envelope[key])

    input_text = str(request.get("input_text") or "").strip()
    if not input_text:
        input_text = str(envelope.get("prompt") or "").strip()
    request["input_text"] = input_text

    if "prompt" not in request:
        request["prompt"] = """请生成一张极简技术白皮书 / 研究报告 Figure 风格的架构图。

请根据上述文本进行绘制。

整体视觉风格：
- 高端 AI Infra / 分布式系统 / 计算架构白皮书中的技术插图风格
- 干净、克制、理性、工程化
- 不像营销海报，不像手绘草图，不像产品宣传图
- 像论文、系统设计文档、技术战略报告里的正式 Figure

画面比例与构图：
- 16:9 横向画布
- 白色或极浅米白色背景
- 大量留白
- 主体结构清晰，元素少而准
- 使用横向长条、分层卡片、细线框、轻微圆角
- 所有元素严格对齐，网格化排版
- 层级之间间距均匀
- 视觉重心稳定，不要拥挤

线条与形状：
- 使用细边框矩形作为主要容器
- 边框颜色低饱和
- 圆角很小，接近工程图风格
- 不使用厚重阴影
- 不使用强烈渐变
- 不使用复杂装饰
- 不使用 3D 透视
- 不使用卡通图标
- 不使用手绘线条

颜色风格：
- 低饱和、高级灰、技术感配色
- 主色以蓝灰、青灰、米灰、棕灰、暗红灰为主
- 背景填充非常浅，边框略深
- 颜色只用于表达层级、分组、状态，不做装饰
- 整体色彩克制、冷静、专业
- 避免荧光色、高亮霓虹色、赛博朋克色、强对比彩虹色

字体风格：
- 标题使用现代无衬线字体，类似 Inter / IBM Plex Sans / Helvetica Neue
- 技术关键词使用 monospace 字体，类似 JetBrains Mono / IBM Plex Mono
- 英文标题可以使用大写字母和轻微字母间距
- 中文标注使用小字号、细字体，像白皮书边注
- 字体层级清楚：标题粗，说明轻，注释小
- 不要使用艺术字体、书法字体、手写字体

排版气质：
- 像正式研究报告中的系统 Figure
- 像企业级技术架构白皮书插图
- 像学术论文里的架构层级图
- 信息密度中等，避免把图塞满
- 每个模块只放必要文字
- 文字应短、硬、准，偏技术标签风格
- 使用中英文混排，但保持克制和统一

细节元素：
- 可以使用细分隔线、浅色虚线、轻量标签、Figure 编号、简短 caption
- 可以在底部加入一行简短结论或设计原则
- 可以使用少量小型状态标注，但不要抢主体
- 可以使用微弱阴影或浅色底纹，但必须非常克制

禁止风格：
- 不要手绘风
- 不要卡通风
- 不要 3D
- 不要玻璃拟态
- 不要大面积渐变
- 不要赛博朋克
- 不要花哨插画
- 不要复杂图标
- 不要营销海报风
- 不要 PPT 模板感太重
- 不要五颜六色
- 不要文字堆满
- 不要强烈阴影
- 不要拟物化 UI

最终效果：
画面应呈现为一张高级、克制、可直接放入技术白皮书、研究报告、架构设计文档或高端技术 PPT 的系统 Figure。"""

    if task_dir is not None:
        request.setdefault("request_dir", str((task_dir / "tech-diagram-request").resolve()))
    request.setdefault("timeout_seconds", 600)
    request.setdefault("max_retries", 1)
    return request


def _rate_control_settings(envelope: dict[str, Any]) -> dict[str, Any]:
    operator_id = _operator_id(envelope)
    flow_control: dict[str, Any] = {}
    try:
        import operator_runtime  # type: ignore
        config = operator_runtime.get_operator_config(operator_id) or {}
        if isinstance(config.get("flow_control"), dict):
            flow_control = dict(config["flow_control"])
    except Exception:
        flow_control = {}
    return {
        "operator_id": operator_id,
        "success_cooldown_seconds": ofc.int_value(
            envelope.get("success_cooldown_seconds") or flow_control.get("success_cooldown_seconds"),
            30,
        ),
        "rate_limit_cooldown_seconds": ofc.int_value(
            envelope.get("rate_limit_cooldown_seconds") or flow_control.get("rate_limit_cooldown_seconds"),
            600,
        ),
        "auth_cooldown_seconds": ofc.int_value(
            envelope.get("auth_cooldown_seconds") or flow_control.get("auth_cooldown_seconds"),
            3600,
        ),
        "defer_on_cooldown": ofc.bool_value(
            envelope.get("defer_on_cooldown") or flow_control.get("defer_on_cooldown"),
            True,
        ),
        "defer_on_auth": ofc.bool_value(
            envelope.get("defer_on_auth") or flow_control.get("defer_on_auth"),
            True,
        ),
    }


def _summary_markdown(response: dict[str, Any]) -> str:
    return "\n".join([
        "# Technology Diagram Painter Result",
        "",
        "## 已完成",
        f"- 状态: {response.get('status') or 'N/A'}",
        f"- 图像路径: {response.get('image_path') or 'N/A'}",
        f"- 外部URL: {response.get('url') or 'N/A'}",
        "",
        "## 说明",
        "- 生成的技术架构图已成功下载并保存在上述路径。",
        f"![Generated Diagram](file://{response.get('image_path')})" if response.get('image_path') else ""
    ])


def run_request(request: dict[str, Any], *, task_dir: Path, operator_id: str = DEFAULT_OPERATOR_ID) -> dict[str, Any]:
    input_text = str(request.get("input_text") or "").strip()
    if not input_text:
        raise RuntimeError("Technology Diagram operator requires input_text")
    cmd = _wrapper_cmd()
    if not cmd:
        raise RuntimeError("Technology Diagram browser-agent wrapper command is not configured")
    task_dir.mkdir(parents=True, exist_ok=True)
    request_dir = Path(str(request.get("request_dir") or (task_dir / "tech-diagram-request"))).expanduser()
    request_dir.mkdir(parents=True, exist_ok=True)

    (task_dir / "tech-diagram-request.json").write_text(
        json.dumps(request, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    env = os.environ.copy()
    if "BROWSER_AGENT_HEADLESS" not in env:
        env["BROWSER_AGENT_HEADLESS"] = "false"
    env.update({
        "BROWSER_AGENT_REQUEST_DIR": str(request_dir),
        "BROWSER_AGENT_TIMEOUT": str(request.get("timeout_seconds") or 600),
    })

    timeout = ofc.int_value(request.get("timeout_seconds"), 600)
    subprocess_timeout = timeout + 90
    max_retries = max(1, ofc.int_value(request.get("max_retries"), 1))

    last_exc = None
    for attempt in range(1, max_retries + 1):
        print(f"[Tech Diagram Operator] Starting execution attempt {attempt} of {max_retries}...", flush=True)
        try:
            proc = subprocess.run(
                cmd,
                input=json.dumps(request),
                text=True,
                capture_output=True,
                env=env,
                timeout=subprocess_timeout,
            )
            combined = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
            (task_dir / f"tech-diagram-output-attempt{attempt}.txt").write_text(
                combined + ("\n" if combined else ""),
                encoding="utf-8",
            )

            # The wrapper script should have written result.json to request_dir
            result_path = request_dir / "result.json"
            if not result_path.exists():
                if proc.returncode != 0:
                    raise RuntimeError(f"Wrapper exited with code {proc.returncode}. Log snippet:\n{combined[-1000:]}")
                else:
                    raise FileNotFoundError(f"result.json was not generated in {request_dir}")

            result = json.loads(result_path.read_text(encoding="utf-8"))

            if result.get("status") != "success":
                raise RuntimeError(f"Wrapper failed to generate image: {result.get('error') or result.get('status')}")

            # Save final results
            (task_dir / "tech-diagram-result.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            record_operator_result(result, operator_id=operator_id, task_dir=task_dir)

            print(_summary_markdown(result))
            return result
        except subprocess.TimeoutExpired as exc:
            last_exc = exc
            combined = ((exc.stdout or "") + "\n" + (exc.stderr or "")).strip()
            (task_dir / f"tech-diagram-output-attempt{attempt}.txt").write_text(
                combined + ("\n" if combined else ""),
                encoding="utf-8",
            )
            print(
                f"[Tech Diagram Operator] Attempt {attempt} timed out after "
                f"{subprocess_timeout}s: {exc}",
                file=sys.stderr,
                flush=True,
            )
            if attempt < max_retries:
                time.sleep(5)
        except Exception as exc:
            last_exc = exc
            print(f"[Tech Diagram Operator] Attempt {attempt} failed: {exc}", file=sys.stderr, flush=True)
            if attempt < max_retries:
                time.sleep(5)

    raise RuntimeError(f"Technology Diagram operator failed after {max_retries} attempts: {last_exc}")


def main() -> int:
    try:
        envelope = _load_envelope()
    except Exception as exc:
        print(f"Failed to load envelope: {exc}", file=sys.stderr)
        return 1

    task_dir = _task_dir()
    ofc.clear_task_control(task_dir)
    request = build_request(envelope, task_dir=task_dir)
    rate_control = _rate_control_settings(envelope)
    operator_id = str(rate_control["operator_id"])
    try:
        ofc.ensure_operator_available(operator_id)
        run_request(request, task_dir=task_dir, operator_id=operator_id)
        ofc.apply_success_cooldown(
            operator_id,
            success_cooldown_seconds=int(rate_control.get("success_cooldown_seconds") or 0),
        )
        return 0
    except Exception as exc:
        record_operator_result(
            {
                "status": "error",
                "source": "operator",
                "request_dir": str(request.get("request_dir") or ""),
            },
            operator_id=operator_id,
            task_dir=task_dir,
            status="error",
            error=f"{type(exc).__name__}: {exc}",
        )
        ofc.apply_failure_flow_control(
            task_dir,
            operator_id=operator_id,
            failure_text=str(exc),
            rate_limit_cooldown_seconds=int(rate_control.get("rate_limit_cooldown_seconds") or 0),
            auth_cooldown_seconds=int(rate_control.get("auth_cooldown_seconds") or 0),
            defer_on_cooldown=bool(rate_control.get("defer_on_cooldown")),
            defer_on_auth=bool(rate_control.get("defer_on_auth")),
        )
        print(f"technology_diagram_painter_operator failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
