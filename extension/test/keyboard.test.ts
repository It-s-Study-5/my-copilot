import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { runInNewContext } from "node:vm"
import { test } from "node:test"

class Target {
  constructor(readonly tagName = "div") {}
  value = ""
  disabled = false
  checked = false
  focused = false
  focusCount = 0
  hidden = false
  textContent = ""
  dataset: Record<string, string> = {}
  className = ""
  scrollHeight = 1000
  scrollTop = 800
  clientHeight = 200
  children: Target[] = []
  parent?: Target
  listeners = new Map<string, ((event: any) => void)[]>()
  addEventListener(type: string, callback: (event: any) => void) { this.listeners.set(type, [...this.listeners.get(type) ?? [], callback]) }
  emit(type: string, event: any = {}) { for (const callback of this.listeners.get(type) ?? []) callback(event) }
  setAttribute() {}
  focus() { this.focused = true; this.focusCount++ }
  append(...nodes: Target[]) {
    for (const node of nodes) {
      if (node.tagName === "fragment") { this.append(...node.children); continue }
      if (node.parent) node.parent.children = node.parent.children.filter((child) => child !== node)
      node.parent = this
      this.children.push(node)
    }
  }
  replaceChildren(...nodes: Target[]) { this.children.forEach((node) => { node.parent = undefined }); this.children = []; this.append(...nodes) }
  querySelectorAll(selector: string): Target[] {
    return this.children.flatMap((node) => [
      ...(selector.startsWith(".") ? node.className.split(" ").includes(selector.slice(1)) : node.tagName === selector) ? [node] : [],
      ...node.querySelectorAll(selector),
    ])
  }
  querySelector(selector: string) { return this.querySelectorAll(selector)[0] }
}
function webview() {
  const nodes = new Map<string, Target>()
  const byId = (id: string) => { if (!nodes.has(id)) nodes.set(id, new Target()); return nodes.get(id)! }
  const document = Object.assign(new Target(), { getElementById: byId, querySelector: byId,
    createElement: (tag: string) => new Target(tag), createDocumentFragment: () => new Target("fragment") })
  const window = new Target()
  const ipc: any[] = []
  let draft = ""
  runInNewContext(readFileSync(new URL("../media/chat.js", import.meta.url), "utf8"), {
    document, window, acquireVsCodeApi: () => ({ postMessage: (message: any) => ipc.push(message), getState: () => ({ draft }), setState: (state: any) => { draft = state.draft } }),
  })
  const prompt = byId("prompt")
  const state = (running = false, patch = {}) => window.emit("message", { data: { type: "chat", ready: true, running, sending: false, cancelling: false,
    model: { providerID: "openai", id: "gpt-6.2-sol" }, messages: [], permissions: [], forms: [], ...patch } })
  const key = (key: string, extra = {}) => {
    let prevented = false
    document.emit("keydown", { target: prompt, key, preventDefault: () => { prevented = true }, ...extra })
    return prevented
  }
  return { prompt, ipc, key, state, document, window, byId, draft: () => draft }
}

test("shows the current session agent and model, labels replies and opens the model picker", () => {
  const ui = webview()
  ui.state(false, { agent: "plan", model: { id: "chat", providerID: "provider" },
    messages: [{ id: "answer", role: "assistant", agent: "build", blocks: [{ text: "답변" }] }] })
  assert.equal(ui.byId("active-agent").textContent, "에이전트 · plan")
  assert.equal(ui.byId("pick-model").textContent, "provider/chat")
  assert.equal(ui.byId("messages").querySelector("strong")?.textContent, "build")
  ui.byId("pick-model").emit("click")
  assert.equal(ui.ipc.at(-1)?.type, "pickModel")
  ui.state(true)
  assert.equal(ui.byId("pick-model").disabled, true)
})

