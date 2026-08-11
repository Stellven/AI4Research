# Phase 22 çœŸå®žä»»åŠ¡æµ‹è¯•è®¡åˆ’

çŠ¶æ€ï¼šåˆç¨¿ï¼Œä¾›å®žçŽ°ä¸Žäººå·¥ä¿®è®¢
æ—¥æœŸï¼š2026-07-28

## ç›®æ ‡ä¸Žåˆ¤å®šè¾¹ç•Œ

æœ¬è®¡åˆ’ç”¨ 10 ä¸ªçœŸå®žä»»åŠ¡å›žç­”ä¸€ä¸ªæ›´ç›´æŽ¥çš„é—®é¢˜ï¼šç”¨æˆ·èƒ½å¦è®© OpenSolar å®Œæˆä¸€ä»¶æœ‰ç”¨çš„äº‹æƒ…ï¼Œå¹¶æ‹¿åˆ°å¯ä»¥æ£€æŸ¥çš„äº§ç‰©ã€‚

è¿™äº›ä»»åŠ¡ä¸æ˜¯å¯¹ 1,502 ä¸ª atomic feature çš„æ›¿ä»£æ€§é€é¡¹è¯æ˜Žã€‚ä¸‹æ–‡â€œè¦†ç›–çš„ L2â€è¡¨ç¤ºè¯¥ L2 åœ¨æµç¨‹ä¸­å¿…é¡»äº§ç”Ÿå¯è§‚å¯Ÿä½œç”¨ï¼›åªæœ‰å®žé™…è¯æ®æ”¯æŒçš„ L2 æ‰èƒ½èŽ·å¾—æ–°çš„æ­£é¢ç»“è®ºã€‚æŸæ¡ journey é€šè¿‡ï¼Œä¸ä¼šè‡ªåŠ¨æŠŠåˆ—è¡¨ä¸­æ¯ä¸ª L2 çš„å…¨éƒ¨è¾¹ç•Œéƒ½åˆ¤ä¸ºé€šè¿‡ã€‚

ç»Ÿä¸€ç»“æžœåç§°ï¼š

- `PASS`ï¼šæ ¸å¿ƒä»»åŠ¡å®Œæˆï¼Œä¸»è¦äº§ç‰©å­˜åœ¨ä¸”èƒ½äº’ç›¸å¯¹å¾—ä¸Šã€‚
- `PASS_WITH_KNOWN_LIMITATIONS`ï¼šæ ¸å¿ƒä»»åŠ¡å®Œæˆï¼Œä½†å­˜åœ¨æ˜Žç¡®ä¸”ä¸æŽ©ç›–çš„èƒ½åŠ›è¾¹ç•Œã€‚
- `FAIL`ï¼šçŽ¯å¢ƒå…·å¤‡ã€ä»»åŠ¡å®žé™…æ‰§è¡Œï¼Œä½†æ ¸å¿ƒç›®æ ‡æˆ–çœŸå®žæ€§æ£€æŸ¥å¤±è´¥ã€‚
- `ENVIRONMENT_BLOCKED`ï¼šç¼ºå°‘å·²æ˜Žç¡®æŒ‡å‡ºçš„ç³»ç»Ÿã€ç½‘ç»œã€è´¦å·ã€å‡­æ®æˆ–çœŸå®ž providerã€‚
- `NOT_AVAILABLE`ï¼šå½“å‰ä»£ç æ²¡æœ‰è¯¥ä»»åŠ¡æ‰€éœ€çš„äº§å“å…¥å£æˆ–å®žçŽ°ã€‚
- `NOT_TESTED`ï¼šå°šæœªæ‰§è¡Œã€‚

æ‰€æœ‰ä»»åŠ¡å¿…é¡»ï¼š

- ä½¿ç”¨éš”ç¦»çš„ `HOME`ã€`SOLAR_HOME`ã€`CLAUDE_DIR`ã€harness root å’Œè¾“å‡ºç›®å½•ï¼Œä¸ä¿®æ”¹çœŸå®žç”¨æˆ·ç›®å½•ã€‚
- ä¿å­˜å‘½ä»¤ã€å¼€å§‹/ç»“æŸæ—¶é—´ã€é€€å‡ºç ã€stdoutã€stderrã€äº§ç‰©æ¸…å•ã€å…³é”®æ–­è¨€ã€çŠ¶æ€å’Œé™åˆ¶è¯´æ˜Žã€‚
- å°†è¿è¡Œè¯æ®å†™å…¥ `outputs/phase22-real-journeys/<run-id>/`ã€‚
- éœ€è¦ live provider æ—¶åªä½¿ç”¨æ˜Žç¡®é€‰æ‹©çš„ providerï¼›ä¸å¾—æŠŠå¦ä¸€ provider å½“ä½œé™é»˜åŽå¤‡ã€‚
- ä¸æ‰“å°ã€å¤åˆ¶æˆ–æäº¤ API keyã€`.env` å†…å®¹æˆ–å…¶ä»–å‡­æ®ã€‚

## ä»»åŠ¡æ€»è§ˆ

