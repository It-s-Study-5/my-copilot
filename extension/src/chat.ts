import { OpenCode, type OpenCodeEvent, type OpenCodeClient, type ModelInfo, type ModelRef, type SessionInfo, type SessionMessageInfo } from "@opencode/client";
import { setTimeout as delay } from "node:timers/promises";
import type { Answer, ChatMessage, ChatState } from "./protocol";

const DEFAULT_MODEL: ModelRef = { providerID: "openai", id: "gpt-6.2-sol" };
const GPT_CHAT_ID = /^gpt-\d+(?:\.\d+)*(?:o)?(?:-(?:astra|sol|terra|luna|mini|nano|pro|codex))*$/;

function isGPTChatModel(model: ModelInfo) {
  return model.enabled && model.providerID === DEFAULT_MODEL.providerID && GPT_CHAT_ID.test(model.id) &&
    (model.type ?? "chat") === "chat" && model.status === "active" &&
    model.capabilities.output.some((type) => type.startsWith("text"));
}

function sameModel(left: ModelRef, right: ModelRef) { return left.id === right.id && left.providerID === right.providerID; }

export class ChatSession {
  readonly state: ChatState = { type: "chat", ready: false, running: false, sending: false, cancelling: false, messages: [], permissions: [], forms: [] };
  private api: OpenCodeClient;
  private sessionID?: string;
  private sessionDirectory?: string;
  private loadingAgent?: Promise<void>;
  private signal?: AbortSignal;
  private refreshing?: Promise<void>;
  private buffered?: OpenCodeEvent[];
  private admission?: Promise<unknown>;
  private readonly replying = new Set<string>();
  private stream?: AbortController;
  private awaitingExecution = false;

  constructor(private readonly address: string, password: string | undefined, private readonly directory: string | undefined,
    private readonly publish: (state: ChatState) => void, private readonly connection: (connected: boolean, message: string) => void,
    private readonly sent: () => void = () => undefined) {
    this.api = this.client(password);
  }

  private client(password?: string) {
    return OpenCode.make({ baseUrl: this.address, headers: password ? { Authorization: `Basic ${Buffer.from(`opencode:${password}`).toString("base64")}` } : undefined,
      fetch: (input, init) => fetch(input, { ...init, redirect: "error" }) });
  }

  authenticate(password?: string) { this.api = this.client(password); }

  private emit() { if (!this.signal?.aborted) { this.publish(this.state); } }
  private options() { return { signal: AbortSignal.any([this.signal!, AbortSignal.timeout(15_000)]) }; }

