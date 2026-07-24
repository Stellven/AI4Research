import { access } from "node:fs/promises";
import { extname } from "node:path";
import { fileURLToPath } from "node:url";

/**
 * Minimal loader for executing the repository's extensionless TypeScript ESM
 * imports with Node 24's built-in type transformation. It is intentionally
 * limited to relative imports and never rewrites package or built-in modules.
 */
export async function resolve(specifier, context, nextResolve) {
  if (specifier.startsWith(".") && !extname(specifier)) {
    for (const suffix of [".ts", ".js", ".mjs"]) {
      const candidate = new URL(`${specifier}${suffix}`, context.parentURL);
      try {
        await access(fileURLToPath(candidate));
        return { shortCircuit: true, url: candidate.href };
      } catch {
        // Try the next supported local extension.
      }
    }
  }
  return nextResolve(specifier, context);
}