| ID | çœŸå®žä»»åŠ¡ | ä¸»è¦ç”¨æˆ·ç»“æžœ | é»˜è®¤çŽ¯å¢ƒ |
|---|---|---|---|
| P22-J01 | ä»Žé›¶å®‰è£…å¹¶æŸ¥çœ‹è¿è¡ŒçŠ¶æ€ | å¯ç”¨çš„æœ¬åœ° CLI ä¸ŽçŠ¶æ€é¡µé¢ | Linux/WSL2ï¼Œæœ¬åœ°ï¼Œæ—  live provider |
| P22-J02 | è®© Solar å®žé™…ä¿®å¤ä¸€ä¸ªå°åž‹ä»£ç ç¼ºé™· | çœŸå®žä»£ç æ”¹åŠ¨ã€æµ‹è¯•ä¸Žå®¡æ‰¹è¯æ® | tmux + Codex/Claudeï¼Œlive provider |
| P22-J03 | è¿è¡Œå®˜æ–¹å¹³å°å·¥ä½œæµ benchmark | åˆ†æ•°ã€é€é¡¹è¯æ®ä¸Žå¯å®¡è®¡æŠ¥å‘Š | å·²å®‰è£…çš„éš”ç¦» harness |
| P22-J04 | å¯¼å…¥å¹¶é‡å¤å¯¼å…¥ä¸€ç¯‡æœ¬åœ°è®ºæ–‡ | å¯æŸ¥è¯¢çš„è®ºæ–‡ã€æ¥æºã€å›¾ä¸Žè®°å¿†è¯æ® | æœ¬åœ° PDF/Markdownï¼Œé»˜è®¤ç¦»çº¿ |
| P22-J05 | å›´ç»•ä¸»é¢˜å’Œ anchor æœç´¢æ–‡çŒ® | åŽ»é‡ä¸”å¸¦æ¥æºçš„å€™é€‰æ–‡çŒ®æ¸…å• | ç½‘ç»œ/æ–‡çŒ® provider |
| P22-J06 | ä»Žè®ºæ–‡è¯æ®å½¢æˆå’Œç­›é€‰ç ”ç©¶æƒ³æ³• | æœ‰æ¥æºã€å¯è¯ä¼ªã€å¯æŽ’åºçš„ idea cards | J04/J05 äº§ç‰©ï¼Œå¯é€‰ live model |
| P22-J07 | è®¾è®¡å¹¶å®žé™…è¿è¡Œä¸€ä¸ªå°å®žéªŒ | è®¡åˆ’ã€çœŸå®žè¿›ç¨‹ç»“æžœã€æŒ‡æ ‡å’ŒçŠ¶æ€ | æœ¬åœ° Pythonï¼Œå—æŽ§æ‰§è¡Œè®¸å¯ |
| P22-J08 | ç”¨å®žéªŒç»“æžœéªŒè¯ä¸€çœŸä¸€å‡çš„ä¸»å¼  | ä¸¤ä¸ªå¯è¿½æº¯ä¸”æœ‰åŒºåˆ†åº¦çš„ verdict | J07 äº§ç‰©ï¼Œæœ¬åœ° evaluator |
| P22-J09 | ç”Ÿæˆå¹¶å®¡é˜…ä¸€ä»½å¯äº¤ä»˜ç ”ç©¶æŠ¥å‘Š | æŠ¥å‘Šã€è¯æ®ç´¢å¼•ã€å®¡é˜…å’Œå‘å¸ƒåŒ… | J04â€“J08 äº§ç‰©ï¼Œå¯é€‰ç¼–è¯‘å·¥å…· |
| P22-J10 | å¤‡ä»½ã€ä¿ç•™æ•°æ®å¸è½½ã€æ¢å¤å¹¶å½»åº•å¸è½½ | æ•°æ®å¯æ¢å¤ä¸”æœ€ç»ˆæ—  Solar æ®‹ç•™ | éš”ç¦»å®‰è£…ç›®å½•ï¼Œæœ¬åœ° |

## P22-J01ï¼šä»Žé›¶å®‰è£…å¹¶æŸ¥çœ‹è¿è¡ŒçŠ¶æ€

### è¾“å…¥

- ä¸€ä¸ªæ–°çš„éš”ç¦» Linux/WSL2 ç”¨æˆ·ç›®å½•ã€‚
- å½“å‰ä»“åº“ checkoutã€‚
- å®‰è£…å‚æ•°ï¼š`--yes --components kernel,harness`ã€‚
- ç”¨æˆ·è®¾ç½®ï¼šæ—¶åŒºã€å·¥ä½œåŒºè·¯å¾„ã€selected runtime=`codex`ï¼›ä¸è¦æ±‚åœ¨æ­¤ä»»åŠ¡ä¸­å‘èµ·æ¨¡åž‹è°ƒç”¨ã€‚
- ä¸€ä¸ªåŠ¨æ€åˆ†é…çš„ loopback ç«¯å£ã€‚

### æ‰§è¡Œ

åœ¨éš”ç¦»ç›®å½•å®‰è£… Solarï¼Œè¿è¡Œ `solar doctor --json`ã€`solar status --json` å’Œ `solar ui --once`ï¼›é€šè¿‡è®¾ç½®æŽ¥å£å†™å…¥ç”¨æˆ·è®¾ç½®å¹¶é‡æ–°è¯»å–ï¼›å¯åŠ¨ status serverï¼Œè®¿é—®å¥åº·ã€è®¾ç½®å’ŒçŠ¶æ€é¡µé¢ï¼Œç„¶åŽæ­£å¸¸åœæ­¢æœåŠ¡ã€‚

### é¢„æœŸäº§ç‰©

- å®‰è£…å›žæ‰§ã€CLI launcherã€ç”¨æˆ·é…ç½®å’Œç»„ä»¶ç›®å½•ã€‚
- doctor/status JSONã€CLI çŠ¶æ€æ–‡æœ¬ã€‚
- status server çš„å¥åº·ã€è®¾ç½®å’ŒçŠ¶æ€ HTTP å“åº”ã€‚
- å®‰è£…å‰åŽæ–‡ä»¶æ¸…å•åŠâ€œæœªå†™å‡º sandboxâ€çš„æ£€æŸ¥ç»“æžœã€‚

### é€šè¿‡æ ‡å‡†

- å®‰è£…å‘½ä»¤é€€å‡º 0ï¼Œ`doctor` ç»™å‡ºå¯ç”¨ verdictï¼Œ`status` èƒ½è¯†åˆ«å®‰è£…ç»„ä»¶ã€‚
- ç”¨æˆ·è®¾ç½®å†™å…¥åŽå¯è¯»å–ï¼Œè¿”å›žå†…å®¹ä¸åŒ…å«å‡­æ®æ˜Žæ–‡ã€‚
- status server åœ¨é™å®šæ—¶é—´å†…è¿”å›ž HTTP 2xxï¼Œå¹¶èƒ½è¢«æ­£å¸¸åœæ­¢ï¼Œä¸é—ç•™è¿›ç¨‹æˆ–ç«¯å£ã€‚
- æ‰€æœ‰å†™å…¥å‡ä½äºŽ sandboxï¼›ç¼ºå°‘ provider ç™»å½•åªèƒ½æ˜¾ç¤ºä¸ºæ˜Žç¡®çš„ readiness é™åˆ¶ï¼Œä¸èƒ½è¢«è¯¯æŠ¥ä¸ºå·²ç™»å½•ã€‚

### è¦†ç›–çš„ L2

- Vertical â€” `Linux Cli`
- Vertical â€” `CLI`
- Vertical â€” `LLM Config`
- Vertical â€” `User Settings`
- Vertical â€” `Web Application & Status Service`
- Vertical â€” `Workflow & Platform Status Visibility`

## P22-J02ï¼šè®© Solar å®žé™…ä¿®å¤ä¸€ä¸ªå°åž‹ä»£ç ç¼ºé™·

### è¾“å…¥

