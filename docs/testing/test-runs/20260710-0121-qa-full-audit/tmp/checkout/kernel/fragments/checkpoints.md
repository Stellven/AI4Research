## 强制检查点 (设计/开发前必查)

收到以下任务时，**必须先查 Cortex 知识库**：

**触发词**：
- "设计 xxx" / "实现 xxx" / "开发 xxx"
- "优化 xxx" / "改进 xxx"
- "写个 xxx" / "做个 xxx"
- "帮我 xxx" (涉及技术方案)

**执行顺序** (MUST)：
```
1️⃣ 查 Cortex 知识库
   sqlite3 ~/.solar/db/solar.db "
   SELECT title, finding, credibility
   FROM cortex_sources
   WHERE finding LIKE '%关键词%'
   ORDER BY credibility DESC LIMIT 10;
   "

2️⃣ 判断是否需要补充研究
   • 有相关经验 (credibility > 0.85) → 基于知识设计
   • 无相关经验或不确定 → 补充研究 (网络检索 / 深入分析)

3️⃣ 基于证据设计方案
   • 引用 Cortex 知识点
   • 说明为什么采用这个方案
   • 标注知识来源 (citation_key)

4️⃣ 方案输出后自动收藏
   • 重要设计 → 写入 sys_favorites
   • 新知识点 → 补充到 Cortex
```

**自检清单**：
- [ ] 我查 Cortex 了吗？
- [ ] 有相关的历史经验吗？
- [ ] 有相关的规则/技能吗？
- [ ] 需要补充研究吗？
- [ ] 我的方案基于证据还是猜测？
