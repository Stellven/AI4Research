"""Prepare a real, bounded KV-cache quantization PoC package."""

from __future__ import annotations

import hashlib
import json
import random
import shutil
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from ..operators.research_synthesis.base import ResearchOperatorError
except ImportError:
    from operators.research_synthesis.base import ResearchOperatorError


SERVICE_ID = "autosci-kv-cache-quantization-package"
SERVICE_VERSION = "1.0.0"
DATASET_ID = "Salesforce/wikitext"
DATASET_CONFIG = "wikitext-2-raw-v1"
DATASET_SPLIT = "test"
MODEL_ID = "sshleifer/tiny-gpt2"
EXPERIMENT_FAMILY = "causal_lm_kv_cache_quantization.v1"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return _sha256(path)


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise ResearchOperatorError("Experiment package path escapes the workspace", error_type="scope_violation") from exc


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class KVCacheExperimentPackageBuilder:
    workspace_root: Path
    service_id: str = SERVICE_ID
    service_version: str = SERVICE_VERSION

    def __post_init__(self) -> None:
        self.workspace_root = Path(self.workspace_root).resolve()

    @staticmethod
    def supports(text: str) -> bool:
        normalized = " ".join(str(text or "").casefold().replace("-", " ").split())
        return "kv cache" in normalized and any(term in normalized for term in ("quant", "compress", "memory"))

    def __call__(
        self,
        *,
        objective: str,
        output_dir: Path,
        result_path: Path,
        experiment_id: str,
        allow_network: bool,
    ) -> dict[str, Any]:
        if not self.supports(objective):
            raise ResearchOperatorError(
                "No registered real experiment family matches the selected claim",
                error_type="unsupported_experiment_family",
            )
        if not allow_network:
            raise ResearchOperatorError(
                "The real public dataset/model package requires network-enabled preparation",
                error_type="environment_unavailable",
            )
        output_dir = Path(output_dir).resolve()
        result_path = Path(result_path).resolve()
        if not output_dir.is_relative_to(self.workspace_root) or not result_path.is_relative_to(self.workspace_root):
            raise ResearchOperatorError("Experiment package paths escape the workspace", error_type="scope_violation")

        try:
            from datasets import load_dataset
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:
            raise ResearchOperatorError(
                "datasets and transformers are required for this experiment family",
                error_type="environment_unavailable",
            ) from exc

        output_dir.mkdir(parents=True, exist_ok=True)
        package_dir = output_dir / "experiment_package"
        package_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="download-", dir=output_dir) as temporary:
            cache_root = Path(temporary)
            try:
                dataset = load_dataset(
                    DATASET_ID,
                    DATASET_CONFIG,
                    split=DATASET_SPLIT,
                    cache_dir=str(cache_root / "datasets"),
                )
                tokenizer = AutoTokenizer.from_pretrained(
                    MODEL_ID,
                    cache_dir=str(cache_root / "models"),
                )
                model = AutoModelForCausalLM.from_pretrained(
                    MODEL_ID,
                    cache_dir=str(cache_root / "models"),
                )
            except Exception as exc:
                raise ResearchOperatorError(
                    f"Public dataset/model acquisition failed: {type(exc).__name__}: {str(exc)[:240]}",
                    error_type="environment_unavailable",
                ) from exc

            nonempty = [index for index, row in enumerate(dataset) if str(row.get("text") or "").strip()]
            if len(nonempty) < 3:
                raise ResearchOperatorError("WikiText-2 returned fewer than three non-empty records", error_type="provider_contract_failure")
            cases: list[dict[str, Any]] = []
            retained_rows: dict[int, dict[str, Any]] = {}
            for case_index, (seed, context_length) in enumerate(zip((11, 29, 47), (128, 256, 512)), start=1):
                chooser = random.Random(seed)
                start = chooser.randrange(len(nonempty))
                row_ids: list[int] = []
                text_parts: list[str] = []
                for offset in range(len(nonempty)):
                    row_id = nonempty[(start + offset) % len(nonempty)]
                    text = str(dataset[row_id].get("text") or "").strip()
                    if not text:
                        continue
                    row_ids.append(row_id)
                    text_parts.append(text)
                    retained_rows[row_id] = {
                        "row_id": row_id,
                        "text": text,
                        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                    }
                    ids = tokenizer("\n".join(text_parts), add_special_tokens=False)["input_ids"]
                    if len(ids) >= context_length:
                        break
                ids = tokenizer("\n".join(text_parts), add_special_tokens=False)["input_ids"][:context_length]
                if len(ids) < context_length:
                    raise ResearchOperatorError("Unable to assemble the requested tokenized dataset case", error_type="provider_contract_failure")
                cases.append(
                    {
                        "case_id": f"case-{case_index:02d}",
                        "seed": seed,
                        "context_tokens": context_length,
                        "source_row_ids": row_ids,
                        "input_ids": ids,
                    }
                )

            model_dir = package_dir / "model"
            model.save_pretrained(model_dir, safe_serialization=True)
            config_path = model_dir / "config.json"
            weights = sorted(model_dir.glob("*.safetensors"))
            if len(weights) != 1:
                raise ResearchOperatorError("Prepared model must have one safetensors weight file", error_type="provider_contract_failure")
            weights_path = weights[0]
            tokens_path = package_dir / "dataset_tokens.json"
            text_path = package_dir / "selected_text.json"
            dataset_evidence_id = f"hf:{DATASET_ID}:{DATASET_CONFIG}:{DATASET_SPLIT}:{getattr(dataset, '_fingerprint', 'unknown')}"
            model_evidence_id = f"hf:{MODEL_ID}"
            _write_json(
                tokens_path,
                {
                    "schema": "autosci.kv_cache_dataset_tokens.v1",
                    "experiment_id": experiment_id,
                    "dataset_evidence_id": dataset_evidence_id,
                    "model_evidence_id": model_evidence_id,
                    "cases": cases,
                },
            )
            _write_json(
                text_path,
                {
                    "schema": "autosci.retained_public_text.v1",
                    "dataset_id": DATASET_ID,
                    "dataset_config": DATASET_CONFIG,
                    "split": DATASET_SPLIT,
                    "records": [retained_rows[key] for key in sorted(retained_rows)],
                },
            )

        runner_source = Path(__file__).with_name("kv_cache_quantization_runner.py")
        runner_path = package_dir / "kv_cache_quantization_runner.py"
        shutil.copyfile(runner_source, runner_path)
        assets = [runner_path, config_path, weights_path, tokens_path, text_path]
        asset_rows = [
            {
                "role": role,
                "path": _relative(path, self.workspace_root),
                "sha256": _sha256(path),
                "bytes": path.stat().st_size,
            }
            for role, path in zip(
                ("runner", "model_config", "model_weights", "dataset_tokens", "retained_source_text"),
                assets,
            )
        ]
        runner_rel, config_rel, weights_rel, tokens_rel, text_rel = [row["path"] for row in asset_rows]
        result_rel = _relative(result_path, self.workspace_root)
        input_hashes = {row["path"]: row["sha256"] for row in asset_rows[1:]}
        manifest = {
            "experiment_family": EXPERIMENT_FAMILY,
            "prepared_at": _utc_now(),
            "dataset": {
                "dataset_id": DATASET_ID,
                "config": DATASET_CONFIG,
                "split": DATASET_SPLIT,
                "fingerprint": str(getattr(dataset, "_fingerprint", "unknown")),
                "source": f"https://huggingface.co/datasets/{DATASET_ID}",
                "record_count": len(retained_rows),
                "case_count": len(cases),
                "context_lengths": [case["context_tokens"] for case in cases],
                "seeds": [case["seed"] for case in cases],
                "evidence_id": dataset_evidence_id,
            },
            "model": {
                "model_id": MODEL_ID,
                "source": f"https://huggingface.co/{MODEL_ID}",
                "parameter_count": int(model.num_parameters()),
                "evidence_id": model_evidence_id,
            },
            "assets": asset_rows,
            "execution": {
                "contract": "python_json_file.v1",
                "command_argv": ["python", runner_rel, config_rel, weights_rel, tokens_rel, text_rel, result_rel],
                "result_path": result_rel,
                "runner_sha256": asset_rows[0]["sha256"],
                "input_sha256s": input_hashes,
            },
            "criteria_bindings": [
                {"criterion": "8-bit cache representation reduces retained bytes by at least 1.8x", "metric": "memory_reduction_ratio_int8", "operator": ">=", "value": 1.8},
                {"criterion": "4-bit cache representation reduces retained bytes by at least 3.2x", "metric": "memory_reduction_ratio_int4", "operator": ">=", "value": 3.2},
            ],
            "limitations": [
                "The package uses a small pretrained GPT-2 model and WikiText-2 slices so it remains CPU-bounded.",
                "It validates the cache-footprint/quantization trade-off, not 32K-128K production serving performance.",
            ],
        }
        return manifest