- ä¸€ä¸ªä¸´æ—¶ Git ä»“åº“ï¼ŒåŒ…å«ä¸€ä¸ªå¾ˆå°çš„ Python æ–‡æœ¬è§£æžå™¨ã€ä¸€ä¸ªå¯å¤çŽ°ç¼ºé™·å’ŒçŽ°æœ‰æµ‹è¯•ã€‚
- ç”¨æˆ·è¯·æ±‚ï¼šä¸ºè¯¥ç¼ºé™·æ·»åŠ å¤±è´¥æµ‹è¯•ã€ä¿®å¤å®žçŽ°ã€è¿è¡Œæµ‹è¯•å¹¶æä¾›è¯æ®ã€‚
- ç»‘å®šçš„ä¸´æ—¶å·¥ä½œåŒºã€é€‰å®šçš„ Codex æˆ– Claude runtimeã€å¯ç”¨ç™»å½•/é¢åº¦ã€‚
- æ˜Žç¡®çš„ plan approval ä¸Ž eval approval æ“ä½œã€‚

### æ‰§è¡Œ

å¯åŠ¨çœŸå®ž harness/cockpitï¼Œæäº¤è‡ªç„¶è¯­è¨€ intakeï¼Œè¯»å– sprint IDï¼Œæ£€æŸ¥ requirement/plan artifactsï¼Œæ‰¹å‡†è®¡åˆ’ï¼Œè®©çœŸå®ž builder ä¿®æ”¹ä»“åº“å¹¶è¿è¡Œæµ‹è¯•ï¼Œæœ€åŽæ£€æŸ¥ evaluator è¯æ®å¹¶æäº¤ eval verdictã€‚

### é¢„æœŸäº§ç‰©

- raw intakeã€rewritten intentã€Requirement IRã€manifest å’Œ workspace bindingã€‚
- PRD/contractã€TaskGraphã€plan certificateã€gate ledger ä¸Žè°ƒåº¦è®°å½•ã€‚
- çœŸå®ž Git diffã€æ–°å¢žå›žå½’æµ‹è¯•ã€æµ‹è¯•æ—¥å¿—ã€builder/evaluator ç»“æžœå’Œæœ€ç»ˆ sprint çŠ¶æ€ã€‚
- provider/runtime èº«ä»½ã€å¼€å§‹/ç»“æŸæ—¶é—´å’Œå®žé™…è°ƒç”¨è¾¹ç•Œã€‚

### é€šè¿‡æ ‡å‡†

- ç¡®å®žå¯åŠ¨äº†é€‰å®š runtime çš„çœŸå®ž agentï¼›æ²¡æœ‰ä½¿ç”¨å‡è¿›ç¨‹ã€é¢„åˆ¶ diff æˆ–å¦ä¸€ provider åŽå¤‡ã€‚
- è®¡åˆ’åœ¨ builder è¿è¡Œå‰é€šè¿‡å®¡æ‰¹ï¼›æ”¹åŠ¨åªå‘ç”Ÿåœ¨å…è®¸çš„ä¸´æ—¶ä»“åº“èŒƒå›´ã€‚
- æ–°æµ‹è¯•èƒ½å¤Ÿè¯æ˜ŽåŽŸå§‹ç¼ºé™·ï¼Œä¿®å¤åŽç›®æ ‡æµ‹è¯•åŠåŽŸæœ‰æµ‹è¯•å‡é€šè¿‡ã€‚
- æœ€ç»ˆ verdict ä¸Žæµ‹è¯•ã€diffã€artifact ledger ä¸€è‡´ï¼Œä¸”æ‰€æœ‰å…³é”®äº§ç‰©å¯é€šè¿‡åŒä¸€ä¸ª sprint/run ID ä¸²è”ã€‚
- ç¼ºå°‘ç™»å½•ã€é…é¢ã€tmux æˆ–å—æ”¯æŒå¹³å°æ—¶ä¸º `ENVIRONMENT_BLOCKED`ï¼Œä¸å¾—é™çº§æˆå‡çš„æœ¬åœ° PASSã€‚

### è¦†ç›–çš„ L2

- Workflow â€” `Request Capture`
- Workflow â€” `Intake Context Binding`
- Workflow â€” `Intake Provenance Registration`
- Workflow â€” `Intent Interpretation`
- Workflow â€” `Constraint Resolution`
- Workflow â€” `Acceptance Definition`
- Workflow â€” `Requirement Contract Confirmation`
- Workflow â€” `POC Construction`
- Workflow â€” `POC Functional Readiness Validation`
- Workflow â€” `Evaluation Scope & Evidence Assembly`
- Workflow â€” `Claim & Acceptance-Criteria Comparison`
- Workflow â€” `Verdict, Blocker & Residual-Risk Classification`
- Foundation â€” `Task Contract & Acceptance Compilation`
- Foundation â€” `Task Contract Decomposition`
- Foundation â€” `TaskGraph Construction`
- Foundation â€” `TaskGraph Validation & Feasibility Analysis`
- Foundation â€” `DAG Scheduler, TaskGraph Readiness & Operator Binding`
- Foundation â€” `Main Loop Dispatch & Runtime Supervision`
- Foundation â€” `Code Construction`
- Foundation â€” `Verification Asset Construction`
- Foundation â€” `Engineering Correctness & Code Quality Evaluator`
- Foundation â€” `TaskGraph Persistence & Lifecycle Management`

## P22-J03ï¼šè¿è¡Œå®˜æ–¹å¹³å°å·¥ä½œæµ benchmark

### è¾“å…¥

- P22-J01 åˆ›å»ºçš„éš”ç¦»å®‰è£…å’Œ harness rootã€‚
- å®˜æ–¹ `platform-benchmark` å…¥å£ã€‚
- é˜ˆå€¼ `80`ï¼Œä»¥åŠæ˜¾å¼é‡å®šå‘åˆ°æœ¬æ¬¡ journey è¾“å‡ºç›®å½•çš„ JSONã€Markdown å’Œ evidence ç›®å½•ã€‚

### æ‰§è¡Œ

è¿è¡Œä¸€æ¬¡å®˜æ–¹å¹³å°å·¥ä½œæµ benchmarkï¼Œä¿ç•™æ¯ä¸ª probe çš„å‘½ä»¤ä¸Žè¾“å‡ºï¼Œå¹¶å†æ¬¡è¯»å–ç”Ÿæˆçš„ JSON/Markdown å¯¹ç…§æ€»ä½“åˆ†æ•°ã€æœ€ä½Žåˆ†ã€å¤±è´¥æ£€æŸ¥å’Œæœ€ç»ˆå¸ƒå°” verdictã€‚

### é¢„æœŸäº§ç‰©

- benchmark JSON ä¸Žäººç±»å¯è¯» Markdownã€‚
- æ¯ä¸ªåœºæ™¯çš„ command/stdout/stderr å’Œæ•°æ®/UI probe è¯æ®ã€‚
- æ€»åˆ†ã€æœ€ä½Žåˆ†ã€é˜ˆå€¼ã€é€åœºæ™¯åˆ†æ•°å’Œå¤±è´¥åŽŸå› ã€‚

