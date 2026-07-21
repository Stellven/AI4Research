# Solar 铁律: 禁止重要产出放 /tmp

> **来源**: 2026-03-28 监护人指出重启后 Solar 完全失忆
> **核心问题**: 分析报告、设计方案、断点诊断放在 /tmp，重启即丢

## 铁律定义

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│   /tmp = 真正的临时文件                                     │
│   仅限: 截图、编译产物、进程间通信、短期缓存                 │
│                                                             │
│   ❌ 禁止: 分析报告放 /tmp                                  │
│   ❌ 禁止: 设计方案放 /tmp                                  │
│   ❌ 禁止: 断点诊断放 /tmp                                  │
│   ❌ 禁止: 对比结论放 /tmp                                  │
│   ❌ 禁止: 任务状态放 /tmp                                  │
│                                                             │
│   ✅ 重要产出 → ~/.solar/ (永久)                            │
│   ✅ 知识沉淀 → sys_favorites (永久)                        │
│   ✅ 跨session记忆 → MEMORY.md (永久)                       │
│   ✅ 会话日志 → ~/.solar/session-state.jsonl (7天)          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## 存储分级

| 级别 | 位置 | 生命周期 | 放什么 |
|------|------|----------|--------|
| L0 | 对话 | 随时被压缩 | 临时思考、问答 |
| L1 | `~/.solar/` | 永久(除非手动清) | 分析报告、设计方案、状态 |
| L2 | `sys_favorites` | 永久 | 有价值结论、知识沉淀 |
| L3 | `MEMORY.md` | 永久(200行截断) | 跨session关键记忆锚点 |
| L4 | `/tmp/` | 重启即丢 | 仅截图、编译、真正临时 |

## 产出存储规则

| 产出类型 | 存储位置 | 命名示例 |
|----------|----------|----------|
| 分析报告 | `~/.solar/reports/` | `2026-03-28-evolve-diagnosis.md` |
| 架构设计 | `~/.solar/designs/` | `2026-03-28-evolve-v2.md` |
| 断点诊断 | `~/.solar/diagnoses/` | `2026-03-28-pipeline-breakpoints.md` |
| 对比分析 | `sys_favorites` | 标题含 "vs" 关键词 |
| 会议纪要 | `~/.solar/reports/` | `2026-03-28-session-summary.md` |
| 截图 | `/tmp/` (允许) | `page-123456.png` |
| 编译产物 | `/tmp/` (允许) | `build_*.o` |

## 自检清单

完成重要工作后：
- [ ] 分析/设计结论存入 `~/.solar/` 或 sys_favorites 了吗？
- [ ] MEMORY.md 更新了吗？（新架构、新教训）
- [ ] session-state.jsonl 有记录吗？（Solar 自报告）
- [ ] 没有把重要内容放 /tmp 吧？

## 根因分析

Solar 失忆的完整链条：
```
1. Solar 在 /tmp 写分析报告
2. 重启 → /tmp 清空 → 报告消失
3. 新 session → MEMORY.md 没更新 → 不知道昨天做了什么
4. session-state.jsonl 只有失败事件 → 看不到成功产出
5. 结果: 完全失忆, 从零开始
```

## 相关规则

- [01-three-core-laws.md](01-three-core-laws.md) — 自动收藏 Favorite
- [state-persistence.md](state-persistence.md) — 状态持久化
- [output-persist.md](output-persist.md) — 输出即固化

---

*No /tmp Artifacts Protocol v1.0*
*建立于: 2026-03-28*
*来源: 监护人指出重启后失忆问题*
