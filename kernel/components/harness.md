## harness (已安装)

Python 协调 harness 已安装到 `~/.solar/harness`。基础安装依赖
python3；Product Delivery 运行时启动还需要 Bash 4+、tmux、jq，以及
`claude` CLI 在 PATH 上。

- **CLI**: `~/.solar/bin/solar-harness` 是 harness 入口。
- **启动预检**: `~/.solar/bin/solar-harness preflight` 会在创建 tmux
  session 前检查必需依赖，并明确标注 live Claude 为 manual-pending。
- **多窗格编排**: tmux 多窗格 harness 完整随包发布，无 TVS 依赖。
- **手动边界**: preflight/status 只验证外围运行层；live Claude pane 和真实
  delegation 结果必须在 Claude auth/quota 可用后由 owner 手动确认。
- 运行时依赖见 `requirements/harness.txt`。