### é€šè¿‡æ ‡å‡†

- benchmark 实际运行，而非只列出测试或读取历史结果。
- JSON、Markdown 和 evidence 目录均生成，逐项分数能够与总体分数重新计算一致。
- benchmark runner 必须记录场景、指标、阈值、逐项失败原因和最终 verdict。CLI 因被测对象低于阈值返回 1 时，仍属于一次完整执行。
- 被测对象是否达到质量阈值是 benchmark 的测量结果，不是 Benchmarking 功能本身的成功条件。只有 runner 异常、输出缺失或损坏、分数无法重算、verdict 与阈值不一致、或失败原因不可追溯时，J03 才判 `FAIL`。
- 官方外部 benchmark runner 缺失时必须显示为 pending/blocked，不得伪造 leaderboard 成绩。

### è¦†ç›–çš„ L2

- Workflow â€” `Benchmark Framing`
- Workflow â€” `Benchmark Protocol & Asset Preparation`
- Workflow â€” `Benchmark Execution`
- Workflow â€” `Metrics & Run Evidence Collection`
- Workflow â€” `Comparative Result Analysis & Benchmark Result Packaging`
- Foundation â€” `Benchmark Asset Construction`
- Foundation â€” `Performance, Cost & Benchmark Evaluator`
- Foundation â€” `Build Evidence Generation`

## P22-J04ï¼šå¯¼å…¥å¹¶é‡å¤å¯¼å…¥ä¸€ç¯‡æœ¬åœ°è®ºæ–‡

### è¾“å…¥

- ä¸€ç¯‡çŸ­å°ä½†ç»“æž„å®Œæ•´çš„æœ¬åœ° PDFï¼ŒåŒ…å« titleã€abstractã€methodã€resultsã€limitations å’Œå¼•ç”¨ã€‚
- åŒå†…å®¹çš„ Markdown ç‰ˆæœ¬ï¼Œç”¨äºŽæ£€æŸ¥åŒå†…å®¹ä¸åŒè½½ä½“ã€‚
- `AUTOSCI_DISABLE_NETWORK_FETCH=1`ï¼Œéš”ç¦» AutoSci workspaceã€‚

### æ‰§è¡Œ

å…ˆç”¨ `$ingest` å¯¼å…¥ PDFï¼Œå†å¯¼å…¥åŒä¸€ PDFï¼Œæœ€åŽå¯¼å…¥åŒå†…å®¹ Markdownï¼›è¯»å– source preparationã€research paperã€claim/methodã€memory å’Œ graph evidenceï¼Œæ£€æŸ¥é‡å¤å¯¼å…¥çš„å¤„ç†æ–¹å¼ã€‚

### é¢„æœŸäº§ç‰©

- prepared source/text/sectionsã€parse statusã€hashã€åŽŸå§‹è·¯å¾„å’Œè½¬æ¢é™åˆ¶ã€‚
- `research_paper.v1` ä»¥åŠç›¸å…³ claim/methodã€memoryã€graph/trace evidenceã€‚
- ä¸‰æ¬¡å¯¼å…¥ä¹‹é—´çš„é‡å¤ã€å¤ç”¨æˆ–æ–°å¢žè®°å½•è¯´æ˜Žã€‚

### é€šè¿‡æ ‡å‡†

- PDF å’Œ Markdown çš„æ­£æ–‡ã€ç« èŠ‚åŠæ¥æºä¿¡æ¯å‡èƒ½è¢«è¯»å–ï¼Œè¯æ®è·¯å¾„å…¨éƒ¨ä½äºŽ sandboxã€‚
- é¦–æ¬¡å¯¼å…¥è‡³å°‘ç”Ÿæˆä¸€ä»½ schema-valid research paper evidenceï¼Œtitle/method/result ä¸ä¸ºç©ºã€‚
- é‡å¤å¯¼å…¥ä¸å¾—é™é»˜åˆ¶é€ äº’ç›¸æ— å…³çš„å¤šä»½äº‹å®žï¼›è‹¥å½“å‰åªæ”¯æŒ same-ID å¹‚ç­‰è€Œä¸æ”¯æŒè·¨è½½ä½“åŽ»é‡ï¼Œå¯åˆ¤ `PASS_WITH_KNOWN_LIMITATIONS`ï¼Œä½†å¿…é¡»æ˜Žç¡®å±•ç¤ºé‡å¤è¾¹ç•Œã€‚
- è§£æžå¤±è´¥ã€ç©ºæ­£æ–‡ã€é”™è¯¯æ¥æºç»‘å®šæˆ–è¯æ®å†™åˆ°çœŸå®žç”¨æˆ·ç›®å½•å‡ä¸º `FAIL`ã€‚

### è¦†ç›–çš„ L2

- Workflow â€” `User-Supplied Material Import`
- Workflow â€” `Intake Qualification`
- Workflow â€” `Intake Context Binding`
- Workflow â€” `Intake Provenance Registration`
- Workflow â€” `Real-Time Intake Deduplication & Cleaning`
- Foundation â€” `Persistent Memory & Context Retrieval`
- Foundation â€” `Concept Graph Management`
- Foundation â€” `Memory Graph Management`
- Foundation â€” `Trace Graph Management`
- Foundation â€” `Evidence, Factuality & Scientific Validity Evaluator`

## P22-J05ï¼šå›´ç»•ä¸»é¢˜å’Œ anchor æœç´¢æ–‡çŒ®

### è¾“å…¥

- ä¸»é¢˜ï¼š`verifier-guided skill learning for LLM agents`ã€‚
- ä¸€ä¸ªçœŸå®ž anchor è®ºæ–‡ ID/URLã€ä¸€ä¸ªæŽ’é™¤ anchorã€limit=8ã€‚
- å¯ç”¨ç½‘ç»œåŠé¡¹ç›®å®žé™…æ”¯æŒçš„æ–‡çŒ® providerã€‚

### æ‰§è¡Œ

åˆ†åˆ«è¿è¡Œ topic ä¸Ž anchor discoveryï¼Œåˆå¹¶å€™é€‰ï¼Œæ£€æŸ¥åŽ»é‡ã€æ¥æºæ¸ é“ã€å¹´ä»½ã€æ ‡è¯†ç¬¦ã€æŽ’åç†ç”±å’Œæ˜¾å¼è¦†ç›–é™åˆ¶ã€‚

### é¢„æœŸäº§ç‰©

