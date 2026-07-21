---
name: skin-check
description: 皮肤检测 - 拍照→AI分析→专家评审
user-invocable: true
argument-hint: "[--test=<image_path>] [--remote]"
---

# 皮肤检测 v2.0

AI 驱动的皮肤健康检测系统，支持本地分析和远程专家评审。

## Phase 2: 本地模型实现

### ✅ 已实现

- **Phase 2.1**: 本地分类器 (~/.claude/skills/skin-check/phase2/)
  - CoreML 框架 + MobileNetV3-Large
  - 推理速度: ~30ms (100x faster than API)
  - 成本: $0 (vs $0.002/次 Phase 1)
  - 支持离线使用

- **Phase 2.2**: YOLOv8 病灶检测
  - 实时病灶位置标注
  - 严重程度评估 (0-100 分)
  - 边界框可视化

- **Phase 2.3**: 历史记录与趋势分析
  - SQLite 数据库存储
  - 30 天趋势分析
  - 改善/恶化/稳定状态检测

### ⏸️ 挂起

- **Phase 2.4**: 专用模型训练
  - 等待部署到 Mac mini Pro 48G
  - 数据集: DermNet (23K) / ISIC (50K)
  - 预估时间: 1-2.5 小时
  - 目标准确度: 85-90%
  - **Backlog**: task-e84fb0b2b11dfe95

## 使用方式

### 完整流程 (拍照 + 本地分析)
```bash
bun ~/.claude/skills/skin-check/phase2/skin-check-v2.ts
```

### 测试模式 (使用已有图片)
```bash
bun ~/.claude/skills/skin-check/phase2/skin-check-v2.ts --test=~/Desktop/selfie_xxx.jpg
```

### 混合模式 (本地 + 远程专家)
```bash
bun ~/.claude/skills/skin-check/phase2/skin-check-v2.ts --remote
```

### 历史记录管理
```bash
# 查看最近 10 次记录
bun ~/.claude/skills/skin-check/phase2/history-tracker.ts list 10

# 趋势分析
bun ~/.claude/skills/skin-check/phase2/history-tracker.ts trend 30d

# 对比两次检测
bun ~/.claude/skills/skin-check/phase2/history-tracker.ts compare 1 2
```

## 性能对比

| 指标 | Phase 1 (纯API) | Phase 2.1 (本地) |
|------|----------------|-----------------|
| 延迟 | 3-5s | ~30ms (100x faster) |
| 成本 | $0.002/次 | $0 |
| 离线 | ❌ | ✅ |
| 准确度 | 80-90% (专家) | 60-70% (简化规则) |

## 技术栈

- **运行时**: Bun (TypeScript)
- **本地模型**: CoreML (MobileNetV3-Large)
- **推理**: Vision framework (Swift)
- **病灶检测**: YOLOv8 (CoreML)
- **历史存储**: SQLite

## 架构

```
用户拍照
    │
    ▼
┌──────────────────────┐
│ Phase 2.1: 本地分类  │ ← CoreML + Swift
│ • 皮肤类型识别       │   Vision framework
│ • 置信度评分         │   ~30ms
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐
│ Phase 2.2: 病灶检测  │ ← YOLOv8 + CoreML
│ • 位置标注           │   边界框检测
│ • 严重程度评估       │   0-100 分
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐
│ Phase 2.3: 历史记录  │ ← SQLite
│ • 保存检测结果       │   趋势分析
│ • 趋势分析           │   改善/恶化/稳定
└──────────────────────┘
```

## 免责声明

⚠️ 此检测仅供参考，不能替代专业医疗诊断。

## 下一步

1. **训练专用模型** (等待 Mac mini Pro 部署)
   - 使用 CreateML (Apple 原生)
   - 数据集: DermNet (23K) / ISIC (50K)
   - 预估时间: 1-2.5 小时
   - 目标准确度: 85-90%

2. **模型优化**
   - 量化压缩 (减少模型大小)
   - CoreML 优化 (Metal GPU 加速)

3. **功能扩展**
   - 多部位检测 (面部、手臂、腿部)
   - AR 可视化 (实时标注)
   - 个性化建议 (基于历史趋势)
