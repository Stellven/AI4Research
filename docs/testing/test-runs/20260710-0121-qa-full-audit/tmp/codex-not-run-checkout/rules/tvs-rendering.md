# Solar 铁律: TVS 渲染

> LLM 生成意图(VDL)，不生成 ASCII。TVS 确定性渲染。

## VDL 组件速查

```typescript
card("TITLE", [sections])     // 卡片
kv([{key, value}])            // 键值对
table(headers, rows)          // 表格
sparkline(data, label)        // 趋势线 ▁▂▃▄▅▆▇█
progress(value, max)          // 进度条 ███████░░░ 75%
```

## TCSS 布局

```css
.root { columns: 3; gap: 1; }
@media (max-width: 80) { .root { columns: 1; } }
```

## 显式触发词 (高优先级渲染)

"我要看/给我看/展示/显示" → 输出完整 VDL 仪表盘

## 风格切换

```bash
/theme              # 当前风格
/theme list         # 所有风格
/theme <name>       # 切换风格
```

内置风格: `solar-dark`(默认) | `solar-light` | `minimal` | `neon` | `ascii` | `rounded`

## Footer (必须)

每次 TVS 输出必须包含:
```
────────────────────────────────────────
Powered by TVS v0.4.0 · Style: {风格}
切换风格: /theme <style>
```