  async run(signal: AbortSignal) {
    this.signal = signal;
    while (!signal.aborted) {
      const stream = new AbortController();
      this.stream = stream;
      const combined = AbortSignal.any([signal, stream.signal]);
      let reader: Promise<void> | undefined;
      try {
        this.state.ready = false;
        this.emit();
        const iterator = this.api.event.subscribe({ signal: combined })[Symbol.asyncIterator]();
        const timeout = setTimeout(() => stream.abort(), 10_000);
        try {
          const first = await iterator.next();
          if (first.done || first.value.type !== "server.connected") { throw new Error("이벤트 구독을 시작할 수 없습니다."); }
        } finally { clearTimeout(timeout); }
        this.buffered = [];
        reader = (async () => {
          for (;;) {
            const next = await iterator.next();
            if (next.done) { throw new Error("서버 이벤트 연결이 끊어졌습니다."); }
            if (this.buffered) { this.buffered.push(next.value); }
            else { this.event(next.value); }
          }
        })();
        // Observe immediately: disconnects during initial history loading must not become unhandled rejections.
        void reader.catch(() => stream.abort());
        let session = this.sessionID ? await this.api.session.get({ sessionID: this.sessionID }, this.options()) : undefined;
        const needsModel = !session?.model;
        const model = session?.model ?? await this.initialModel(combined);
        if (!session) {
          session = await this.api.session.create({ location: this.location, model }, this.options());
        } else if (needsModel && model) {
          await this.api.session.switchModel({ sessionID: session.id, model }, this.options());
        }
        this.sessionID = session.id;
        this.sessionDirectory = session.location?.directory ?? this.directory;
        if (!this.state.sending) { this.awaitingExecution = false; }
        if (needsModel) {
          const usingSol = model && sameModel(model, DEFAULT_MODEL);
          this.state.modelSetup = usingSol ? undefined : "choose";
          this.state.modelNotice = usingSol ? undefined : model ?
            `GPT-6.2 Sol을 사용할 수 없습니다. OpenAI API 키를 연결하거나 서버 기본 모델 ${model.providerID}/${model.id}로 계속하세요.` :
            "사용할 모델을 확인할 수 없습니다. OpenAI API 키를 연결하거나 사용 가능한 모델을 선택해 주세요.";
        } else if (this.state.model && model && !sameModel(this.state.model, model)) {
          this.state.modelNotice = undefined;
          this.state.modelSetup = undefined;
        }
        this.state.model = session.model ?? model;
        this.state.agent = await this.readAgent(session);
        await this.refresh();
        if (combined.aborted) { throw new Error("이벤트 연결이 끊어졌습니다."); }
        this.state.ready = true;
        this.connection(true, "서버에 연결되었습니다.");
        this.emit();
        await reader;
      } catch (error) {
        if (!signal.aborted) {
          this.state.ready = false;
          this.connection(false, `${errorMessage(error)} 자동으로 다시 연결합니다.`);
          this.emit();
        }
      } finally {
        stream.abort();
        await reader?.catch(() => undefined);
        this.buffered = undefined;
      }
      if (!signal.aborted) { await delay(1000, undefined, { signal }).catch(() => undefined); }
    }
  }

  private get location() {
    const directory = this.sessionDirectory ?? this.directory;
    return directory ? { directory } : undefined;
  }

  private async initialModel(signal: AbortSignal): Promise<ModelRef | undefined> {
    const options = { signal: AbortSignal.any([signal, AbortSignal.timeout(15_000)]) };
    try {
      const { models, hasSol } = await this.waitForSol(options);
      if (hasSol) { return DEFAULT_MODEL; }
      const [agents, fallback] = await Promise.all([
        this.api.agent.list({ location: this.location }, options).then((result) => result.data).catch(() => []),
        this.api.model.default({ location: this.location }, options).then((result) => result.data).catch(() => undefined),
      ]);
      const agentModel = agents.find((agent) => agent.mode !== "subagent" && !agent.hidden)?.model;
      if (agentModel && models.some((model) => model.enabled && sameModel(model, agentModel))) { return agentModel; }
      if (fallback?.enabled) { return { id: fallback.id, providerID: fallback.providerID }; }
    } catch (error) {
      if (signal.aborted) { throw error; }
    }
  }

  private async waitForSol(options: { signal: AbortSignal }, attempts = 5) {
    // The server can publish a partial catalog while loading or refreshing credentials.
    let models: ModelInfo[] = [];
    for (let attempt = 0; attempt < attempts; attempt++) {
      if (attempt) { await delay(500, undefined, options); }
      ({ data: models } = await this.api.model.list({ location: this.location }, options));
      if (models.some((model) => sameModel(model, DEFAULT_MODEL) && isGPTChatModel(model))) { return { models, hasSol: true }; }
    }
    return { models, hasSol: false };
  }

  continueModel() {
    const model = this.state.model;
    if (!this.state.ready || !model || this.state.modelSetup !== "choose" || this.state.pickingModel || this.state.switchingModel) { return; }
    this.state.modelSetup = "continue";
    this.state.error = undefined;
    this.state.modelNotice = `서버 기본 모델 ${model.providerID}/${model.id}을 사용 중입니다.`;
    this.emit();
  }