test("renders reply text and errors without intermediate agent or tool entries", () => {
  const ui = webview()
  const messages = ui.byId("messages")
  ui.state(true, { messages: [{ role: "assistant", agent: "build", blocks: [] }] })
  assert.equal(messages.children[0], ui.byId("empty-state"))
  ui.state(false, { messages: [
    { role: "user", blocks: [{ text: "질문" }] },
    { role: "assistant", agent: "build", blocks: [{ text: "", tool: "skill", status: "completed" }] },
    { role: "assistant", agent: "build", blocks: [{ text: "tool output", tool: "execute" }, { text: "답변" }] },
    { role: "assistant", agent: "build", blocks: [{ text: "권한 없음", tool: "execute", status: "error" }], error: "응답 실패" },
  ] })
  assert.equal(messages.children.length, 3)
  assert.deepEqual(messages.querySelectorAll(".message-text").map((item) => item.textContent), ["질문", "답변"])
  assert.deepEqual(messages.querySelectorAll(".error").map((item) => item.textContent), ["execute 실패 · 권한 없음", "응답 실패"])
})

test("shows the fallback model and notice before sending", () => {
  const ui = webview()
  const notice = "GPT-6.2 Sol을 사용할 수 없어 서버 기본 모델 qa/chat을 사용합니다."
  ui.prompt.value = "hello"
  ui.state(false, { model: { providerID: "qa", id: "chat" }, modelNotice: notice, pickingModel: true })
  assert.equal(ui.byId("pick-model").textContent, "qa/chat")
  assert.equal(ui.byId("model-notice").textContent, notice)
  assert.equal(ui.byId("model-notice").hidden, false)
  ui.key("Enter")
  assert.ok(!ui.ipc.some((item) => item.type === "send"))
  ui.state(false, { model: undefined, modelNotice: "사용할 모델 없음" })
  ui.key("Enter")
  assert.ok(!ui.ipc.some((item) => item.type === "send"))
})

test("Enter sends once, Shift+Enter keeps native newline, Esc cancels only active work and keeps drafts", () => {
  const ui = webview()
  ui.state()
  ui.prompt.value = "hello\nworld"
  assert.equal(ui.key("Enter", { shiftKey: true }), false)
  assert.equal(ui.ipc.filter((item) => item.type === "send").length, 0)
  assert.equal(ui.key("Enter"), true)
  ui.key("Enter")
  assert.deepEqual(JSON.parse(JSON.stringify(ui.ipc.at(-1))), { type: "send", text: "hello\nworld" })
  assert.equal(ui.ipc.filter((item) => item.type === "send").length, 1)
  ui.window.emit("message", { data: { type: "sent" } })
  assert.equal(ui.prompt.value, "")
  ui.prompt.value = "keep my draft"
  ui.state()
  assert.equal(ui.key("Escape"), false)
  ui.state(true)
  assert.equal(ui.key("Escape"), true)
  ui.key("Escape")
  assert.equal(ui.ipc.filter((item) => item.type === "interrupt").length, 1)
  assert.equal(ui.prompt.value, "keep my draft")
})

test("IME Enter/Esc never sends or interrupts, including keyCode 229; edits made during send survive admission", () => {
  const ui = webview()
  ui.state()
  ui.prompt.value = "한글"
  ui.prompt.emit("compositionstart")
  assert.equal(ui.key("Enter"), false)
  ui.state(true)
  assert.equal(ui.key("Escape"), false)
  ui.prompt.emit("compositionend")
  ui.state()
  assert.equal(ui.key("Enter", { isComposing: true }), false)
  assert.equal(ui.key("Enter", { keyCode: 229 }), false)
  assert.equal(ui.ipc.filter((item) => ["send", "interrupt"].includes(item.type)).length, 0)
  ui.key("Enter")
  ui.prompt.value = "새 초안"
  ui.prompt.emit("input")
  ui.window.emit("message", { data: { type: "sent" } })
  assert.equal(ui.prompt.value, "새 초안")
  assert.equal(ui.draft(), "새 초안")
})

