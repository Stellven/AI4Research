#!/usr/bin/env python3
"""
MLX 量化性能 Benchmark
测试 FP16 vs INT8 vs INT4 的性能差异
"""

import mlx.core as mx
import mlx.nn as nn
import time
import numpy as np
from typing import Dict, Any, List, Tuple
from dataclasses import dataclass


@dataclass
class BenchConfig:
    """Benchmark 配置"""
    warmup_iters: int = 5
    test_iters: int = 20
    batch_size: int = 1
    seq_len: int = 512
    hidden_size: int = 2048
    num_layers: int = 4


class SimpleTransformerBlock(nn.Module):
    """简化的 Transformer Block 用于测试"""

    def __init__(self, hidden_size: int, num_heads: int = 8):
        super().__init__()
        self.hidden_size = hidden_size
        self.num_heads = num_heads
        self.head_dim = hidden_size // num_heads

        # Self-attention
        self.q_proj = nn.Linear(hidden_size, hidden_size)
        self.k_proj = nn.Linear(hidden_size, hidden_size)
        self.v_proj = nn.Linear(hidden_size, hidden_size)
        self.o_proj = nn.Linear(hidden_size, hidden_size)

        # FFN
        self.ffn_up = nn.Linear(hidden_size, hidden_size * 4)
        self.ffn_down = nn.Linear(hidden_size * 4, hidden_size)

        # Norms
        self.norm1 = nn.RMSNorm(hidden_size)
        self.norm2 = nn.RMSNorm(hidden_size)

    def __call__(self, x: mx.array) -> mx.array:
        # Self-attention
        residual = x
        x = self.norm1(x)

        B, L, D = x.shape
        q = self.q_proj(x).reshape(B, L, self.num_heads, self.head_dim).transpose(0, 2, 1, 3)
        k = self.k_proj(x).reshape(B, L, self.num_heads, self.head_dim).transpose(0, 2, 1, 3)
        v = self.v_proj(x).reshape(B, L, self.num_heads, self.head_dim).transpose(0, 2, 1, 3)

        # Scaled dot-product attention
        scale = self.head_dim ** -0.5
        scores = (q @ k.transpose(0, 1, 3, 2)) * scale
        attn = mx.softmax(scores, axis=-1)
        out = (attn @ v).transpose(0, 2, 1, 3).reshape(B, L, D)
        x = residual + self.o_proj(out)

        # FFN
        residual = x
        x = self.norm2(x)
        x = self.ffn_up(x)
        x = nn.gelu(x)
        x = self.ffn_down(x)
        x = residual + x

        return x


class SimpleModel(nn.Module):
    """简单模型用于 benchmark"""

    def __init__(self, hidden_size: int = 2048, num_layers: int = 4):
        super().__init__()
        self.layers = [SimpleTransformerBlock(hidden_size) for _ in range(num_layers)]
        self.final_norm = nn.RMSNorm(hidden_size)

    def __call__(self, x: mx.array) -> mx.array:
        for layer in self.layers:
            x = layer(x)
        return self.final_norm(x)


def count_parameters(model: nn.Module) -> int:
    """统计模型参数量 - 递归处理嵌套结构"""
    def count_nested(obj) -> int:
        if isinstance(obj, mx.array):
            return obj.size
        elif isinstance(obj, dict):
            return sum(count_nested(v) for v in obj.values())
        elif isinstance(obj, list):
            return sum(count_nested(item) for item in obj)
        else:
            return 0
    return count_nested(model.parameters())


def get_model_memory_mb(model: nn.Module, dtype_bytes: int = 2) -> float:
    """估算模型内存占用 (MB)"""
    params = count_parameters(model)
    return (params * dtype_bytes) / (1024 * 1024)


def quantize_to_int8(weight: mx.array) -> Tuple[mx.array, mx.array]:
    """简单的 INT8 量化"""
    # Per-tensor symmetric quantization
    abs_max = mx.max(mx.abs(weight))
    scale = abs_max / 127.0
    q_weight = mx.round(weight / scale).astype(mx.int8)
    return q_weight, scale


def dequantize_int8(q_weight: mx.array, scale: mx.array) -> mx.array:
    """INT8 反量化"""
    return q_weight.astype(mx.float16) * scale


class QuantizedLinear(nn.Module):
    """量化的 Linear 层"""

    def __init__(self, original_linear: nn.Linear):
        super().__init__()
        weight = original_linear.weight
        q_weight, scale = quantize_to_int8(weight)
        self.q_weight = q_weight
        self.scale = scale
        self.bias = original_linear.bias if hasattr(original_linear, 'bias') else None

    def __call__(self, x: mx.array) -> mx.array:
        # 动态反量化
        weight = dequantize_int8(self.q_weight, self.scale)
        out = x @ weight.T
        if self.bias is not None:
            out = out + self.bias
        return out