  async connectOpenAI(input: () => PromiseLike<string | undefined>) {
    const previous = this.state.modelSetup;
    const signal = this.signal;
    if (!signal || signal.aborted || !this.state.ready || this.state.running || this.state.sending ||
        this.state.pickingModel || this.state.switchingModel || (previous !== "choose" && previous !== "continue")) { return; }
    const address = new URL(this.address);
    if (address.protocol !== "https:" && !["localhost", "127.0.0.1", "[::1]"].includes(address.hostname)) {
      this.state.error = "OpenAI API 키를 연결하려면 로컬 서버나 HTTPS 서버에 연결해 주세요.";
      this.emit();
      return;
    }
    this.state.modelSetup = "connecting";
    this.state.error = undefined;
    this.emit();
    let registered = false;
    try {
      const key = (await input())?.trim();
      if (!key || signal.aborted || !this.state.ready || this.state.modelSetup !== "connecting") { return; }
      await this.api.integration.connect.key({ integrationID: "openai", key, location: this.location }, this.options());
      registered = true;
      const { hasSol } = await this.waitForSol(this.options(), 17);
      if (signal.aborted || !this.state.ready) { return; }
      if (!hasSol) {
        this.state.error = "API 키를 서버에 등록했습니다. GPT-6.2 Sol을 사용할 수 있는지 확인하거나 다른 모델을 선택해 주세요.";
        return;
      }
      await this.api.session.switchModel({ sessionID: this.sessionID!, model: DEFAULT_MODEL }, this.options());
      this.state.model = DEFAULT_MODEL;
      this.state.modelSetup = undefined;
      this.state.modelNotice = undefined;
    } catch {
      if (!signal.aborted) {
        this.state.error = registered ? "API 키를 서버에 등록했지만 GPT-6.2 Sol로 전환하지 못했습니다. 모델 선택에서 다시 확인해 주세요." :
          "OpenCode 서버에 OpenAI API 키를 연결하지 못했습니다. 키와 서버 설정을 확인해 주세요.";
      }
    } finally {
      if (this.state.modelSetup === "connecting") { this.state.modelSetup = previous; }
      this.emit();
    }
  }

  private async readAgent(session: SessionInfo) {
    if (session.agent) { return session.agent; }
    // Catalog discovery can fail independently of the session transport.
    const agents = await this.api.agent.list({ location: this.location }, this.options()).then((result) => result.data).catch(() => undefined);
    return agents?.find((agent) => agent.mode !== "subagent" && !agent.hidden)?.id;
  }

  private fillAgent() {
    if (!this.sessionID || this.loadingAgent) { return; }
    const stream = this.stream;
    const previousAgent = this.state.agent;
    this.loadingAgent = this.api.session.get({ sessionID: this.sessionID }, this.options())
      .then((session) => this.readAgent(session))
      .then((agent) => {
        if (!agent || stream?.signal.aborted || this.stream !== stream || this.state.agent !== previousAgent) { return; }
        this.state.agent = agent;
        this.emit();
      }).catch(() => undefined).finally(() => { this.loadingAgent = undefined; });
  }

  async availableModels() {
    const { data } = await this.api.model.list({ location: this.location }, this.options());
    return data.filter(isGPTChatModel).sort((a, b) => b.time.released - a.time.released);
  }

  async pickModel(pick: (models: ModelInfo[]) => PromiseLike<ModelRef | undefined>) {
    if (!this.state.ready || this.state.running || this.state.sending || this.state.switchingModel || this.state.pickingModel || this.state.modelSetup === "connecting") { return; }
    const signal = this.signal;
    this.state.pickingModel = true;
    this.emit();
    try {
      const models = await this.availableModels();
      if (signal?.aborted || !this.state.ready) { return; }
      const selected = await pick(models);
      if (selected && signal && !signal.aborted && this.signal === signal) { await this.switchModel(selected); }
    } catch (error) { this.state.error = errorMessage(error); }
    finally { this.state.pickingModel = false; this.emit(); }
  }

