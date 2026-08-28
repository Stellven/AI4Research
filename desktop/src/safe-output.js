"use strict";

const CLOSED_OUTPUT_CODES = new Set(["EPIPE", "EOF", "ERR_STREAM_DESTROYED"]);

function isClosedOutputError(error) {
  const code = String((error && error.code) || "").toUpperCase();
  const message = String((error && error.message) || error || "").toUpperCase();
  return CLOSED_OUTPUT_CODES.has(code) || /\b(?:WRITE )?EOF\b|BROKEN PIPE/.test(message);
}

function guardOutputStream(stream, onError = () => {}) {
  const state = { writable: Boolean(stream && typeof stream.on === "function") };
  if (!state.writable) return state;
  stream.on("error", (error) => {
    if (isClosedOutputError(error)) state.writable = false;
    try {
      onError(error, state);
    } catch {}
  });
  return state;
}

module.exports = { guardOutputStream, isClosedOutputError };
