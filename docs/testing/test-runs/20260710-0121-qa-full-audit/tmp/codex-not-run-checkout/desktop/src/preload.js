// Minimal, secure preload. contextIsolation is on; we expose nothing yet.
// Place to bridge native <-> renderer later (e.g. a "restart backend" button).
const { contextBridge } = require("electron");

contextBridge.exposeInMainWorld("solarDesktop", {
  version: "0.1.0",
});