  async switchModel(model: ModelRef) {
    if (!this.state.ready || this.state.running || this.state.sending || this.state.switchingModel) {
      this.state.error = "채팅이 준비되거나 현재 응답이 끝난 뒤 모델을 다시 선택해 주세요.";
      this.emit();
      return;
    }
    this.state.switchingModel = true;
    this.state.error = undefined;
    this.emit();
    try {
      if (!(await this.availableModels()).some((available) => sameModel(available, model))) {
        this.state.error = "선택한 GPT 모델을 사용할 수 없습니다. 모델 목록을 다시 열어 주세요.";
        return;
      }
      if (!this.state.ready || this.state.running) {
        this.state.error = "채팅이 준비되거나 현재 응답이 끝난 뒤 모델을 다시 선택해 주세요.";
        return;
      }
      await this.api.session.switchModel({ sessionID: this.sessionID!, model }, this.options());
      this.state.model = model;
      this.state.modelNotice = undefined;
      this.state.modelSetup = undefined;
    } catch (error) { this.state.error = errorMessage(error); }
    finally { this.state.switchingModel = false; this.emit(); }
  }

  private refresh(): Promise<void> {
    if (this.refreshing) { return this.refreshing; }
    this.buffered ??= [];
    this.refreshing = (async () => {
      const sessionID = this.sessionID!;
      const messages: SessionMessageInfo[] = [];
      let cursor: string | undefined;
      do {
        const page = await this.api.message.list({ sessionID, order: cursor ? undefined : "asc", limit: 100, cursor }, this.options());
        messages.push(...page.data);
        cursor = page.cursor.next ?? undefined;
      } while (cursor);
      const [active, permissions, forms] = await Promise.all([
        this.api.session.active(this.options()), this.api.permission.list({ sessionID }, this.options()),
        this.api.session.form.list({ sessionID }, this.options()),
      ]);
      const snapshot = messages.flatMap(projectMessage);
      const completedText = new Set(snapshot.flatMap((message) => message.blocks.filter((block) => block.id.startsWith("text:") && block.text).map((block) => `${message.id}/${block.id}`)));
      // Volatile deltas are not in server history until text.ended; retain the live excerpt during resync.
      for (const message of this.state.messages.filter((item) => item.role === "assistant")) {
        const current = snapshot.find((item) => item.id === message.id);
        if (!current) { snapshot.push(message); continue; }
        for (const block of message.blocks.filter((item) => item.id.startsWith("text:") || item.status === "error")) {
          const target = current.blocks.find((item) => item.id === block.id);
          if (!target) { current.blocks.push(block); }
          else if (!target.text) { target.text = block.text; }
        }
      }
      this.state.messages = snapshot;
      this.state.running = !!active[sessionID] || this.awaitingExecution;
      this.state.permissions = permissions;
      this.state.forms = forms;
      const buffered = this.buffered ?? [];
      this.buffered = undefined;
      for (const event of buffered) {
        if (event.type === "session.text.delta" && completedText.has(`${event.data.assistantMessageID}/text:${event.data.ordinal}`)) { continue; }
        this.event(event, true);
      }
      this.emit();
    })().catch((error) => { this.buffered = undefined; this.stream?.abort(); throw error; })
      .finally(() => { this.refreshing = undefined; });
    return this.refreshing;
  }

