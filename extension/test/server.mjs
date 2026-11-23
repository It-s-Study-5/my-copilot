// Local HTTP fixture for GUI verification; this does not run OpenCode or a model.
import assert from "node:assert/strict";
import { createServer } from "node:http";

const password = "test-only";
const authorization = `Basic ${Buffer.from(`opencode:${password}`).toString("base64")}`;
assert.equal(Buffer.from(authorization.slice(6), "base64").toString(), "opencode:test-only");

const server = createServer((request, response) => {
  response.setHeader("Content-Type", "application/json");
  if (request.url !== "/api/info") {
    response.writeHead(404).end("{}");
    return;
  }
  if (request.headers.authorization !== authorization) {
    response.writeHead(401).end(JSON.stringify({ message: "Test password required" }));
    return;
  }
  response.end(JSON.stringify({
    version: "2.4.0-test-fixture",
    pid: process.pid,
    urls: [],
    paths: { tmp: "/tmp/opencode-test-fixture" },
  }));
});

server.listen(41960, "127.0.0.1", () => {
  console.log("GUI test fixture: http://127.0.0.1:41960 (password: test-only)");
});
server.on("error", (error) => {
  console.error(error.message);
  process.exitCode = 1;
});
process.on("SIGTERM", () => {
  server.closeAllConnections();
  server.close();
});