test("permission response replaces the composer, requires an explicit choice and preserves the draft", () => {
  const ui = webview()
  ui.prompt.value = "작성 중인 초안"
  const permission = { id: "per_composer", action: "shell", resources: ["pwd"], message: "작업 폴더 확인" }
  ui.state(true, { permissions: [permission] })
  assert.equal(ui.byId("composer").hidden, true)
  const card = ui.byId("requests").children[0]
  assert.equal(card.children[0].textContent, "권한 확인")
  const confirm = card.querySelectorAll("button")[0]
  assert.ok(confirm.disabled)
  const submit = () => card.emit("submit", { preventDefault() {} })
  submit()
  assert.equal(ui.ipc.filter((item) => item.type === "permission").length, 0)
  const [allow, reject] = card.querySelectorAll("input")
  assert.equal(allow.focused, true)
  assert.equal(allow.checked, false, "focus must not grant or preselect permission")
  allow.checked = true
  allow.emit("change")
  assert.equal(confirm.disabled, false)
  assert.equal(ui.ipc.filter((item) => item.type === "permission").length, 0, "selection must not send before confirmation")
  ui.state(true, { permissions: [permission] })
  assert.equal(ui.byId("requests").children[0], card, "stream updates must keep the selected option")
  submit()
  allow.checked = false
  reject.checked = true
  reject.emit("change")
  submit()
  assert.deepEqual(JSON.parse(JSON.stringify(ui.ipc.slice(-2))), [
    { type: "permission", id: "per_composer", decision: "once" },
    { type: "permission", id: "per_composer", decision: "reject" },
  ])
  ui.state(true, { permissions: [permission], ready: false })
  assert.equal(ui.byId("composer").hidden, true)
  assert.ok(ui.byId("requests").querySelectorAll("button").every((node) => node.disabled))
  assert.ok(ui.byId("requests").querySelectorAll("input").every((node) => node.disabled))
  ui.state()
  assert.equal(ui.byId("requests").children.length, 0)
  assert.equal(ui.byId("composer").hidden, false)
  assert.equal(ui.prompt.value, "작성 중인 초안")
  assert.equal(ui.prompt.focused, true)
})

test("question forms also replace the composer and restore it after answering", () => {
  const ui = webview()
  ui.prompt.value = "keep draft"
  ui.state(true, { forms: [{ id: "frm_question", title: "추가 질문", fields: [{ key: "note", type: "string" }] }] })
  assert.equal(ui.byId("composer").hidden, true)
  ui.key("Enter")
  assert.equal(ui.ipc.filter((item) => item.type === "send").length, 0)
  ui.state()
  assert.equal(ui.byId("composer").hidden, false)
  assert.equal(ui.prompt.value, "keep draft")
})

test("permission autofocus runs for a new request or reconnect, without stealing focus on stream updates", () => {
  const ui = webview()
  const permission = { id: "per_focus", action: "shell", resources: ["pwd"] }
  ui.state(true, { permissions: [permission], ready: false })
  assert.equal(ui.byId("requests").querySelectorAll("input")[0].focusCount, 0)
  ui.state(true, { permissions: [permission] })
  const [allow, reject] = ui.byId("requests").querySelectorAll("input")
  assert.equal(allow.focusCount, 1)
  reject.focus()
  ui.state(true, { permissions: [permission], messages: [{ id: "msg_stream", role: "assistant", blocks: [{ text: "new chunk" }] }] })
  assert.equal(allow.focusCount, 1, "stream updates must not refocus the first option")
  assert.equal(reject.focusCount, 1)
  ui.state(true, { permissions: [{ ...permission, id: "per_next" }] })
  assert.equal(ui.byId("requests").querySelectorAll("input")[0].focusCount, 1)
  ui.state(true, { permissions: [{ ...permission, id: "per_next" }], ready: false })
  assert.equal(ui.byId("requests").querySelectorAll("input")[0].focusCount, 0)
  ui.state(true, { permissions: [{ ...permission, id: "per_next" }] })
  assert.equal(ui.byId("requests").querySelectorAll("input")[0].focusCount, 1)
})