- discovery request/strategyã€‚
- `literature_discovery.v1`ã€å€™é€‰åˆ—è¡¨ã€provider/fetch çŠ¶æ€å’Œ limitationsã€‚
- åˆå¹¶åŽ»é‡åŽçš„æ¥æºæ¸…å•åŠ coverage reviewã€‚

### é€šè¿‡æ ‡å‡†

- è‡³å°‘è¿”å›ž 3 ç¯‡å”¯ä¸€ä¸”ä¸Žä¸»é¢˜ç›¸å…³çš„çœŸå®žå€™é€‰ï¼Œæ¯é¡¹æœ‰ç¨³å®š ID æˆ– URLã€æ ‡é¢˜å’Œæ¥æºæ¸ é“ã€‚
- anchorã€negative anchor å’Œ limit å¯¹ç»“æžœäº§ç”Ÿå¯è§‚å¯Ÿå½±å“ã€‚
- å€™é€‰ä¸æ˜¯å†…ç½® fixture å†’å……çš„å®žæ—¶ç»“æžœï¼›ä¸å¯è®¿é—® provider æ—¶ä¸º `ENVIRONMENT_BLOCKED`ã€‚
- åªæœ‰å•ä¸€æ¸ é“ä½†ç»“æžœæœ‰ç”¨ä¸”é™åˆ¶æ˜Žç¡®æ—¶å¯ä¸º `PASS_WITH_KNOWN_LIMITATIONS`ï¼›é”™è¯¯å¼•ç”¨ã€é‡å¤æ³›æ»¥æˆ–æŠŠç©ºç»“æžœæŠ¥æˆåŠŸä¸º `FAIL`ã€‚

### è¦†ç›–çš„ L2

- Workflow â€” `Search Strategy Formation`
- Workflow â€” `Multi-Source Signal Discovery`
- Workflow â€” `Source Qualification`
- Workflow â€” `Technical Signal Extraction`
- Workflow â€” `Signal Organization`
- Workflow â€” `Trend & Gap Analysis`
- Workflow â€” `Search Coverage Review`
- Foundation â€” `Model Routing & Selection`
- Foundation â€” `Model Usage Auditing`

## P22-J06ï¼šä»Žè®ºæ–‡è¯æ®å½¢æˆå’Œç­›é€‰ç ”ç©¶æƒ³æ³•

### è¾“å…¥

- P22-J04 çš„è®ºæ–‡ã€claim/method evidenceã€‚
- P22-J05 çš„å€™é€‰æ¥æºã€è¶‹åŠ¿å’Œ evidence gapã€‚
- ç”¨æˆ·ç›®æ ‡ï¼šæå‡ºæœ€å¤š 3 ä¸ªèƒ½å¤Ÿåœ¨å°åž‹æœ¬åœ°å®žéªŒä¸­éªŒè¯çš„æ”¹è¿›æƒ³æ³•ã€‚
- çº¦æŸï¼šå¿…é¡»å¼•ç”¨æ¥æºã€å†™å‡ºæœºåˆ¶ã€å¯è¯ä¼ªæ¡ä»¶ã€ä¸»è¦é£Žé™©å’Œæœ€å°å®žéªŒã€‚

### æ‰§è¡Œ

è¿è¡Œ `$ideate` ç”Ÿæˆå€™é€‰ï¼Œå†è¿è¡Œ `$novelty`/idea evaluationï¼›æ£€æŸ¥ known/failed idea memory çš„åŽ»é‡ï¼Œå¹¶é€‰æ‹©ä¸€ä¸ªè¿›å…¥å®žéªŒã€‚

### é¢„æœŸäº§ç‰©

- idea candidatesã€idea evaluationsã€è¯æ®é“¾æŽ¥å’ŒåŽ»é‡çŠ¶æ€ã€‚
- è‡³å°‘ä¸€ä¸ªå®Œæ•´ idea cardï¼šé—®é¢˜ã€å‡è®¾ã€æœºåˆ¶ã€æ–¹æ³•æ”¹å˜ã€éªŒè¯æ–¹å¼ã€é£Žé™©ã€é™åˆ¶å’ŒæŽ¨èç»“è®ºã€‚
- è¢«é€‰ idea åŠé€‰æ‹©ç†ç”±ã€‚

### é€šè¿‡æ ‡å‡†

- è‡³å°‘ç”Ÿæˆ 2 ä¸ªå«ä¹‰ä¸åŒçš„å€™é€‰ï¼›æ¯ä¸ªå€™é€‰éƒ½èƒ½è¿½æº¯åˆ°è¾“å…¥ evidenceï¼Œè€Œä¸æ˜¯åªå¤è¿°é¢˜ç›®ã€‚
- è‡³å°‘ä¸€ä¸ªå€™é€‰åŒ…å«å¯æµ‹é‡æˆåŠŸæ¡ä»¶å’Œèƒ½æŽ¨ç¿»å®ƒçš„ç»“æžœï¼›é€‰æ‹©ç†ç”±ä¸Ž novelty/feasibility evidence ä¸€è‡´ã€‚
- ç¼ºå°‘å¿…è¦ method/adaptation evidence å¿…é¡»æˆä¸ºæ˜¾å¼ blockerï¼Œä¸èƒ½ç”Ÿæˆçœ‹ä¼¼å®Œæ•´ä½†æ— ä¾æ®çš„ green resultã€‚
- ä»…ç”Ÿæˆ 1 ä¸ªä»æœ‰ç”¨ä¸”é™åˆ¶æ˜Žç¡®çš„å€™é€‰å¯ä¸º `PASS_WITH_KNOWN_LIMITATIONS`ï¼›æ— æ¥æºã€ä¸å¯è¯ä¼ªæˆ–é‡å¤å€™é€‰ä¸º `FAIL`ã€‚

### è¦†ç›–çš„ L2

- Workflow â€” `Idea Identification`
- Workflow â€” `Candidate Consolidation`
- Workflow â€” `Idea Card Formation`
- Workflow â€” `Opportunity Portfolio Prioritization`
- Workflow â€” `Research Question & Technical Claim Formation`
- Workflow â€” `Claim, Evidence, Data & Method Modeling`
- Workflow â€” `Falsifiability Screening & Hypothesis Contracting`
- Workflow â€” `Verification-Ready POC Design`
- Foundation â€” `Capability Discovery, Scoring & Selection`

## P22-J07ï¼šè®¾è®¡å¹¶å®žé™…è¿è¡Œä¸€ä¸ªå°å®žéªŒ

### è¾“å…¥

