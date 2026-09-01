#!/usr/bin/env python3
"""Run a bounded, no-network KV-cache quantization measurement.

The preparation operator supplies a pretrained causal-language-model state,
its exact config, and tokenized slices from a retained public dataset.  This
runner performs no discovery or download.  It measures the actual cache tensor
footprint and quantize/dequantize reconstruction error for 8-bit and 4-bit
representations across every retained case.
"""

from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import torch
import torch.nn.functional as functional
from safetensors.torch import load_file
from transformers import GPT2Config, GPT2LMHeadModel


def _legacy_cache(value):
    if hasattr(value, "to_legacy_cache"):
        return value.to_legacy_cache()
    return tuple(value)


def _quantization_measure(tensor: torch.Tensor, bits: int) -> dict[str, float | int]:
    source = tensor.detach().float().cpu().contiguous()
    qmax = (1 << (bits - 1)) - 1
    maximum = float(source.abs().max().item())
    scale = maximum / qmax if maximum > 0 else 1.0
    started = time.perf_counter_ns()
    quantized = torch.clamp(torch.round(source / scale), -qmax, qmax)
    restored = quantized * scale
    elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
    flat_source = source.reshape(-1)
    flat_restored = restored.reshape(-1)
    cosine = float(
        functional.cosine_similarity(flat_source, flat_restored, dim=0, eps=1e-12).item()
    )
    mse = float(torch.mean((source - restored) ** 2).item())
    elements = int(source.numel())
    packed_bytes = math.ceil(elements * bits / 8) + 4
    return {
        "bits": bits,
        "elements": elements,
        "source_bytes": int(source.numel() * source.element_size()),
        "packed_bytes": int(packed_bytes),
        "mse": mse,
        "cosine_similarity": cosine,
        "quantize_dequantize_ms": elapsed_ms,
    }


def _mean(values: list[float]) -> float:
    return float(sum(values) / len(values)) if values else 0.0


