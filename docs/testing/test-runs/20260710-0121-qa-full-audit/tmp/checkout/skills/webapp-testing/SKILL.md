---
name: webapp-testing
description: 使用 Playwright 进行 Web 应用 UI 测试
user-invocable: true
disable-model-invocation: false
argument-hint: "[url 或测试描述]"
---

# /webapp-testing - Web UI 测试

## 功能

使用 Playwright 自动化测试 Web 应用的 UI 交互。

## 前置条件

```bash
# 安装 Playwright
npm install -D @playwright/test
npx playwright install
```

## 执行步骤

1. **确认测试目标**
   - URL 或本地服务地址
   - 要测试的功能点

2. **生成测试代码**
   ```typescript
   import { test, expect } from '@playwright/test';

   test('功能描述', async ({ page }) => {
     await page.goto('http://localhost:3000');

     // 交互操作
     await page.click('button#submit');

     // 断言
     await expect(page.locator('.result')).toBeVisible();
   });
   ```

3. **运行测试**
   ```bash
   npx playwright test
   ```

4. **输出结果**
   ```
   ✓ 测试名称 (耗时)

   总计: X passed, Y failed
   ```

## 常用操作

| 操作 | 代码 |
|------|------|
| 点击 | `page.click('selector')` |
| 输入 | `page.fill('input', 'text')` |
| 等待 | `page.waitForSelector('selector')` |
| 截图 | `page.screenshot({ path: 'out.png' })` |
| 断言可见 | `expect(locator).toBeVisible()` |
| 断言文本 | `expect(locator).toHaveText('text')` |

## 与 Tester Agent 配合

此 skill 专注于 UI 测试，补充 Tester Agent 的单元/集成测试能力。