  private event(event: OpenCodeEvent, replay = false) {
    if (event.type === "agent.updated") {
      if (!event.location?.directory || event.location.directory === this.sessionDirectory) { this.fillAgent(); }
      return;
    }
    if (event.type === "form.created") {
      if (event.data.form.sessionID !== this.sessionID) { return; }
      this.state.forms = [...this.state.forms.filter((item) => item.id !== event.data.form.id), event.data.form];
      this.emit();
      return;
    }
    if (!("data" in event) || !("sessionID" in event.data) || event.data.sessionID !== this.sessionID) { return; }
    switch (event.type) {
      case "session.agent.selected": this.state.agent = event.data.agent; break;
      case "session.model.selected":
        if (!this.state.model || !sameModel(this.state.model, event.data.model)) {
          this.state.modelNotice = undefined;
          this.state.modelSetup = undefined;
        }
        this.state.model = event.data.model; break;
      case "session.step.started": {
        this.state.agent = event.data.agent;
        this.state.model = event.data.model;
        const message = this.state.messages.find((item) => item.id === event.data.assistantMessageID);
        if (message) { message.agent = event.data.agent; }
        else { this.state.messages.push({ id: event.data.assistantMessageID, role: "assistant", agent: event.data.agent, blocks: [] }); }
        break;
      }
      case "session.inbox.enqueued":
        if (event.data.item.type === "user" && !this.state.messages.some((item) => item.id === event.data.inboxID)) {
          this.state.messages.push({ id: event.data.inboxID, role: "user", blocks: [{ id: "text:0", text: event.data.item.payload.text }] });
        }
        break;
      case "session.text.started":
      case "session.text.delta":
      case "session.text.ended": {
        let message = this.state.messages.find((item) => item.id === event.data.assistantMessageID);
        if (!message) { message = { id: event.data.assistantMessageID, role: "assistant", blocks: [] }; this.state.messages.push(message); }
        const id = `text:${event.data.ordinal}`;
        let block = message.blocks.find((item) => item.id === id);
        if (!block) { block = { id, text: "" }; message.blocks.push(block); }
        if (event.type === "session.text.delta") { block.text += event.data.delta; }
        if (event.type === "session.text.ended") { block.text = event.data.text; }
        break;
      }
      case "permission.asked":
        this.state.permissions = [...this.state.permissions.filter((item) => item.id !== event.data.id), event.data]; break;
      case "permission.replied":
        this.state.permissions = this.state.permissions.filter((item) => item.id !== event.data.requestID); break;
      case "form.replied":
      case "form.cancelled":
        this.state.forms = this.state.forms.filter((item) => item.id !== event.data.id); break;
      case "session.tool.input.started":
      case "session.tool.called":
      case "session.tool.progress":
      case "session.tool.success":
      case "session.tool.failed": {
        let message = this.state.messages.find((item) => item.id === event.data.assistantMessageID);
        if (!message) { message = { id: event.data.assistantMessageID, role: "assistant", blocks: [] }; this.state.messages.push(message); }
        let block = message.blocks.find((item) => item.id === event.data.id);
        if (!block) { block = { id: event.data.id, text: "", tool: "name" in event.data ? event.data.name : "도구" }; message.blocks.push(block); }
        block.status = event.type === "session.tool.success" ? "completed" : event.type === "session.tool.failed" ? "error" : "running";
        if (event.type === "session.tool.failed") { block.text = event.data.error.message; }
        break;
      }
      case "session.execution.started": this.awaitingExecution = false; this.state.running = true; this.state.notice = undefined; break;
      case "session.status":
        this.state.running = event.data.status.type !== "idle";
        if (!this.state.running) { this.awaitingExecution = false; }
        break;
      case "session.execution.failed": this.awaitingExecution = false; this.state.notice = undefined; this.state.error = event.data.error.message; this.state.running = false; break;
      case "session.execution.interrupted": this.awaitingExecution = false; this.state.notice = "작업을 취소했습니다."; this.state.running = false; break;
      case "session.execution.succeeded": this.state.notice = undefined; this.awaitingExecution = false; this.state.running = false; break;
      case "session.idle":
        if (this.state.notice?.includes("응답을 기다리는 중")) { this.state.notice = undefined; }
        this.awaitingExecution = false; this.state.running = false; break;
    }
    if (!replay && ["session.inbox.enqueued", "session.inbox.delivered", "session.step.started", "session.step.ended", "session.step.failed", "session.execution.failed", "session.execution.interrupted", "session.execution.succeeded", "session.idle"].includes(event.type)) {
      void this.refresh().catch((error) => { this.state.error = errorMessage(error); this.emit(); });
    }
    this.emit();
  }

