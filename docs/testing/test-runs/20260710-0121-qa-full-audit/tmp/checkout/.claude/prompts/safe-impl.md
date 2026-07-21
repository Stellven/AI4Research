# Safe Implementation Template

把 Claude Code 从“写代码机器”切换成“受控工程执行系统”。没有证据，不许报喜。

## PHASE 1 · READ-ONLY ANALYSIS (Plan Mode)

请先不要改代码。先进入只读分析模式，完成以下内容：

1. 找出这个功能涉及的入口、调用链、数据结构、配置项、测试文件。
2. 给出实现计划，必须列出每个要修改的文件和原因。
3. 给出验收标准：
   - 哪些测试要跑
   - 哪些手工场景要验证
   - 哪些边界情况必须覆盖
4. 明确指出你不确定的地方，不允许假设。
5. 等我确认计划后再开始修改。

## PHASE 2 · EXECUTION RULES

执行阶段要求：

- 不允许硬编码业务数据、路径、token、ID、feature flag。
- 不允许新增孤立模块；新增代码必须接入真实调用链。
- 每完成一个小阶段必须运行相关测试。
- 如果测试失败，先修复，不要总结完成。
- 如果无法运行测试，必须说明原因和未验证风险。

## PHASE 3 · MANDATORY REPORTING FORMAT

最终回复必须包含：

- 已修改文件：file list with one-line purpose
- 实际运行的命令：commands actually executed
- 测试结果：pass/fail counts；failing tests verbatim
- 未验证项：what could not be tested and why
- 风险：regressions；edge cases；open questions
- 是否真正完成：yes/no/partial；with evidence

## HARD RULE · 无证据禁止报喜

没有测试或等价验证结果时，禁止使用 “完成” / “已实现” / “done” / “implemented” 等词。
