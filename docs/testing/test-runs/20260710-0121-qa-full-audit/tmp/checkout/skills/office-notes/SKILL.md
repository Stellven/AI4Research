---
name: office-notes
description: 管理 Apple Notes - 创建、搜索、列出笔记 (macOS)
user-invocable: true
argument-hint: "[list|search <关键词>|create <标题>]"
---

# Apple Notes 管理

通过 AppleScript 管理 Apple Notes (macOS)。

## 前提条件

- macOS
- 授予终端 Automation 权限 (系统设置 → 隐私与安全 → 自动化)

## 操作

### 列出笔记文件夹

```bash
osascript -e 'tell application "Notes" to get name of every folder'
```

### 列出笔记 (默认文件夹)

```bash
osascript -e 'tell application "Notes" to get name of every note in folder "Notes"'
```

### 搜索笔记

```bash
osascript -e 'tell application "Notes"
  set matchingNotes to every note whose name contains "关键词"
  repeat with n in matchingNotes
    log (name of n) & " | " & (id of n)
  end repeat
end tell'
```

### 创建笔记

```bash
osascript -e 'tell application "Notes"
  make new note at folder "Notes" with properties {name:"标题", body:"内容"}
end tell'
```

### 读取笔记内容

```bash
osascript -e 'tell application "Notes"
  set theNote to first note whose name is "笔记标题"
  get body of theNote
end tell'
```

### 追加内容到笔记

```bash
osascript -e 'tell application "Notes"
  set theNote to first note whose name is "笔记标题"
  set body of theNote to (body of theNote) & "<br>追加内容"
end tell'
```

## 注意事项

- 笔记内容使用 HTML 格式
- 换行使用 `<br>`
- 操作需要 Notes 应用在后台运行
- 首次使用会弹出权限请求
