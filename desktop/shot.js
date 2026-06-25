// Visually verify the live dashboard via the cached chromium (no MCP needed).
const { chromium } = require("playwright");
(async () => {
  const url = process.env.URL || "http://127.0.0.1:8765/";
  const out = process.env.OUT || "dashboard.png";
  const browser = await chromium.launch({
    args: ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
  });
  const page = await browser.newPage({
    viewport: { width: 1440, height: 900 },
  });
  try {
    await page.goto(url, { waitUntil: "domcontentloaded", timeout: 20000 });
  } catch (e) {
    console.log("GOTO_WARN:", e.message);
  }
  await page.waitForTimeout(3000); // let the SPA render
  console.log("URL:", url);
  console.log("TITLE:", await page.title());
  const html = await page.content();
  console.log("HTML_LEN:", html.length);
  const txt = await page
    .evaluate(() => (document.body && document.body.innerText) || "")
    .catch(() => "");
  console.log("VISIBLE_TEXT_SAMPLE:", JSON.stringify(txt.slice(0, 500)));
  try {
    await page.screenshot({
      path: out,
      timeout: 12000,
      animations: "disabled",
    });
    console.log("SCREENSHOT_OK:", out);
  } catch (e) {
    console.log("SCREENSHOT_FAIL:", e.message);
  }
  await browser.close();
})();
