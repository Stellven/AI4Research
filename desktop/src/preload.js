// Minimal, secure preload. contextIsolation is on; we expose nothing yet.
// Place to bridge native <-> renderer later (e.g. a "restart backend" button).
const { contextBridge } = require("electron");

const rendererErrors = [];
function rememberRendererError(value) {
  const message = String(value || "unknown renderer error").slice(0, 1000);
  rendererErrors.push(message);
  if (rendererErrors.length > 20) rendererErrors.shift();
}

window.addEventListener("error", (event) => {
  rememberRendererError(event.error?.stack || event.message);
});
window.addEventListener("unhandledrejection", (event) => {
  rememberRendererError(event.reason?.stack || event.reason);
});

contextBridge.exposeInMainWorld("solarDesktop", {
  version: "0.1.0",
  selftestDiagnostics: () => ({ rendererErrors: rendererErrors.slice() }),
});
