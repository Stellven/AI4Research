# Apple Notes → WeChat → Solar Wiki 工作流

## 工作流概览

```
微信文章
  → 用户分享/复制到 Apple 备忘录 "Solar Inbox" 文件夹
  → solar-harness notes scan --once  (每 2 小时自动运行)
  → 自动识别 mp.weixin.qq.com 链接并抓取微信网页正文
  → 新/变更正文导出到 ~/Knowledge/_raw/apple-notes/YYYYMMDD/
  → 标准 wiki-ingest dispatch 文件创建 → 大模型提炼
  → Solar Knowledge Base (concepts/entities/claims)
```

---

## 快速开始

### 1. 在 Apple 备忘录创建 "Solar Inbox" 文件夹

打开备忘录 → 左侧"文件夹"列表 → "+"新建文件夹 → 命名 `Solar Inbox`

### 2. 授权自动化权限

**系统设置 → 隐私与安全 → 自动操作**

确保终端（Terminal / iTerm2）对 **备忘录** 有访问权限。

### 3. 诊断检查

```bash
solar-harness notes doctor --json
```

期望输出：
```json
{
  "notes_access": "ok",
  "target_folder": "Solar Inbox",
  "target_folder_status": "exists",
  "raw_dir_writable": true
}
```

### 4. 手动扫描

```bash
# 干运行 — 查看待处理 Notes，不写文件
solar-harness notes scan --once --dry-run

# 正式扫描 — 导出新/变更 Notes
solar-harness notes scan --once
```

### 5. 安装定时任务（可选）

```bash
# 每 2 小时自动扫描
solar-harness notes install-scheduler --interval 7200

# 其他间隔选项
solar-harness notes install-scheduler --interval 3600   # 每 1 小时
solar-harness notes install-scheduler --interval 21600  # 每 6 小时
solar-harness notes install-scheduler --interval 86400  # 每 24 小时

# 卸载
solar-harness notes uninstall-scheduler
```

---

## 命令参考

| 命令 | 说明 |
|------|------|
| `notes doctor [--json]` | 检查权限和配置 |
| `notes scan --once [--dry-run] [--force-dispatch] [--json]` | 扫描并导出 Notes |
| `notes status [--json]` | 查看上次运行状态 |
| `notes install-scheduler --interval <s> [--dry-run]` | 安装 launchd 定时任务 |
| `notes uninstall-scheduler` | 卸载定时任务 |

---

## 配置文件

`~/.solar/harness/config/apple-notes-ingest.json`：

```json
{
  "notes_folder": "Solar Inbox",
  "tags": ["#solar-ingest", "#知识库", "#solar"],
  "interval_seconds": 7200,
  "raw_dir": "~/Knowledge/_raw/apple-notes",
  "all_notes": false,
  "fetch_wechat": true,
  "wechat_timeout_seconds": 20
}
```

⚠️ `all_notes` 默认 `false`。只有显式改为 `true` 才会扫全量备忘录。

`fetch_wechat` 默认 `true`。如果备忘录正文或链接字段里出现 `mp.weixin.qq.com`，扫描器会抓取微信网页正文；抓取失败时降级使用 Notes 内容，并在 frontmatter 写入 `wechat_fetch_status: "error"`。

---

## 导出文件格式

导出路径：`~/Knowledge/_raw/apple-notes/YYYYMMDD/note-<id>-<slug>.md`

每个文件含完整 frontmatter：

```markdown
---
source: "apple-notes"
source_app: "WeChat"
note_id: "note-abc001"
note_title: "文章标题"
note_folder: "Solar Inbox"
captured_at: "2026-05-08T09:00:00Z"
updated_at: "2026-05-08T10:00:00Z"
source_url: "https://mp.weixin.qq.com/s/..."
wechat_url: "https://mp.weixin.qq.com/s/..."
wechat_fetch_status: "ok"
wechat_fetched_at: "2026-05-08T10:00:00Z"
ingest_status: "pending"
content_hash: "sha256:a1b2c3d4"
---

# 文章标题

正文内容（已脱敏）...
```

## 知识库派单

每个新/变更导出会同时写两类 dispatch：

| 类型 | 路径 | 用途 |
|------|------|------|
| 标准派单 | `~/Knowledge/_raw/solar-harness/.dispatch/wiki-ingest-<ts>.md` | 被 `wiki dispatch-watch` 默认识别并派给 `wiki-ingest` |
| 兼容派单 | `~/Knowledge/_raw/solar-harness/.dispatch/apple-notes-<id>-<ts>.json` | 保留旧链路/审计信息 |

标准派单参数固定为 `mode=append`、`project=apple-notes`、`source=<导出 md>`，避免只写 raw 文件但没有进入知识库流水线的断头。

---

## 隐私保护

默认启用以下脱敏（可用 `--full` 跳过）：

| 类型 | 替换为 |
|------|--------|
| 手机号 `1[3-9]\d{9}` | `[PHONE]` |
| 邮箱 | `[EMAIL]` |
| Bearer Token | `[TOKEN]` |
| 银行卡号 16-19位 | `[CARD]` |
| 身份证 18位 | `[ID]` |

- 加密/锁定笔记会被跳过
- 事件日志不包含笔记正文
- 导出文件只进入 `_raw/` 暂存目录，不直接写最终 wiki 页面

---

## Delta / 内容去重机制

Manifest 路径：`~/.solar/harness/state/apple-notes-ingest/manifest.json`

重复扫描不会重复导出。去重分两层：

| 层级 | 机制 | 处理 |
|------|------|------|
| 同一笔记 | `note_id + modified_at + content_hash` | 内容未变化则跳过 |
| 删除重建 | `content_index[content_hash]` | 新 `note_id` 但内容相同则标记 `duplicate`，不重复导出/派单 |

`content_hash` 会先去 HTML、折叠空白再哈希，避免 Apple Notes 同步造成的格式噪声。重复项仍写入 manifest，记录 `duplicate_of` 和 `last_seen_at`，方便审计。

---

## 故障排查

### `notes_access: "denied"`

→ 系统设置 → 隐私与安全 → 自动操作 → 授权终端访问备忘录

### `target_folder_status: "missing"`

→ 在备忘录 App 创建 `Solar Inbox` 文件夹

### `raw_dir_writable: false`

→ `mkdir -p ~/Knowledge/_raw/apple-notes`

### 扫描返回空 candidates

→ 确认 Notes 在 `Solar Inbox` 文件夹（不是子文件夹）  
→ 确认备忘录已同步（iCloud 同步中可能延迟）

### launchd scheduler 未运行

```bash
# 检查状态
launchctl list com.solar.apple-notes-ingest

# 日志
tail -f ~/.solar/harness/logs/apple-notes-ingest.out.log
tail -f ~/.solar/harness/logs/apple-notes-ingest.err.log
```

---

## Observability

`/status` 端点 (port 8765) 包含 `apple_notes_ingest` section：

```json
{
  "apple_notes_ingest": {
    "enabled": true,
    "interval_seconds": 7200,
    "last_run_at": "2026-05-08T12:00:00Z",
    "notes_seen": 5,
    "notes_exported": 3,
    "notes_skipped": 2,
    "scheduler_loaded": true,
    "ok": true
  }
}
```