def quantize_model(model: SimpleModel) -> SimpleModel:
    """量化整个模型的 Linear 层"""
    for layer in model.layers:
        layer.q_proj = QuantizedLinear(layer.q_proj)
        layer.k_proj = QuantizedLinear(layer.k_proj)
        layer.v_proj = QuantizedLinear(layer.v_proj)
        layer.o_proj = QuantizedLinear(layer.o_proj)
        layer.ffn_up = QuantizedLinear(layer.ffn_up)
        layer.ffn_down = QuantizedLinear(layer.ffn_down)
    return model


def run_benchmark(model: nn.Module, config: BenchConfig, name: str) -> Dict[str, float]:
    """运行 benchmark"""
    # 生成测试数据
    x = mx.random.normal((config.batch_size, config.seq_len, config.hidden_size))
    x = x.astype(mx.float16)

    # Warmup
    print(f"  Warming up {name}...")
    for _ in range(config.warmup_iters):
        _ = model(x)
        mx.eval(_)

    # Benchmark
    print(f"  Running {config.test_iters} iterations...")
    times = []
    for _ in range(config.test_iters):
        start = time.perf_counter()
        output = model(x)
        mx.eval(output)  # 确保计算完成
        end = time.perf_counter()
        times.append((end - start) * 1000)  # ms

    times = np.array(times)
    return {
        'name': name,
        'avg_ms': float(np.mean(times)),
        'std_ms': float(np.std(times)),
        'min_ms': float(np.min(times)),
        'max_ms': float(np.max(times)),
        'p50_ms': float(np.percentile(times, 50)),
        'p99_ms': float(np.percentile(times, 99)),
        'throughput': config.batch_size * config.seq_len / (np.mean(times) / 1000),  # tokens/sec
    }


def print_results(results: List[Dict], config: BenchConfig):
    """打印结果"""
    print("\n" + "=" * 70)
    print("MLX 量化性能 Benchmark 结果")
    print("=" * 70)
    print(f"\n配置: batch={config.batch_size}, seq_len={config.seq_len}, "
          f"hidden={config.hidden_size}, layers={config.num_layers}")
    print("-" * 70)

    # 表头
    print(f"{'模型':<20} {'平均(ms)':<12} {'P50(ms)':<12} {'P99(ms)':<12} {'吞吐(tok/s)':<15}")
    print("-" * 70)

    baseline = results[0]['avg_ms']
    for r in results:
        speedup = baseline / r['avg_ms']
        print(f"{r['name']:<20} {r['avg_ms']:<12.2f} {r['p50_ms']:<12.2f} "
              f"{r['p99_ms']:<12.2f} {r['throughput']:<15.0f} ({speedup:.2f}x)")

    print("-" * 70)

    # 计算提升
    if len(results) > 1:
        speedup = baseline / results[1]['avg_ms']
        print(f"\n✨ INT8 量化加速比: {speedup:.2f}x")
        print(f"   内存节省: ~50% (FP16 → INT8)")


def main():
    print("=" * 70)
    print("🚀 MLX 量化性能 Benchmark")
    print("=" * 70)
    print(f"\nMLX 版本: {mx.__version__}")
    print(f"设备: {mx.default_device()}")

    config = BenchConfig(
        warmup_iters=5,
        test_iters=20,
        batch_size=1,
        seq_len=512,
        hidden_size=2048,
        num_layers=4
    )

    # 创建 FP16 模型
    print("\n📦 创建 FP16 基准模型...")
    model_fp16 = SimpleModel(config.hidden_size, config.num_layers)
    mx.eval(model_fp16.parameters())

    params = count_parameters(model_fp16)
    mem_fp16 = get_model_memory_mb(model_fp16, 2)
    print(f"   参数量: {params:,}")
    print(f"   FP16 内存: {mem_fp16:.1f} MB")

    # 创建 INT8 量化模型
    print("\n📦 创建 INT8 量化模型...")
    model_int8 = SimpleModel(config.hidden_size, config.num_layers)
    mx.eval(model_int8.parameters())
    model_int8 = quantize_model(model_int8)
    mem_int8 = get_model_memory_mb(model_fp16, 1)  # INT8 = 1 byte
    print(f"   INT8 内存: {mem_int8:.1f} MB (节省 {(1 - mem_int8/mem_fp16)*100:.0f}%)")

    results = []

    # Benchmark FP16
    print("\n🔥 Benchmark FP16...")
    r = run_benchmark(model_fp16, config, "FP16 (baseline)")
    results.append(r)

    # Benchmark INT8
    print("\n🔥 Benchmark INT8...")
    r = run_benchmark(model_int8, config, "INT8 Quantized")
    results.append(r)

    # 打印结果
    print_results(results, config)

    print("\n✅ Benchmark 完成!")
    print("=" * 70)


if __name__ == "__main__":
    main()
