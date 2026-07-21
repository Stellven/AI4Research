你是 Solar Harness 的 ThunderOMLX 分片代码库语义分析器。
请仅基于当前这个仓库分片里的 deterministic 代码片段做中文分析，不要补全未看到的实现。
你的职责是给后续总汇编阶段提供高密度、可验证的局部摘要。

输出格式要求：
1. 这一分片覆盖的模块/目录
2. 关键入口/符号
3. 明确观察到的数据流/控制流
4. 该分片暴露的风险/边界
5. 必须继续查看的相邻模块

- objective: grouped synthesis
- repo_path: /Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/codex-not-run-phase/codex-nr-0284/pytest/test_run_pipeline_groups_final0/repo
- requested_language: zh
- chunk_id: chunk-001
- chunk_paths: README.md, src/mod_1.py, src/mod_2.py, src/mod_3.py

## Repo Scan Summary
- file_count_scanned: 7
- directories: README.md, src
- languages: {"Markdown": 1, "Python": 6}

## Chunk Snippets
### File: README.md
- language: Markdown
- symbols: N/A
```text
# Demo Repo

```

### File: src/mod_1.py
- language: Python
- symbols: fn_1, Class1
```text
def fn_1():
    return 'value-1'

class Class1:
    pass

########################################################################################################################################################################################################
```

### File: src/mod_2.py
- language: Python
- symbols: fn_2, Class2
```text
def fn_2():
    return 'value-2'

class Class2:
    pass

########################################################################################################################################################################################################
```

### File: src/mod_3.py
- language: Python
- symbols: fn_3, Class3
```text
def fn_3():
    return 'value-3'

class Class3:
    pass

########################################################################################################################################################################################################
```
