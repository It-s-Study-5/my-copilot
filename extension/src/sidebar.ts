import { randomBytes } from "node:crypto";
import * as path from "node:path";
import * as vscode from "vscode";
import { getServerInfo, serverUrl, ServerConnectionError } from "./server";
import {
  isSidebarMessage,
  type ConnectionState,
  type ImpactState,
} from "./protocol";
import { ensureLocalServer } from "./local-server";
import { ensureCli } from "./cli-download";
import { ChatSession } from "./chat";

export class ChatSidebar
  implements vscode.WebviewViewProvider, vscode.Disposable
{
  private view?: vscode.WebviewView;
  private controller?: AbortController;
  private password?: string;
  private chat?: ChatSession;
  private chatKey?: string;
  private chatTask?: Promise<void>;
  private readonly impacts = new Map<number, ImpactState>();
  private impactRoot?: string;
  private readonly configuration: vscode.Disposable;
  private state: ConnectionState = {
    type: "connection",
    status: "disconnected",
    address: "",
    message: "서버에 연결해 주세요.",
  };

  constructor(private readonly context: vscode.ExtensionContext) {
    this.configuration = vscode.workspace.onDidChangeConfiguration((event) => {
      if (
        event.affectsConfiguration("opencode.serverUrl") ||
        event.affectsConfiguration("opencode.cliPath")
      ) {
        this.password = undefined;
        if (this.view) {
          void this.connect();
        }
      }
    });
  }

  resolveWebviewView(view: vscode.WebviewView) {
    this.view = view;
    view.webview.options = {
      enableScripts: true,
      localResourceRoots: [
        vscode.Uri.joinPath(this.context.extensionUri, "media"),
      ],
    };
    view.webview.html = this.html(view.webview);
    view.webview.onDidReceiveMessage((message: unknown) => {
      if (!isSidebarMessage(message)) {
        return;
      }
      switch (message.type) {
        case "send":
          void this.chat?.send(message.text);
          break;
        case "pickModel":
          void this.pickModel();
          break;
        case "connectOpenAI":
          void this.chat?.connectOpenAI(() =>
            vscode.window.showInputBox({
              title: "OpenAI API 키 연결",
              prompt: "이 OpenCode 서버에 등록할 OpenAI API 키를 입력하세요.",
              password: true,
              ignoreFocusOut: true,
              validateInput: (value) =>
                value.trim() ? undefined : "OpenAI API 키를 입력해 주세요.",
            }),
          );
          break;
        case "continueModel":
          this.chat?.continueModel();
          break;
        case "interrupt":
          void this.chat?.interrupt();
          break;
        case "permission":
          void this.chat?.permission(message.id, message.decision);
          break;
        case "form":
          void this.chat?.form(message.id, message.answer);
          break;
        case "open":
          void this.open(message.file, message.line);
          break;
        case "ready":
          for (const impact of this.impacts.values()) {
            void view.webview.postMessage(impact);
          }
          void this.connect();
          break;
        case "connect":
          void this.connect();
          break;
        case "configure":
          void this.configure();
          break;
        case "password":
          void this.authenticate();
          break;
      }
    });
    view.onDidDispose(() => {
      this.controller?.abort();
      this.view = undefined;
    });
  }

  showImpact(impact: Omit<ImpactState, "after">, root: string) {
    const after =
      this.impacts.get(impact.id)?.after ??
      this.chat?.state.messages.length ??
      0;
    const state = { ...impact, after };
    this.impacts.set(impact.id, state);
    this.impactRoot = root;
    void this.view?.webview.postMessage(state);
  }

  private async open(file: string, line: number) {
    if (!this.impactRoot) {
      return;
    }
    const root = vscode.Uri.file(this.impactRoot);
    const uri = vscode.Uri.joinPath(root, file);
    // webview가 보낸 경로이므로 분석한 작업 폴더 밖은 열지 않는다.
    if (!uri.fsPath.startsWith(root.fsPath + path.sep)) {
      return;
    }
    const position = new vscode.Position(line - 1, 0);
    try {
      await vscode.window.showTextDocument(uri, {
        selection: new vscode.Range(position, position),
        viewColumn: vscode.ViewColumn.One,
      });
    } catch {
      void vscode.window.showErrorMessage(`${file} 파일을 열 수 없습니다.`);
    }
  }

  private get address() {
    return vscode.workspace
      .getConfiguration("opencode")
      .get<string>("serverUrl", "")
      .trim();
  }

  private update(state: ConnectionState) {
    this.state = state;
    void this.view?.webview.postMessage(state);
  }

  private async pickModel() {
    const chat = this.chat;
    await chat?.pickModel(async (models) => {
      if (!models.length) {
        void vscode.window.showInformationMessage("사용 가능한 GPT 모델이 없습니다. OpenCode 서버의 OpenAI 연결을 확인해 주세요.");
        return;
      }
      const current = chat.state.model;
      const selected = await vscode.window.showQuickPick(models.map(({ name, id, providerID }) => ({
        label: name || id,
        description: `${providerID}/${id}${current?.id === id && current.providerID === providerID ? " · 현재 모델" : ""}`,
        model: { id, providerID },
      })), { placeHolder: "이 채팅에 사용할 모델 선택", matchOnDescription: true });
      return selected?.model;
    });
  }

  private async connect() {
    this.controller?.abort();
    const controller = new AbortController();
    this.controller = controller;
    this.update({
      type: "connection",
      status: "connecting",
      address: "",
      message: "서버에 연결하는 중입니다…",
    });
    let address = "";
    try {
      await this.chatTask;
      if (controller.signal.aborted) {
        return;
      }
      let password = this.password ?? process.env.OPENCODE_PASSWORD;
      if (this.address) {
        address = serverUrl(this.address);
      } else {
        this.update({
          type: "connection",
          status: "starting",
          address: "자동 연결",
          message: "로컬 OpenCode 서버를 준비하는 중입니다…",
        });
        // cliPath overrides; otherwise the CLI matching this extension version is downloaded once.
        let cli = vscode.workspace
          .getConfiguration("opencode")
          .get<string>("cliPath", "")
          .trim();
        if (!cli) {
          this.update({
            type: "connection",
            status: "starting",
            address: "자동 연결",
            message:
              "OpenCode CLI를 준비하는 중입니다. 처음 한 번만 내려받습니다…",
          });
          cli = await ensureCli(
            this.context.globalStorageUri.fsPath,
            String(this.context.extension.packageJSON.version),
            controller.signal,
          );
        }
        const local = await ensureLocalServer(controller.signal, [cli]);
        address = local.address;
        password = this.password ?? local.password;
      }
      if (controller.signal.aborted) {
        return;
      }
      this.update({
        type: "connection",
        status: "connecting",
        address,
        message: "서버에 연결하는 중입니다…",
      });
      const info = await getServerInfo(address, password, controller.signal);
      if (!controller.signal.aborted) {
        this.update({
          type: "connection",
          status: "connected",
          address,
          message: "서버에 연결되었습니다.",
          version: info.version,
        });
        const directory = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
        const key = JSON.stringify([address, directory]);
        if (!this.chat || key !== this.chatKey) {
          this.chatKey = key;
          this.chat = new ChatSession(
            address,
            password,
            directory,
            (state) => {
              void this.view?.webview.postMessage(state);
            },
            (connected, message) =>
              this.update({
                type: "connection",
                status: connected ? "connected" : "error",
                address,
                message,
                version: info.version,
              }),
            () => {
              void this.view?.webview.postMessage({ type: "sent" });
            },
          );
        }
        this.chat.authenticate(password);
        this.chatTask = this.chat.run(controller.signal);
      }
    } catch (error) {
      if (!controller.signal.aborted) {
        this.update({
          type: "connection",
          status:
            error instanceof ServerConnectionError && error.needsPassword
              ? "unauthorized"
              : "error",
          address,
          message:
            error instanceof Error
              ? error.message
              : "서버 연결을 확인할 수 없습니다.",
        });
      }
    }
  }

  private async configure() {
    const address = await vscode.window.showInputBox({
      title: "OpenCode 서버 주소",
      value: this.address,
      placeHolder: "자동 연결 (로컬 OpenCode)",
      prompt:
        "비워 두면 로컬 서버를 자동 실행·연결합니다. 직접 연결하려면 HTTP(S) 주소를 입력하세요.",
      ignoreFocusOut: true,
      validateInput: (value) => {
        try {
          if (value.trim()) {
            serverUrl(value);
          }
          return undefined;
        } catch (error) {
          return error instanceof Error
            ? error.message
            : "서버 주소를 확인해 주세요.";
        }
      },
    });
    if (address === undefined) {
      return;
    }
    try {
      const configuration = vscode.workspace.getConfiguration("opencode");
      const normalized = address.trim() ? serverUrl(address) : "";
      if (normalized === this.address) {
        await this.connect();
        return;
      }
      await configuration.update(
        "serverUrl",
        normalized,
        vscode.workspace.workspaceFolders?.length
          ? vscode.ConfigurationTarget.Workspace
          : vscode.ConfigurationTarget.Global,
      );
    } catch {
      void vscode.window.showErrorMessage(
        "서버 주소를 저장할 수 없습니다. 작업 폴더와 설정 파일을 확인해 주세요.",
      );
    }
  }

  private async authenticate() {
    const address = this.address;
    const password = await vscode.window.showInputBox({
      title: "OpenCode 서버 비밀번호",
      prompt:
        "서버의 OPENCODE_PASSWORD를 입력하세요. 창을 닫으면 비밀번호가 지워집니다.",
      password: true,
      ignoreFocusOut: true,
    });
    if (password !== undefined && this.view && address === this.address) {
      this.password = password;
      await this.connect();
    }
  }

  dispose() {
    this.controller?.abort();
    this.password = undefined;
    this.configuration.dispose();
  }

  private html(webview: vscode.Webview) {
    const asset = (file: string) =>
      webview.asWebviewUri(
        vscode.Uri.joinPath(this.context.extensionUri, "media", file),
      );
    const nonce = randomBytes(16).toString("hex");
    return `<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src ${webview.cspSource}; script-src 'nonce-${nonce}';">
  <link rel="stylesheet" href="${asset("chat.css")}">
  <title>OpenCode Chat</title>
</head>
<body>
  <section class="connection" aria-label="서버 연결">
    <div id="connection-summary" class="connection-summary" title="서버 연결을 확인하고 있습니다.">
      <svg class="connection-icon" viewBox="0 0 16 16" aria-hidden="true"><rect x="2" y="2" width="12" height="5" rx="1"/><rect x="2" y="9" width="12" height="5" rx="1"/><path d="M4 4.5h1m-1 7h1"/></svg>
      <span id="status" role="status" aria-live="polite">연결 안 됨</span>
    </div>
    <div class="actions">
      <button id="connect" type="button" class="icon-button" title="다시 연결" aria-label="다시 연결"><svg viewBox="0 0 16 16" aria-hidden="true"><path d="M13 6a5 5 0 1 0 0 4M13 2v4H9"/></svg></button>
      <button id="configure" type="button" class="icon-button" title="서버 주소 설정" aria-label="서버 주소 설정"><svg viewBox="0 0 16 16" aria-hidden="true"><path d="M2 4h12M2 12h12"/><rect x="5" y="2" width="3" height="4" rx=".5"/><rect x="9" y="10" width="3" height="4" rx=".5"/></svg></button>
      <button id="password" type="button" class="icon-button" title="비밀번호 입력" aria-label="비밀번호 입력" hidden><svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="5" cy="6" r="3"/><path d="m7 8 6 6m-2-2 2-2m-4 0 2-2"/></svg></button>
    </div>
  </section>
  <section id="session-selection" aria-label="채팅 에이전트와 모델" hidden>
    <span id="active-agent" aria-live="polite"></span>
    <button id="pick-model" type="button" class="model-button" aria-label="모델 선택" disabled>모델 선택</button>
  </section>
  <p id="model-notice" role="status" hidden></p>
  <div id="model-setup" class="actions" aria-label="채팅 모델 설정" hidden>
    <button id="connect-openai" type="button">OpenAI API 키 연결</button>
    <button id="continue-model" type="button">현재 모델로 계속</button>
  </div>
  <main id="conversation" role="log" aria-label="채팅 메시지" aria-live="polite">
    <div id="messages">
      <div id="empty-state" class="empty-state">
        <h2>OpenCode Chat</h2>
        <p id="empty-message">작업할 프로젝트를 열고<br>OpenCode 서버에 연결해 주세요.</p>
      </div>
    </div>
  </main>
  <p id="chat-error" role="alert" hidden></p>
  <section id="interaction" aria-label="메시지 입력 및 요청 응답">
    <section id="requests" aria-label="응답이 필요한 요청"></section>
    <form id="composer" aria-label="메시지 작성">
      <textarea id="prompt" rows="3" maxlength="100000" placeholder="무엇을 도와드릴까요?" aria-label="메시지" aria-describedby="composer-hint"></textarea>
      <div class="composer-footer">
        <small id="composer-hint" role="status">채팅 준비 중</small>
        <button type="submit" class="send-button" aria-label="전송" disabled title="전송 (Enter)"><svg viewBox="0 0 16 16" aria-hidden="true"><path d="m14 2-12 5 5 2 2 5 5-12ZM7 9l7-7"/></svg></button>
      </div>
    </form>
  </section>
  <script nonce="${nonce}" src="${asset("chat.js")}"></script>
</body>
</html>`;
  }
}