- P22-J06 é€‰ä¸­çš„ ideaã€‚
- ä¸€ä¸ªå°åž‹ CSV æ–‡æœ¬åˆ†ç±»æ•°æ®é›†ã€baseline è„šæœ¬å’Œ normalization variant è„šæœ¬ã€‚
- é¢„å…ˆå£°æ˜Žçš„å‡è®¾ï¼švariant çš„ exact-match accuracy è‡³å°‘æé«˜ 20 ä¸ªç™¾åˆ†ç‚¹ï¼Œä¸”ä¸­ä½å»¶è¿Ÿä½ŽäºŽ 20 msã€‚
- å›ºå®šéšæœºç§å­ã€å…è®¸æ‰§è¡Œçš„æœ¬åœ° Python å‘½ä»¤å’Œæ˜Žç¡® approval evidenceã€‚

### æ‰§è¡Œ

ä¾æ¬¡è¿è¡Œ `$exp-design`ã€èŽ·æ‰¹åŽçš„ `$exp-run`ã€`$exp-status` å’Œ `$exp-eval`ã€‚å¿…é¡»å¯åŠ¨çœŸå®žæœ¬åœ°è¿›ç¨‹è¯»å–æ•°æ®å¹¶è®¡ç®—ç»“æžœï¼Œä¸å¾—ç›´æŽ¥å¤åˆ¶ fixture resultã€‚

### é¢„æœŸäº§ç‰©

- experiment planã€çŽ¯å¢ƒ/ä¾èµ– manifestã€è¿è¡ŒåˆåŒå’Œæ‰§è¡Œå‘½ä»¤ã€‚
- stdout/stderrã€åŽŸå§‹é€æ ·æœ¬ç»“æžœã€æ±‡æ€» metricsã€experiment result å’Œ experiment statusã€‚
- success-criteria comparisonã€é™åˆ¶å’Œ eval evidenceã€‚

### é€šè¿‡æ ‡å‡†

- è®¡åˆ’åœ¨è¿è¡Œå‰äº§ç”Ÿï¼ŒåŒ…å«æ•°æ®ã€baselineã€variantã€æŒ‡æ ‡ã€é˜ˆå€¼ã€ç§å­å’Œåœæ­¢æ¡ä»¶ã€‚
- çœŸå®žå­è¿›ç¨‹é€€å‡º 0ï¼›ä¿å­˜çš„ accuracy/latency èƒ½ä»ŽåŽŸå§‹ç»“æžœé‡æ–°è®¡ç®—å¹¶ä¸€è‡´ã€‚
- status ä»Žå‡†å¤‡/è¿è¡Œè¿›å…¥æ˜Žç¡®ç»ˆæ€ï¼›eval verdict ä¸Žé¢„å…ˆå£°æ˜Žçš„é˜ˆå€¼ä¸€è‡´ã€‚
- ç¼ºå°‘ approval æ—¶å¿…é¡» fail closedï¼›åªè½¬æ¢ fixture è€Œæ²¡æœ‰æ‰§è¡Œå®žéªŒä¸º `FAIL`ã€‚

### è¦†ç›–çš„ L2

- Workflow â€” `Verification-Ready POC Design`
- Workflow â€” `POC Implementation Environment Preparation`
- Workflow â€” `POC Construction`
- Workflow â€” `POC Component Integration & Configuration`
- Workflow â€” `POC Functional Readiness Validation`
- Workflow â€” `Testable POC Artifact Consolidation & Benchmark Handoff`
- Foundation â€” `Experimental Asset Construction`
- Foundation â€” `Runtime Deliverable Construction`
- Foundation â€” `Execution Admission, Lease & Concurrency Control`
- Foundation â€” `Runtime Control Loop & Run Lifecycle Management`
- Foundation â€” `Contract, Schema & Artifact Conformance Evaluator`

## P22-J08ï¼šç”¨å®žéªŒç»“æžœéªŒè¯ä¸€çœŸä¸€å‡çš„ä¸»å¼ 

### è¾“å…¥

- P22-J07 çš„ planã€åŽŸå§‹ç»“æžœã€metricsã€æ—¥å¿—å’Œ artifact hashesã€‚
- ä¸»å¼  Aï¼šæŒ‰å®žé™…ç»“æžœè®¾ç½®ã€åº”å½“èƒ½è¢« evidence æ”¯æŒã€‚
- ä¸»å¼  Bï¼š`è¯¥æ–¹æ³•åœ¨æ‰€æœ‰è¾“å…¥å’Œæ‰€æœ‰çŽ¯å¢ƒä¸­è¾¾åˆ° 100% accuracy`ï¼Œæ•…æ„è¶…å‡º evidenceã€‚

### æ‰§è¡Œ

å¯¹ä¸¤ä¸ªä¸»å¼ åˆ†åˆ«è¿è¡Œ claim verification/experiment evaluationï¼Œå†è¿è¡Œä¸€æ¬¡ artifact reviewï¼›æ£€æŸ¥ verdictã€å¼•ç”¨ã€é™åˆ¶å’Œåè¯å¤„ç†ã€‚

### é¢„æœŸäº§ç‰©

- ä¸¤ä»½ claim verdictã€claim-to-evidence mappingã€review evidence å’Œ residual risksã€‚
- æ”¯æŒè¯æ®ã€åè¯/ç¼ºå¤±è¯æ®ã€é€‚ç”¨èŒƒå›´å’Œç»“è®ºç†ç”±ã€‚

### é€šè¿‡æ ‡å‡†

- ä¸»å¼  A çš„ç»“è®ºä¸¥æ ¼å–å†³äºŽé‡æ–°è®¡ç®—çš„æŒ‡æ ‡ï¼›ä¸»å¼  B ä¸å¾—è¢«åˆ¤ä¸ºå®Œå…¨ supportedã€‚
- verdict å¼•ç”¨çœŸå®ž experiment evidence å’Œ artifact hashï¼Œä¸æŠŠ backend è‡ªæŠ¥ç»“è®ºå½“æœ€ç»ˆè¯æ˜Žã€‚
- ç¼ºå¤±æˆ–å†²çª evidence å¯¼è‡´ `partially_supported`ã€`not_supported` æˆ– `inconclusive`ï¼Œä¸”åŽŸå› æ¸…æ¥šã€‚
- ä¸¤ä¸ªä¸»å¼ èŽ·å¾—æ— å·®åˆ«çš„ç¬¼ç»Ÿ green verdict ä¸º `FAIL`ã€‚

### è¦†ç›–çš„ L2

- Workflow â€” `Evaluation Scope & Evidence Assembly`
- Workflow â€” `Claim & Acceptance-Criteria Comparison`
- Workflow â€” `Evidence Completeness & Provenance Review`
- Workflow â€” `Experimental, Reasoning & External Validity Review`
- Workflow â€” `Verdict, Blocker & Residual-Risk Classification`
- Workflow â€” `Refinement & Follow-Up Recording`
- Foundation â€” `Evidence, Factuality & Scientific Validity Evaluator`
- Foundation â€” `Lifecycle, Parity & Human Review Evaluator`
- Foundation â€” `Trace Graph Management`

