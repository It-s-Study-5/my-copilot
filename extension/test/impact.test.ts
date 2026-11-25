import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { runInNewContext } from "node:vm"
import { test } from "node:test"

// ponytail: keyboard.test.ts의 가짜 DOM을 최소로 줄이고 텍스트 노드(문자열)만 더했다.
class Node {
  constructor(readonly tagName = "div") {}
  hidden = false
  textContent = ""
  className = ""
  title = ""
  type = ""
  scrollTop = 0
  disabled = false
  dataset: Record<string, string> = {}
  children: (Node | string)[] = []
  listeners = new Map<string, ((event: any) => void)[]>()
  addEventListener(type: string, callback: (event: any) => void) { this.listeners.set(type, [...this.listeners.get(type) ?? [], callback]) }
  emit(type: string, event: any = {}) { for (const callback of this.listeners.get(type) ?? []) callback(event) }
  setAttribute() {}
  focus() {}
  // 실제 DOM처럼 DocumentFragment는 자식만 옮긴다.
  append(...nodes: (Node | string)[]) { for (const node of nodes) { this.children.push(...(typeof node !== "string" && node.tagName === "fragment" ? node.children : [node])) } }
  replaceChildren(...nodes: (Node | string)[]) { this.children = []; this.append(...nodes) }
  querySelector() { return undefined }
  querySelectorAll() { return [] }
  text(): string { return this.textContent + this.children.map((child) => typeof child === "string" ? child : child.text()).join("") }
  all(): Node[] { return this.children.flatMap((child) => typeof child === "string" ? [] : [child, ...child.all()]) }
  find(className: string) { return this.all().filter((node) => node.className.split(" ").includes(className)) }
}

function webview() {
  const nodes = new Map<string, Node>()
  const byId = (id: string) => { if (!nodes.has(id)) nodes.set(id, new Node()); return nodes.get(id)! }
  const document = Object.assign(new Node(), { getElementById: byId, querySelector: byId, createElement: (tag: string) => new Node(tag), createDocumentFragment: () => new Node("fragment") })
  const window = new Node()
  const ipc: any[] = []
  runInNewContext(readFileSync(new URL("../media/chat.js", import.meta.url), "utf8"), {
    document, window, console, acquireVsCodeApi: () => ({ postMessage: (message: any) => ipc.push(message), getState: () => ({}), setState() {} }),
  })
  const post = (data: any) => window.emit("message", { data: { type: "impact", id: 1, after: 0, file: "price.js", line: 3, ...data } })
  const chat = (count: number) => window.emit("message", { data: { type: "chat", ready: true, running: false, sending: false, cancelling: false, permissions: [], forms: [],
    messages: Array.from({ length: count }, (_, index) => ({ id: `m${index}`, role: "user", blocks: [{ id: "text:1", text: `질문 ${index}` }] })) } })
  return { messages: byId("messages"), ipc, post, chat }
}
const result = {
  target: { name: "calculatePrice", file: "price.js", start_line: 2, end_line: 5 },
  summary: "계산 결과가 주문 처리에 연결됩니다.",
  impacts: [
    { name: "createOrder", file: "order.js", start_line: 3, end_line: 9, depth: 1, relation: "direct",
      calls: [{ callee: "calculatePrice", line: 4, col: 18, kind: "call" }],
      facts: ["amount를 조건문(amount <= 0)에서 검사한다."], risk: "금액 검증을 확인해야 합니다.", risk_level: "high" },
    { name: "<module>", risk: ["라우터 동작을 확인해야 합니다."] },
  ],
  truncated: false,
  warnings: ["동명 함수 후보가 있습니다."],
  trace: [
    { step: 1, actor: "static", tool: "find_callers", args: { name: "calculatePrice", depth: 3 }, reason: null, result: "호출자 1개 확인" },
    { step: 2, actor: "agent", tool: "read_function", args: { name: "saveOrder" }, reason: "저장 방식을 확인한다.", result: "본문 확인" },
  ],
}

test("analysis renders as a chat message with only summary and risks", () => {
  const { messages, post } = webview()
  post({ status: "running" })
  assert.match(messages.text(), /price\.js:3 함수를 분석하는 중입니다/)

  post({ status: "done", result })
  const [article] = messages.find("impact")
  assert.ok(article.className.includes("message"))
  const text = article.text()
  for (const expected of ["분석 함수", "calculatePrice", "영향 후보 1개", "계산 결과가 주문 처리에 연결됩니다.", "동명 함수 후보가 있습니다.", "높음", "영향도 분석", "amount를 조건문(amount <= 0)에서 검사한다.", "금액 검증을 확인해야 합니다.", "<module>", "라우터 동작을 확인해야 합니다."]) {
    assert.ok(text.includes(expected), expected)
  }
  // 요청대로 빼는 것: facts 제목, 관계 태그, Agent 실행 기록, "AI 추정" 문구
  for (const hidden of ["확인된 사실", "정적 분석", "직접 호출", "파일 최상위", "Agent 실행 기록", "저장 방식을 확인한다.", "AI 추정"]) {
    assert.ok(!text.includes(hidden), hidden)
  }

  post({ status: "done", result: { error: { code: "NOT_IN_FUNCTION", message: "커서가 함수 안에 있지 않습니다." } } })
  assert.match(messages.text(), /커서가 함수 안에 있지 않습니다/)
  assert.equal(messages.find("impact").length, 1)
})

test("analysis stays between the chat messages it was run after", () => {
  const { messages, post, chat } = webview()
  chat(1)
  post({ status: "done", after: 1, result })
  chat(2) // 채팅이 갱신돼도 분석 결과는 첫 번째 메시지 뒤에 남는다.
  const order = messages.children.map((node) => typeof node === "string" ? node : node.className)
  assert.deepEqual(order, ["message user", "message assistant impact", "message user"])
})

test("AI failure shows only the engine notice without candidates", () => {
  const { messages, post } = webview()
  const notice = "AI 분석을 성공적으로 마치지 못했습니다. 모델 설정 또는 응답을 확인해야합니다."
  post({ status: "done", result: { ...result, summary: null, warnings: [notice] } })
  const text = messages.text()
  assert.ok(text.includes("calculatePrice") && text.includes(notice))
  assert.ok(!text.includes("AI 요약을 만들지 못했습니다") && !text.includes("영향 후보"))
  assert.equal(messages.find("impact-item").length, 0)
  assert.equal(messages.find("plain").length, 1)
})

test("links post open messages", () => {
  const { messages, ipc, post } = webview()
  post({ status: "done", result })
  messages.find("link").find((node) => node.text() === "order.js:4")!.emit("click")
  assert.deepEqual(ipc.at(-1), { type: "open", file: "order.js", line: 4 })
})

test("malformed result shows an error instead of breaking the webview", () => {
  const { messages, post } = webview()
  post({ status: "done", result: { summary: "x" } })
  assert.match(messages.text(), /분석 결과 형식을 읽을 수 없습니다/)
})
