import { createServer, type ServerResponse } from "node:http"

// Transport fixture only: no model is called.
export class ChatFixture {
  readonly sessionID = "ses_fixture"
  readonly calls: { path: string; method: string; body: any; auth?: string }[] = []
  readonly streams = new Set<ServerResponse>()
  messages: any[] = []
  permissions: any[] = []
  forms: any[] = []
  running = false
  address = ""
  password?: string
  agent?: string
  model?: { id: string; providerID: string }
  catalogReady = true
  defaultAgent = "build"
  modelCatalog = [
    { id: "gpt-6.2-sol", providerID: "openai", enabled: true },
    { id: "gpt-6-luna", providerID: "openai", enabled: true },
    { id: "gpt-6.2-astra", providerID: "openai", enabled: false },
    { id: "gpt-6.2-sol", providerID: "amazon-bedrock", enabled: true },
    { id: "gpt-6-cyber", providerID: "openai", enabled: true },
    { id: "gpt-image-2.6-flare", providerID: "openai", enabled: true, type: "image" },
    { id: "gpt-5.4", providerID: "openai", enabled: true, status: "deprecated" },
  ].map((model, index) => ({ status: "active", type: "chat", time: { released: 100 - index }, capabilities: { output: ["text"] }, ...model }))
  defaultModel: { id: string; providerID: string; enabled: boolean } | null = null
  onOpenAIKey?: (key: string) => boolean
  onPrompt?: (text: string, response: ServerResponse) => void | Promise<void>
  failReplies = false
  rejectPrompt = false
  onReply?: () => void
  historyReads = 0
  historyDelay = 0
  readonly server = createServer(async (request, response) => {
    const url = new URL(request.url!, "http://localhost")
    const path = url.pathname
    let raw = ""
    for await (const chunk of request) raw += chunk
    const body = raw ? JSON.parse(raw) : undefined
    this.calls.push({ path, method: request.method!, body, auth: request.headers.authorization })
    if (this.password && request.headers.authorization !== `Basic ${Buffer.from(`opencode:${this.password}`).toString("base64")}`) { response.writeHead(401).end(); return }
    if (path.endsWith("/api/event")) {
      response.writeHead(200, { "Content-Type": "text/event-stream" })
      this.streams.add(response)
      this.event("server.connected", {})
      response.on("close", () => this.streams.delete(response))
      return
    }
    response.setHeader("Content-Type", "application/json")
    const json = (value: unknown) => response.end(JSON.stringify(value))
    if (path.endsWith("/api/info")) return json({ version: "2.4.0-chat-fixture", pid: process.pid, urls: [this.address], paths: { tmp: "/tmp" } })
    if (path.endsWith("/api/agent")) return json({ data: this.catalogReady ? [{ id: this.defaultAgent, mode: "primary", hidden: false }] : [] })
    if (path.endsWith("/api/model")) return json({ data: this.modelCatalog })
    if (path.endsWith("/api/model/default")) return json({ data: this.defaultModel })
    if (path.endsWith("/api/integration/openai/connect/key") && request.method === "POST") {
      if (!this.onOpenAIKey?.(body.key)) { response.writeHead(400); return json({ message: "fixture rejected credential" }) }
      response.writeHead(204).end()
      return
    }
    if (path.endsWith("/api/session") && request.method === "POST") {
      this.model = body.model
      return json({ data: { id: this.sessionID, agent: this.agent, model: this.model } })
    }
    if (path.endsWith(`/api/session/${this.sessionID}`)) {
      return json({ data: { id: this.sessionID, agent: this.agent, model: this.model } })
    }
    if (path.endsWith(`/api/session/${this.sessionID}/model`) && request.method === "POST") {
      this.model = body.model
      this.event("session.model.selected", { sessionID: this.sessionID, model: body.model })
      response.writeHead(204).end()
      return
    }
    if (path.endsWith("/api/session/active")) return json({ data: this.running ? { [this.sessionID]: { type: "running" } } : {} })
    if (path.endsWith("/message")) {
      this.historyReads++
      if (url.searchParams.has("cursor") && url.searchParams.has("order")) { response.writeHead(400); return json({ message: "cursor and order cannot be combined" }) }
      const data = structuredClone(this.messages)
      if (this.historyDelay) await new Promise((resolve) => setTimeout(resolve, this.historyDelay))
      return json({ data, cursor: {} })
    }
    if (path.endsWith("/permission") && request.method === "GET") return json({ data: this.permissions })
    if (path.endsWith("/form") && request.method === "GET") return json({ data: this.forms })
    if (path.endsWith("/prompt")) {
      if (this.rejectPrompt) { response.writeHead(400); return json({ message: "rejected" }) }
      this.messages.push({ id: `msg_user${this.messages.length}`, type: "user", text: body.text, time: { created: Date.now() } })
      this.running = true
      this.event("session.execution.started", { sessionID: this.sessionID })
      if (this.onPrompt) await this.onPrompt(body.text, response)
      if (!response.writableEnded) json({ data: { id: "msg_inbox" } })
      return
    }
    if (path.endsWith("/interrupt")) { this.running = false; this.event("session.execution.interrupted", { sessionID: this.sessionID, reason: "user" }); return json({ interrupted: true }) }
    if (path.includes("/permission/") && path.endsWith("/reply")) {
      if (this.failReplies) { response.writeHead(500); return json({ message: "fixture reply failed" }) }
      const id = path.split("/").at(-2)
      this.permissions = this.permissions.filter((item) => item.id !== id)
      this.event("permission.replied", { sessionID: this.sessionID, requestID: id, reply: body.decision })
      this.onReply?.()
      response.writeHead(204).end(); return
    }
    if (path.includes("/form/") && (path.endsWith("/reply") || request.method === "DELETE")) {
      if (this.failReplies) { response.writeHead(500); return json({ message: "fixture invalid answer" }) }
      const id = path.split("/").at(request.method === "DELETE" ? -1 : -2)
      this.forms = this.forms.filter((item) => item.id !== id)
      this.event(request.method === "DELETE" ? "form.cancelled" : "form.replied", { id, sessionID: this.sessionID, answer: body?.answer })
      this.onReply?.()
      response.writeHead(204).end(); return
    }
    response.writeHead(404); json({ message: `Unknown fixture route: ${path}` })
  })
  event(type: string, data: any) {
    const event = { id: `evt_${crypto.randomUUID()}`, type, created: Date.now(), data }
    for (const response of this.streams) response.write(`data: ${JSON.stringify(event)}\n\n`)
  }
  assistant(id = "msg_assistant", text = "") {
    const message = { id, type: "assistant", time: { created: Date.now() }, agent: "build", model: { id: "fixture", providerID: "fixture" }, content: [{ type: "text", text }] }
    this.messages.push(message)
    return message
  }
  finish(text = "안녕하세요. 테스트 응답입니다.", id = "msg_assistant") {
    let message = this.messages.find((item) => item.id === id)
    if (!message) message = this.assistant(id)
    message.content[0].text = text
    this.event("session.text.ended", { sessionID: this.sessionID, assistantMessageID: id, ordinal: 0, text })
    this.running = false
    this.event("session.execution.succeeded", { sessionID: this.sessionID })
    this.event("session.idle", { sessionID: this.sessionID })
  }
  async listen(port = 0) {
    await new Promise<void>((resolve, reject) => { this.server.once("error", reject); this.server.listen(port, "127.0.0.1", resolve) })
    const address = this.server.address()
    if (!address || typeof address === "string") throw new Error("fixture did not listen")
    this.address = `http://127.0.0.1:${address.port}`
    return this.address
  }
  async close() {
    for (const response of this.streams) response.end()
    this.server.closeAllConnections()
    await new Promise<void>((resolve) => this.server.close(() => resolve()))
  }
}