## P22-J09ï¼šç”Ÿæˆå¹¶å®¡é˜…ä¸€ä»½å¯äº¤ä»˜ç ”ç©¶æŠ¥å‘Š

### è¾“å…¥

- P22-J04 çš„æ¥æº/æ–¹æ³•ã€P22-J05 çš„æ–‡çŒ®ã€P22-J06 çš„ ideaã€P22-J07 çš„å®žéªŒç»“æžœå’Œ P22-J08 çš„ verdictã€‚
- ç›®æ ‡è¯»è€…ï¼šæŠ€æœ¯è´Ÿè´£äººï¼›é•¿åº¦çº¦ 1,500â€“2,500 å­—ã€‚
- å¿…å¤‡ç« èŠ‚ï¼šé—®é¢˜ã€ç›¸å…³è¯æ®ã€æ–¹æ³•ã€å®žéªŒã€ç»“æžœã€é™åˆ¶ã€å»ºè®®å’Œå¼•ç”¨ã€‚

### æ‰§è¡Œ

ä¾æ¬¡è¿è¡Œ `$paper-plan`ã€`$paper-draft`ã€`$review` å’Œ `$paper-compile`ï¼›è‹¥ poster å·¥å…·å¯ç”¨ï¼Œå†è¿è¡Œ `$poster`ã€‚åªç”Ÿæˆæœ¬åœ°äº¤ä»˜åŒ…ï¼Œä¸è¿›è¡Œå¤–éƒ¨å‘é€æˆ–å‘å¸ƒã€‚

### é¢„æœŸäº§ç‰©

- report/paper planã€Markdown draftã€citation/evidence index å’Œ review findingsã€‚
- scientific reportã€publication bundleï¼Œä»¥åŠçŽ¯å¢ƒæ”¯æŒæ—¶çš„ PDF/HTML posterã€‚
- æ¯ä¸ªä¸»è¦ç»“è®ºåˆ°æ¥æºæˆ– experiment verdict çš„é“¾æŽ¥ã€‚

### é€šè¿‡æ ‡å‡†

- Markdown æŠ¥å‘Šå¯ç›´æŽ¥é˜…è¯»ï¼Œå…·å¤‡å…¨éƒ¨å¿…å¤‡ç« èŠ‚ï¼Œä¸»è¦ç»“è®ºèƒ½å¤Ÿè¿½æº¯åˆ° evidenceã€‚
- æŠ¥å‘Šä¸å¾—æŠŠ P22-J08 åˆ¤ä¸º unsupported/inconclusive çš„ä¸»å¼ å†™æˆç¡®å®šäº‹å®žã€‚
- review å‘çŽ°ä¼šè¢«è®°å½•å¹¶åæ˜ åœ¨æœ€ç»ˆç¨¿ï¼›publication bundle ä¸åŒ…å« secret æˆ– sandbox å¤–è·¯å¾„ã€‚
- æœ¬æœºç¼ºå°‘ LaTeX/PDF/poster å·¥å…·æ—¶ï¼Œæ ¸å¿ƒ Markdown ä¸Ž evidence bundle å®Œæ•´å¯åˆ¤ `PASS_WITH_KNOWN_LIMITATIONS`ï¼›å·¥å…·å­˜åœ¨å´ç¼–è¯‘å¤±è´¥ä¸º `FAIL`ã€‚

### è¦†ç›–çš„ L2

- Workflow â€” `Delivery Planning & Evidence Handoff`
- Workflow â€” `Deliverable, Reusable Asset & Knowledge Packaging`
- Workflow â€” `User-Facing Deliverable Generation`
- Workflow â€” `Authorized Distribution, Knowledge Transfer & Lifecycle Closure`
- Foundation â€” `Report/Paper/Deliverable Construction`
- Foundation â€” `Decision Artifact Construction`
- Foundation â€” `Contract, Schema & Artifact Conformance Evaluator`
- Foundation â€” `Security, Privacy, Compliance & IP Evaluator`

## P22-J10ï¼šå¤‡ä»½ã€ä¿ç•™æ•°æ®å¸è½½ã€æ¢å¤å¹¶å½»åº•å¸è½½

### è¾“å…¥

- ä¸€ä¸ªéš”ç¦» Solar å®‰è£…ï¼ŒåŒ…å«æµ‹è¯•ç”¨ install receiptã€configã€å‡ `.env`ã€SQLite DBã€Solar code å’Œç”¨æˆ·è‡ªå·±çš„ `CLAUDE.md` å†…å®¹ã€‚
- å¯¹æ‰€æœ‰å¾…ä¿ç•™æ–‡ä»¶é¢„å…ˆè®¡ç®—çš„ hashã€‚
- æœ¬åœ° migration export/verify è·¯å¾„ï¼›ä¸è¿žæŽ¥è¿œç¨‹æœºå™¨ã€‚

### æ‰§è¡Œ

æ‰§è¡Œ `solar backup`ã€æœ¬åœ° migration export/verifyã€`uninstall --dry-run`ã€`uninstall --yes --keep-data`ã€é‡æ–°å®‰è£…ã€`solar restore`ï¼Œæœ€åŽæ‰§è¡Œå®Œæ•´ `uninstall --yes`ã€‚

### é¢„æœŸäº§ç‰©

- backup archiveã€migration bundle/manifest/verify evidenceã€‚
- dry-run æ–‡ä»¶å‰åŽå¿«ç…§ã€keep-data æ–‡ä»¶æ¸…å•ã€restore åŽ hash å¯¹æ¯”ã€‚
- full uninstall åŽæ®‹ç•™æ‰«æå’Œç”¨æˆ·åŽŸå§‹ `CLAUDE.md` å¯¹æ¯”ã€‚

### é€šè¿‡æ ‡å‡†

