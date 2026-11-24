import assert from "node:assert/strict"
import { test } from "node:test"
import { setTimeout as delay } from "node:timers/promises"
import { ChatSession } from "../src/chat"
import { isSidebarMessage } from "../src/protocol"
import { ChatFixture } from "./chat-fixture"

async function until(check: () => boolean) {
  const deadline = Date.now() + 5000
  while (!check()) { if (Date.now() > deadline) throw new Error("condition timed out"); await delay(10) }
}
async function withChat(run: (fixture: ChatFixture, chat: ChatSession, snapshots: any[], sent: () => number) => Promise<void>) {
  const fixture = new ChatFixture()
  fixture.password = "fixture-only"
  const address = await fixture.listen()
  const controller = new AbortController()
  const snapshots: any[] = []
  let sent = 0
  const chat = new ChatSession(address, fixture.password, "/tmp/workspace with spaces", (state) => snapshots.push(structuredClone(state)), () => undefined, () => sent++)
  const task = chat.run(controller.signal)
  try { await until(() => chat.state.ready); await run(fixture, chat, snapshots, () => sent) }
  finally { controller.abort(); await task; await fixture.close() }
}

test("validates chat IPC at the webview boundary", () => {
  for (const value of [{ type: "send", text: "hi" }, { type: "interrupt" }, { type: "permission", id: "per_1", decision: "reject" }, { type: "form", id: "frm_1", answer: { name: "yes", count: 2, checked: true, choices: ["a"] } }]) assert.ok(isSidebarMessage(value))
  for (const value of [{ type: "send", text: " " }, { type: "send", text: "a".repeat(100001) }, { type: "permission", id: "per_1", decision: "always" }, { type: "form", id: "f", answer: { bad: {} } }, { type: "form", id: "f", answer: { bad: NaN } }]) assert.ok(!isSidebarMessage(value))
})

test("subscribes before sending, creates at workspace, separates admission from completion, filters and streams", async () => {
  await withChat(async (fixture, chat, snapshots, sent) => {
    const create = fixture.calls.find((call) => call.path === "/api/session")!
    assert.deepEqual(create.body.location, { directory: "/tmp/workspace with spaces" })
    assert.ok(fixture.calls.findIndex((call) => call.path === "/api/event") < fixture.calls.indexOf(create))
    await chat.send("첫 메시지\n두 번째 줄")
    assert.equal(sent(), 1)
    assert.equal(chat.state.running, true)
    fixture.assistant()
    fixture.event("session.text.started", { sessionID: fixture.sessionID, assistantMessageID: "msg_assistant", ordinal: 0 })
    fixture.event("session.text.delta", { sessionID: "ses_other", assistantMessageID: "msg_foreign", ordinal: 0, delta: "SECRET" })
    fixture.event("session.text.delta", { sessionID: fixture.sessionID, assistantMessageID: "msg_assistant", ordinal: 0, delta: "안녕" })
    await until(() => JSON.stringify(chat.state.messages).includes("안녕"))
    fixture.event("session.text.delta", { sessionID: fixture.sessionID, assistantMessageID: "msg_assistant", ordinal: 0, delta: "하세요" })
    await until(() => JSON.stringify(chat.state.messages).includes("안녕하세요"))
    assert.ok(!JSON.stringify(snapshots).includes("SECRET"))
    await chat.send("should not send while running")
    assert.equal(fixture.calls.filter((call) => call.path.endsWith("/prompt")).length, 1)
    fixture.finish("안녕하세요")
    await until(() => !chat.state.running)
    assert.equal(chat.state.messages.filter((item) => item.id === "msg_assistant").length, 1)
    assert.equal(chat.state.messages.find((item) => item.id === "msg_assistant")!.blocks[0].text, "안녕하세요")
    assert.equal(chat.state.notice, undefined)
    assert.ok(fixture.calls.every((call) => call.auth === `Basic ${Buffer.from("opencode:fixture-only").toString("base64")}`))
  })
})

test("reports prompt admission failure without clearing the draft or retrying", async () => {
  await withChat(async (fixture, chat, _snapshots, sent) => {
    fixture.rejectPrompt = true
    await chat.send("retry manually")
    assert.equal(sent(), 0)
    assert.ok(chat.state.error?.includes("전송 결과"))
    assert.equal(chat.state.running, false)
    assert.equal(fixture.calls.filter((call) => call.path.endsWith("/prompt")).length, 1)
  })
})

