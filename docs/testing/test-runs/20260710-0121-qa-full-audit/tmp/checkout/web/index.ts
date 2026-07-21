/**
 * Solar Web Dashboard
 *
 * 极简架构：
 * - 无服务器，直接生成 HTML
 * - 从 SQLite 读取数据
 * - HTML 自动刷新
 *
 * 使用:
 *   bun run web/generate.ts              # 生成一次
 *   bun run web/generate.ts --watch      # 持续更新
 *   bun run web/generate.ts --open       # 生成并打开
 */

export { } from "./generate";
