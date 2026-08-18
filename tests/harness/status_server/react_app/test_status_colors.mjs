import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const cssUrl = new URL(
  "../../../../harness/status-server/react-app/src/styles.css",
  import.meta.url,
);
const css = await readFile(cssUrl, "utf8");
const successMatch = css.match(/--solar-success:\s*(#[0-9a-f]{6})\s*;/i);
assert.ok(successMatch, "completed-state color token must exist");

const [red, green, blue] = successMatch[1]
  .slice(1)
  .match(/.{2}/g)
  .map((channel) => Number.parseInt(channel, 16));
assert.ok(red !== green || green !== blue, "completed state must not be pending gray");

function linear(channel) {
  const value = channel / 255;
  return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
}
const luminance = 0.2126 * linear(red) + 0.7152 * linear(green) + 0.0722 * linear(blue);
const contrastOnWhite = 1.05 / (luminance + 0.05);
assert.ok(contrastOnWhite >= 4.5, `completed-state contrast is only ${contrastOnWhite.toFixed(2)}:1`);

assert.match(
  css,
  /\.run-stage-done\s*\{[^}]*color:\s*var\(--solar-success\)[^}]*background:\s*var\(--solar-success-wash\)/s,
);
assert.match(
  css,
  /\.plan-card\.tone-complete\s*\{[^}]*border-color:\s*var\(--solar-success-line\)[^}]*background:\s*var\(--solar-success-wash\)/s,
);

console.log(`statusColors: completed state is distinct and ${contrastOnWhite.toFixed(2)}:1 on white`);
