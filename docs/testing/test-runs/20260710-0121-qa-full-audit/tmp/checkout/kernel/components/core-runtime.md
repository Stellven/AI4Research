## core-runtime (已安装)

TypeScript 核心运行时已安装到 `~/.solar/core`，依赖 Bun。

- **守护进程**: `solar-daemon` 启动 `core/daemon/server.ts`（监听 `/tmp/solar.sock`）。
- **Web 仪表盘**: `bun run dashboard:web`（默认 http://127.0.0.1:3721/），是随包发布的仪表盘。
- **本体/上下文**: `core/ontology` 提供偏好与关系图谱，供启动时加载 Solar 上下文。
- 数据库默认 `~/.solar/db/solar.db`（可用 `SOLAR_DB_PATH` 覆盖）。