- dry-run ä¸æ”¹å˜ä»»ä½•æ–‡ä»¶ï¼›backup/migration åŒ…åªå«åˆåŒå…è®¸çš„æ•°æ®ä¸”ä¸æŠŠ secret æ‰“å°åˆ°æ—¥å¿—ã€‚
- keep-data åˆ é™¤ code/runtime assetsï¼Œä½†ä¿ç•™ receiptã€configã€`.env` å’Œ DBã€‚
- restore åŽä¿ç•™æ–‡ä»¶ hash ä¸Žå¤‡ä»½å‰ä¸€è‡´ï¼Œdoctor èƒ½è§£é‡Šå½“å‰å®‰è£…çŠ¶æ€ã€‚
- full uninstall åˆ é™¤ Solar è‡ªæœ‰ç›®å½•å’Œ sentinel/hookï¼Œåªä¿ç•™ç”¨æˆ·åŽŸå†…å®¹ä¸”æ— åŽå°è¿›ç¨‹/æœåŠ¡æ®‹ç•™ã€‚
- ä»»ä½•å†™å…¥çœŸå®ž homeã€ä¸¢å¤±æ•°æ®ã€æ—¥å¿—æ³„å¯†æˆ–åˆ é™¤ç”¨æˆ·å†…å®¹å‡ä¸º `FAIL`ã€‚

### è¦†ç›–çš„ L2

- Vertical â€” `Privacy & Personal Data Controls`
- Vertical â€” `Linux Cli`
- Vertical â€” `CLI`
- Workflow â€” `Deliverable, Reusable Asset & Knowledge Packaging`
- Workflow â€” `Authorized Distribution, Knowledge Transfer & Lifecycle Closure`
- Foundation â€” `Persistent Memory & Context Retrieval`
- Foundation â€” `Runtime Deliverable Construction`
- Foundation â€” `Security, Privacy, Compliance & IP Evaluator`

## P22-J11 through P22-J24 canonical mapping

The following journeys are intentionally kept in `tests/journeys/phase22/code/`.
Each row names the production-facing task, the executable selector, the minimum
observable success boundary, and the L2 scope that the journey may prove.

| Journey | Real task and production boundary | Exact test file | Minimum success and L2 mapping |
|---|---|---|---|
| P22-J11 | Resolve and invoke a capability capsule/operator through Solar. | `test_j11_capsule_operator.py` | A selected capsule and physical operator produce governed runtime evidence. Maps capsule definition/selection/invocation, operator binding, and model registry. |
| P22-J12 | Recover an interrupted run and retain execution records. | `test_j12_failure_recovery_records.py` | Resume preserves prior state and produces a terminal auditable record. Maps admission/lease, queue, supervision, and resumability. |
| P22-J13 | Open the local interaction interface through the shipped entrypoint. | `test_j13_local_interaction_interface.py` | The interface renders usable state without a platform crash. Maps CLI/GUI/TUI only for the exercised interface. |
| P22-J14 | Receive a WeChat-origin identity event through a product channel boundary. | `test_j14_wechat_identity.py` | A real configured channel/account is required; fixtures alone cannot pass WeChat or identity L2s. |
| P22-J15 | Execute the install/runtime matrix on the named OS. | `test_j15_cross_platform_install_matrix.py` | Each OS verdict requires evidence from that OS; one platform never proves another. Maps Windows/macOS/Linux app and CLI variants individually. |
| P22-J16 | Clarify requirements, compile a bounded repair, and verify it in TMUX. | `test_j16_tmux_requirements_builder.py` | Clarifications affect the contract; a real diff fixes a failing test through Solar. Maps requirement compilation, build preparation, integration, and defect repair. |
| P22-J17 | Select capsule/operator/model, persist TaskGraph state, interrupt, and recover in TMUX. | `test_j17_tmux_capsule_operator_core.py` | Dispatch, execution, evaluation, persistence, and recovery evidence all belong to the same sprint. Maps capsule/operator/model/graph/queue/resume L2s. |
| P22-J18 | Run Linux CLI/status/TMUX lifecycle and inspect settings and traces. | `test_j18_real_linux_status_lifecycle.py`; `test_j18_tmux_cli_status_config.py` | Real Linux/WSL commands start, report, stop, and release resources. Maps Linux CLI, status/web, TMUX, settings, TUI, and trace inspection only when directly observed. |
| P22-J19 | Use the real dashboard and inspect local account/channel surfaces. | `test_j19_real_gui_dashboard.py`; `test_j19_tmux_ui_account_channels.py` | Browser UI must render real backend state; account/channel claims require a real product entrypoint and configured platform. |
| P22-J20 | Produce a source-backed research synthesis through `autosci_bridge.py research`. | `test_j20_research_synthesis.py` | Provider sources, synthesis, citations, report, and terminal Solar state must all be usable. Maps technical-signal/trend analysis only when directly present. |
| P22-J21 | Build and execute an experiment, then hand off a usable package. | `test_j21_experiment_build_handoff.py` | Product-built assets execute, satisfy the contract, and are accepted by the downstream checker. Maps POC integration, conformance, admission, experimental/runtime construction. |
| P22-J22 | Review supported and overbroad claims and record follow-up. | `test_j22_evidence_review_followup.py` | Supported evidence passes and overreach fails closed through the production review path. Maps evaluation scope, completeness, validity, verdict, and follow-up. |
| P22-J23 | Route a real model request and retain usage audit evidence. | `test_j23_model_routing_audit.py` | Requested and observed provider/model match with no hidden fallback and durable request/response/cost evidence. Maps model routing and usage auditing. |
| P22-J24 | Export, redact, back up, delete, and uninstall only sandbox-owned personal data. | `test_j24_privacy_lifecycle.py` | All privacy actions run in an isolated home, preserve required data, remove owned residue, and expose no secrets. Maps privacy controls and lifecycle closure. |
| P22-J25 | Construct the supported Python runtime deliverable and execute its lifecycle in a clean sandbox. | `test_j25_runtime_deliverable_distribution.py` | A hash-bound wheel and credential-free manifest are independently verified; the wheel installs, starts a real status service, passes health checks, and rolls back both runtime and wrapper. Maps Runtime Deliverable Construction only for the exercised WSL/Linux Python-wheel target. |

Live provider journeys require explicit authorization and configured credentials.
Default collection does not execute them. Every group uses a unique basetemp,
cache directory, sandbox home, and dynamically reserved or group-owned port.

## å®žçŽ°é¡ºåº

å»ºè®®å…ˆå®Œæˆæ— éœ€ provider çš„ P22-J01ã€J03ã€J04ã€J07ã€J08ã€J10ï¼Œå†å®Œæˆéœ€è¦ç½‘ç»œæˆ–æ¨¡åž‹çš„ J05ã€J06ã€J09ï¼Œæœ€åŽåœ¨å·²æŽˆæƒçš„ live runtime ä¸Šè¿è¡Œ P22-J02ã€‚è¿™æ ·èƒ½å¤Ÿå…ˆè¯æ˜Ž runnerã€sandbox å’Œè¯æ®æ ¼å¼å¯é ï¼Œå†æ‰¿æ‹… provider æˆæœ¬ä¸Žä¸ç¡®å®šæ€§ã€‚