  async send(text: string) {
    if (!this.state.ready || !this.state.model || this.state.running || this.state.sending || this.state.switchingModel ||
        this.state.pickingModel || this.state.modelSetup === "choose" || this.state.modelSetup === "connecting") {
      this.emit();
      return;
    }
    const signal = this.signal!;
    this.awaitingExecution = true;
    this.state.sending = true;
    this.state.running = true;
    this.state.error = undefined;
    this.state.notice = "메시지를 보내는 중입니다…";
    this.emit();
    try {
      this.admission = this.api.session.prompt({ sessionID: this.sessionID!, text }, this.options());
      await this.admission;
      if (signal.aborted) { return; }
      this.sent();
      if (this.state.running) { this.state.notice = "서버 접수 완료 · 응답을 기다리는 중입니다…"; }
      await this.refresh();
    } catch (error) {
      this.awaitingExecution = false;
      if (signal.aborted) { return; }
      this.state.error = `${errorMessage(error)} 전송 결과를 기록에서 확인한 뒤 다시 보내 주세요.`;
      await this.refresh().catch(() => undefined);
    } finally { this.admission = undefined; this.state.sending = false; this.emit(); }
  }

  async interrupt() {
    if (!this.state.ready || !this.state.running || this.state.cancelling) { return; }
    this.state.cancelling = true;
    this.emit();
    try {
      await this.admission?.catch(() => undefined);
      await this.api.session.interrupt({ sessionID: this.sessionID! }, this.options());
      await this.refresh();
      this.state.notice = "취소를 요청했습니다.";
    } catch (error) { this.state.error = errorMessage(error); }
    finally { this.state.cancelling = false; this.emit(); }
  }

  async permission(id: string, decision: "once" | "reject") {
    if (!this.state.ready || this.replying.has(id) || !this.state.permissions.some((item) => item.id === id)) { return; }
    this.replying.add(id);
    this.state.error = undefined;
    try { await this.api.permission.reply({ sessionID: this.sessionID!, requestID: id, decision }, this.options()); await this.refresh(); }
    catch (error) { this.state.error = errorMessage(error); this.emit(); }
    finally { this.replying.delete(id); }
  }

  async form(id: string, answer?: Answer) {
    if (!this.state.ready || this.replying.has(id) || !this.state.forms.some((item) => item.id === id)) { return; }
    this.replying.add(id);
    this.state.error = undefined;
    try {
      const input = { sessionID: this.sessionID!, formID: id };
      if (answer) { await this.api.session.form.reply({ ...input, answer }, this.options()); }
      else { await this.api.session.form.cancel(input, this.options()); }
      await this.refresh();
    } catch (error) { this.state.error = errorMessage(error); this.emit(); }
    finally { this.replying.delete(id); }
  }
}

function projectMessage(message: SessionMessageInfo): ChatMessage[] {
  if (message.type === "user") { return [{ id: message.id, role: "user", blocks: [{ id: "text:0", text: message.text }] }]; }
  if (message.type !== "assistant") { return []; }
  let ordinal = 0;
  return [{ id: message.id, role: "assistant", agent: message.agent, error: message.error?.message, blocks: message.content.flatMap((part) => {
    if (part.type === "text") { return [{ id: `text:${ordinal++}`, text: part.text }]; }
    if (part.type === "tool") { return [{ id: part.id, text: part.state.status === "error" ? part.state.error.message : "", tool: part.name, status: part.state.status }]; }
    return [];
  }) }];
}

function errorMessage(error: unknown) { return error instanceof Error ? error.message : "OpenCode 요청에 실패했습니다."; }