def main(argv: list[str]) -> int:
    if len(argv) != 5:
        raise SystemExit(
            "usage: kv_cache_quantization_runner.py MODEL_CONFIG MODEL_WEIGHTS DATASET_TOKENS DATASET_TEXT RESULT"
        )
    config_path, weights_path, tokens_path, text_path, result_path = map(Path, argv)
    config = GPT2Config.from_json_file(str(config_path))
    model = GPT2LMHeadModel(config)
    missing, unexpected = model.load_state_dict(load_file(str(weights_path)), strict=False)
    if set(missing) != {"lm_head.weight"} or unexpected:
        raise RuntimeError(
            f"Unexpected model-state mismatch: missing={sorted(missing)}, unexpected={sorted(unexpected)}"
        )
    model.tie_weights()
    model.eval()
    dataset = json.loads(tokens_path.read_text(encoding="utf-8"))
    retained_text = json.loads(text_path.read_text(encoding="utf-8"))
    cases = dataset.get("cases") if isinstance(dataset, dict) else None
    if not isinstance(cases, list) or not cases:
        raise ValueError("dataset token package contains no cases")

    case_results: list[dict] = []
    for case in cases:
        input_ids = case.get("input_ids") if isinstance(case, dict) else None
        if not isinstance(input_ids, list) or not input_ids:
            raise ValueError("dataset case has no input_ids")
        tensor = torch.tensor([input_ids], dtype=torch.long)
        started = time.perf_counter_ns()
        with torch.inference_mode():
            output = model(input_ids=tensor, use_cache=True)
        forward_ms = (time.perf_counter_ns() - started) / 1_000_000
        cache = _legacy_cache(output.past_key_values)
        tensors = [entry for layer in cache for entry in layer[:2]]
        measurements = {
            bits: [_quantization_measure(value, bits) for value in tensors]
            for bits in (8, 4)
        }
        fp32_bytes = sum(item["source_bytes"] for item in measurements[8])
        int8_bytes = sum(item["packed_bytes"] for item in measurements[8])
        int4_bytes = sum(item["packed_bytes"] for item in measurements[4])
        case_results.append(
            {
                "case_id": str(case.get("case_id") or ""),
                "seed": int(case.get("seed") or 0),
                "context_tokens": len(input_ids),
                "source_row_ids": list(case.get("source_row_ids") or []),
                "forward_ms": forward_ms,
                "kv_tensor_count": len(tensors),
                "kv_fp32_bytes": fp32_bytes,
                "kv_int8_estimated_bytes": int8_bytes,
                "kv_int4_estimated_bytes": int4_bytes,
                "memory_reduction_ratio_int8": fp32_bytes / int8_bytes,
                "memory_reduction_ratio_int4": fp32_bytes / int4_bytes,
                "mean_reconstruction_mse_int8": _mean([float(item["mse"]) for item in measurements[8]]),
                "mean_reconstruction_mse_int4": _mean([float(item["mse"]) for item in measurements[4]]),
                "mean_reconstruction_cosine_int8": _mean([float(item["cosine_similarity"]) for item in measurements[8]]),
                "mean_reconstruction_cosine_int4": _mean([float(item["cosine_similarity"]) for item in measurements[4]]),
                "quantize_dequantize_ms_int8": sum(float(item["quantize_dequantize_ms"]) for item in measurements[8]),
                "quantize_dequantize_ms_int4": sum(float(item["quantize_dequantize_ms"]) for item in measurements[4]),
            }
        )

    def average(field: str) -> float:
        return _mean([float(case[field]) for case in case_results])

    metrics = [
        {"name": "case_count", "value": len(case_results), "unit": "cases"},
        {"name": "mean_context_tokens", "value": average("context_tokens"), "unit": "tokens"},
        {"name": "memory_reduction_ratio_int8", "value": average("memory_reduction_ratio_int8"), "unit": "ratio"},
        {"name": "memory_reduction_ratio_int4", "value": average("memory_reduction_ratio_int4"), "unit": "ratio"},
        {"name": "mean_reconstruction_mse_int8", "value": average("mean_reconstruction_mse_int8"), "unit": "mse"},
        {"name": "mean_reconstruction_mse_int4", "value": average("mean_reconstruction_mse_int4"), "unit": "mse"},
        {"name": "mean_reconstruction_cosine_int8", "value": average("mean_reconstruction_cosine_int8"), "unit": "cosine"},
        {"name": "mean_reconstruction_cosine_int4", "value": average("mean_reconstruction_cosine_int4"), "unit": "cosine"},
        {"name": "mean_forward_ms", "value": average("forward_ms"), "unit": "ms"},
        {"name": "mean_quantize_dequantize_ms_int8", "value": average("quantize_dequantize_ms_int8"), "unit": "ms"},
        {"name": "mean_quantize_dequantize_ms_int4", "value": average("quantize_dequantize_ms_int4"), "unit": "ms"},
    ]
    experiment_id = str(dataset.get("experiment_id") or "kv-cache-quantization-poc")
    payload = {
        "schema": "autosci.kv_cache_quantization_result.v1",
        "outputs": {
            "result": {
                "experiment_id": experiment_id,
                "outcome": "inconclusive",
                "metrics": metrics,
                "evidence_ids": [
                    str(dataset.get("dataset_evidence_id") or ""),
                    str(dataset.get("model_evidence_id") or ""),
                ],
                "case_results": case_results,
                "retained_text_record_count": len(retained_text.get("records") or []),
            }
        },
        "limitations": [
            "This bounded CPU PoC measures KV tensor footprint and quantization reconstruction error on a small GPT-2 model; it does not reproduce 32K-128K serving benchmarks.",
            "Packed memory is estimated from tensor element count plus one scale per tensor; no production quantized attention kernel was benchmarked.",
            "Forward latency is descriptive only and is not a cross-system throughput or TTFT comparison.",
        ],
    }
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
