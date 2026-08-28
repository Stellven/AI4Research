"use strict";

const assert = require("assert");
const { EventEmitter } = require("events");
const { guardOutputStream, isClosedOutputError } = require("./src/safe-output");

assert.equal(isClosedOutputError(Object.assign(new Error("write EOF"), { code: "EOF" })), true);
assert.equal(isClosedOutputError(Object.assign(new Error("broken pipe"), { code: "EPIPE" })), true);
assert.equal(isClosedOutputError(new Error("unrelated")), false);

const stream = new EventEmitter();
const observed = [];
const state = guardOutputStream(stream, (error) => observed.push(error.code));
assert.equal(state.writable, true);
stream.emit("error", Object.assign(new Error("write EOF"), { code: "EOF" }));
assert.equal(state.writable, false);
assert.deepEqual(observed, ["EOF"]);

console.log("safe-output tests passed");