test("keeps an instant answer arriving before HTTP admission without duplicates", async () => {
  await withChat(async (fixture, chat) => {
    fixture.onPrompt = () => { fixture.assistant(); fixture.event("session.text.delta", { sessionID: fixture.sessionID, assistantMessageID: "msg_assistant", ordinal: 0, delta: "fast" }); fixture.finish("fast") }
    await chat.send("instant")
    await until(() => !chat.state.running)
    assert.equal(chat.state.messages.filter((item) => item.role === "user").length, 1)
    assert.equal(chat.state.messages.filter((item) => item.role === "assistant").length, 1)
    assert.equal(chat.state.messages.find((item) => item.role === "assistant")!.blocks[0].text, "fast")
  })
})

test("reconnects the same session and recovers missed messages and pending requests", async () => {
  await withChat(async (fixture, chat) => {
    for (const stream of fixture.streams) stream.end()
    await until(() => !chat.state.ready)
    fixture.assistant("msg_missed", "disconnected answer")
    fixture.permissions = [{ id: "per_missed", sessionID: fixture.sessionID, action: "shell", resources: ["pwd"] }]
    fixture.forms = [{ id: "frm_missed", sessionID: fixture.sessionID, title: "Pick", fields: [{ key: "choice", type: "string" }] }]
    await until(() => chat.state.ready && chat.state.messages.some((item) => item.id === "msg_missed"))
    assert.equal(fixture.calls.filter((call) => call.path === "/api/session").length, 1)
    assert.equal(chat.state.permissions[0].id, "per_missed")
    assert.equal(chat.state.forms[0].id, "frm_missed")
  })
})

test("interrupt waits for admission; idle interrupt does nothing", async () => {
  await withChat(async (fixture, chat) => {
    await chat.interrupt()
    assert.ok(!fixture.calls.some((call) => call.path.endsWith("/interrupt")))
    let admit!: () => void
    fixture.onPrompt = () => new Promise<void>((resolve) => { admit = resolve })
    const sending = chat.send("slow admission")
    await until(() => !!admit)
    const cancelling = chat.interrupt()
    await delay(30)
    assert.ok(!fixture.calls.some((call) => call.path.endsWith("/interrupt")))
    admit()
    await Promise.all([sending, cancelling])
    assert.equal(fixture.calls.filter((call) => call.path.endsWith("/interrupt")).length, 1)
    assert.equal(chat.state.running, false)
  })
})

test("handles approval/rejection, tool failure, question reply/cancel and retry after failure", async () => {
  await withChat(async (fixture, chat) => {
    fixture.permissions = [{ id: "per_1", sessionID: fixture.sessionID, action: "shell", resources: ["pwd"] }]
    fixture.event("permission.asked", fixture.permissions[0])
    fixture.forms = [{ id: "frm_1", sessionID: fixture.sessionID, title: "Question", fields: [{ key: "choice", type: "string", required: true }] }]
    fixture.event("form.created", { form: fixture.forms[0] })
    await until(() => chat.state.permissions.length === 1 && chat.state.forms.length === 1)
    await chat.permission("per_foreign", "once")
    fixture.failReplies = true
    await chat.form("frm_1", { choice: "a" })
    assert.ok(chat.state.error)
    assert.equal(chat.state.forms.length, 1)
    fixture.failReplies = false
    await chat.form("frm_1", { choice: "a" })
    assert.equal(chat.state.forms.length, 0)
    await chat.permission("per_1", "once")
    fixture.permissions = [{ id: "per_2", sessionID: fixture.sessionID, action: "shell", resources: ["rm"] }]
    fixture.event("permission.asked", fixture.permissions[0])
    await until(() => chat.state.permissions.length === 1)
    await chat.permission("per_2", "reject")
    assert.deepEqual(fixture.calls.filter((call) => call.path.includes("/permission/")).map((call) => call.body.decision), ["once", "reject"])
    fixture.forms = [{ id: "frm_2", sessionID: fixture.sessionID, title: "Skip", fields: [{ key: "name", type: "string" }] }]
    fixture.event("form.created", { form: fixture.forms[0] })
    await until(() => chat.state.forms.length === 1)
    await chat.form("frm_2")
    assert.equal(chat.state.forms.length, 0)
    fixture.event("session.tool.input.started", { sessionID: fixture.sessionID, assistantMessageID: "msg_tool", id: "tool_1", name: "bash" })
    fixture.event("session.tool.failed", { sessionID: fixture.sessionID, assistantMessageID: "msg_tool", id: "tool_1", error: { message: "denied" } })
    await until(() => chat.state.messages.some((item) => item.id === "msg_tool" && item.blocks[0].status === "error"))
    assert.equal(chat.state.messages.find((item) => item.id === "msg_tool")!.blocks[0].text, "denied")
  })
})
