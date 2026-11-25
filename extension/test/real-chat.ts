import assert from "node:assert/strict"
import { createServer } from "node:http"
import { execFile } from "node:child_process"
import { mkdtemp, mkdir, rm } from "node:fs/promises"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { promisify } from "node:util"
import { setTimeout as delay } from "node:timers/promises"
import { OpenCode } from "@opencode/client"
import { ChatSession } from "../src/chat"
import { ensureLocalServer } from "../src/local-server"

// Real OpenCode server and runner; deterministic local provider instead of paid model credentials.
const command = process.argv.slice(2)
if (!command.length) command.push("opencode")
const execute = promisify(execFile)
const root = await mkdtemp(join(tmpdir(), "opencode-real-chat-"))
for (const name of ["config", "state", "data", "cache", "project"]) await mkdir(join(root, name))
for (const name of ["config", "state", "data", "cache"]) process.env[`XDG_${name.toUpperCase()}_HOME`] = join(root, name)
for (const name of ["OPENCODE_CONFIG_DIR", "OPENCODE_CONFIG", "OPENCODE_PASSWORD", "OPENCODE_SERVER_PASSWORD"]) delete process.env[name]
process.env.OPENCODE_CONFIG_PROJECT_DISABLE = "1"
process.env.OPENCODE_DISABLE_MODELS_FETCH = "1"
let providerCalls = 0
let cancellationRequests = 0
const provider = createServer(async (request, response) => {
  let raw = ""
  for await (const chunk of request) raw += chunk
  providerCalls++
  if (raw.includes("CHAT_QA_ERROR")) { response.writeHead(400, { "Content-Type": "application/json" }); response.end(JSON.stringify({ error: { message: "QA provider error", type: "invalid_request_error" } })); return }
  response.writeHead(200, { "Content-Type": "text/event-stream" })
  const chunk = (content: string, finish: string | null = null) => response.write(`data: ${JSON.stringify({ id: "chatcmpl-qa", object: "chat.completion.chunk", created: 1, model: "chat", choices: [{ index: 0, delta: { content }, finish_reason: finish }] })}\n\n`)
  chunk("실제 ")
  if (raw.includes("CHAT_QA_CANCEL")) {
    cancellationRequests++
    const timer = setInterval(() => response.write(": keepalive\n\n"), 1000)
    response.on("close", () => clearInterval(timer))
    return
  }
  await delay(300)
  chunk("OpenCode 서버 응답")
  chunk("", "stop")
  response.end("data: [DONE]\n\n")
})
await new Promise<void>((resolve) => provider.listen(0, "127.0.0.1", resolve))
const endpoint = provider.address()
assert.ok(endpoint && typeof endpoint === "object")
process.env.OPENCODE_CONFIG_CONTENT = JSON.stringify({
  model: "qa/chat", snapshots: false, automations: false,
  permissions: [{ action: "*", resource: "*", effect: "ask" }],
  providers: { qa: { package: "@opencode/ai/providers/openai-compatible", settings: { baseURL: `http://127.0.0.1:${endpoint.port}/v1`, apiKey: "fixture-only" }, models: { chat: { capabilities: { tools: true, input: ["text"], output: ["text"] }, limit: { context: 32000, output: 1000 } } } } },
})
const run = async (args: string[]) => (await execute(command[0], [...command.slice(1), ...args], { timeout: 130000, maxBuffer: 65536 })).stdout.trim()
const controller = new AbortController()
let task: Promise<void> | undefined
async function until(check: () => boolean, hint: string) {
  const deadline = Date.now() + 30000
  while (!check()) { if (Date.now() > deadline) throw new Error(`Timed out: ${hint}`); await delay(25) }
}
try {
  const probe = createServer();
  await new Promise<void>((resolve) => probe.listen(0, "127.0.0.1", resolve));
  const free = probe.address();
  assert.ok(free && typeof free === "object");
  await new Promise<void>((resolve) => probe.close(() => resolve()));
  await run(["service", "set", "port", String(free.port)])
  const local = await ensureLocalServer(controller.signal, command)
  const api = OpenCode.make({ baseUrl: local.address, headers: { Authorization: `Basic ${Buffer.from(`opencode:${local.password}`).toString("base64")}` } })
  let streamed = false
  const chat = new ChatSession(local.address, local.password, join(root, "project"), (state) => {
    if (state.messages.some((message) => message.blocks.some((block) => block.text === "실제 "))) streamed = true
  }, (_connected, message) => { if (!message.includes("연결되었습니다")) console.log(message) })
  task = chat.run(controller.signal)
  await until(() => chat.state.ready, "session ready")
  await chat.send("CHAT_QA_HELLO")
  await until(() => !chat.state.running && chat.state.messages.some((message) => message.blocks.some((block) => block.text === "실제 OpenCode 서버 응답")), `answer: ${chat.state.error ?? "none"}`)
  assert.ok(streamed, "must display partial SSE text before completion")
  assert.equal(chat.state.messages.filter((message) => message.role === "user").length, 1)
  const sessionID = (chat as unknown as { sessionID: string }).sessionID
  const approval = api.permission.create({ sessionID, action: "qa", resources: ["safe-test"] })
  await until(() => chat.state.permissions.length > 0, "permission request")
  await chat.permission(chat.state.permissions[0].id, "once")
  assert.equal((await approval).effect, "ask")
  assert.equal((await api.permission.list({ sessionID })).length, 0)
  const denied = api.permission.create({ sessionID, action: "qa", resources: ["deny-test"] })
  await until(() => chat.state.permissions.length > 0, "deny request")
  await chat.permission(chat.state.permissions[0].id, "reject")
  assert.equal((await denied).effect, "ask")
  assert.equal((await api.permission.list({ sessionID })).length, 0)
  const form = await api.session.form.create({ sessionID, title: "QA question", fields: [{ key: "answer", type: "string", required: true }] })
  await until(() => chat.state.forms.some((item) => item.id === form.id), "question")
  await chat.form(form.id, { answer: "yes" })
  assert.equal((await api.session.form.get({ sessionID, formID: form.id })).state.status, "answered")
  await chat.send("CHAT_QA_CANCEL")
  await until(() => cancellationRequests > 0, "provider cancellation request")
  await chat.interrupt()
  await until(() => !chat.state.running, "interrupted")
  await chat.send("CHAT_QA_ERROR")
  await until(() => !chat.state.running && !!chat.state.error, "provider error")
  console.log(JSON.stringify({ realServer: true, provider: "local deterministic fixture", workspaceSession: true, streaming: streamed, completion: true, permissionAllow: true, permissionReject: true, question: true, interrupt: true, error: true, providerCalls }, null, 2))
} finally {
  controller.abort()
  await task
  await run(["service", "stop"])
  provider.closeAllConnections()
  await new Promise<void>((resolve) => provider.close(() => resolve()))
  await rm(root, { recursive: true, force: true })
}
