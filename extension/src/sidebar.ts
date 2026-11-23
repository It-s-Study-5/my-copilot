import { randomBytes } from "node:crypto";
import * as vscode from "vscode";
import { getServerInfo, serverUrl, ServerConnectionError } from "./server";
import { isSidebarMessage, type ConnectionState } from "./protocol";
import { ensureLocalServer } from "./local-server";

export class ChatSidebar implements vscode.WebviewViewProvider, vscode.Disposable {
  private view?: vscode.WebviewView;
  private controller?: AbortController;
  private password?: string;
  private readonly configuration: vscode.Disposable;
  private state: ConnectionState = {
    type: "connection", status: "disconnected", address: "", message: "서버에 연결해 주세요.",
  };

  constructor(private readonly context: vscode.ExtensionContext) {
    this.configuration = vscode.workspace.onDidChangeConfiguration((event) => {
      if (event.affectsConfiguration("opencode.serverUrl")) {
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
      localResourceRoots: [vscode.Uri.joinPath(this.context.extensionUri, "media")],
    };
    view.webview.html = this.html(view.webview);
    view.webview.onDidReceiveMessage((message: unknown) => {
      if (!isSidebarMessage(message)) {
        return;
      }
      switch (message.type) {
        case "ready":
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

  private get address() {
    return vscode.workspace.getConfiguration("opencode").get<string>("serverUrl", "").trim();
  }

  private update(state: ConnectionState) {
    this.state = state;
    void this.view?.webview.postMessage(state);
  }

  private async connect() {
    this.controller?.abort();
    const controller = new AbortController();
    this.controller = controller;
    this.update({ type: "connection", status: "connecting", address: "", message: "서버에 연결하는 중입니다…" });
    let address = "";
    try {
      let password = this.password ?? process.env.OPENCODE_PASSWORD;
      if (this.address) {
        address = serverUrl(this.address);
      } else {
        this.update({ type: "connection", status: "starting", address: "자동 연결", message: "로컬 OpenCode 서버를 준비하는 중입니다…" });
        const local = await ensureLocalServer(controller.signal);
        address = local.address;
        password = this.password ?? local.password;
      }
      if (controller.signal.aborted) {
        return;
      }
      this.update({ type: "connection", status: "connecting", address, message: "서버에 연결하는 중입니다…" });
      const info = await getServerInfo(address, password, controller.signal);
      if (!controller.signal.aborted) {
        this.update({ type: "connection", status: "connected", address, message: "서버에 연결되었습니다.", version: info.version });
      }
    } catch (error) {
      if (!controller.signal.aborted) {
        this.update({
          type: "connection",
          status: error instanceof ServerConnectionError && error.needsPassword ? "unauthorized" : "error",
          address,
          message: error instanceof Error ? error.message : "서버 연결을 확인할 수 없습니다.",
        });
      }
    }
  }

  private async configure() {
    const address = await vscode.window.showInputBox({
      title: "OpenCode 서버 주소",
      value: this.address,
      placeHolder: "자동 연결 (로컬 OpenCode)",
      prompt: "비워 두면 로컬 서버를 자동 실행·연결합니다. 직접 연결하려면 HTTP(S) 주소를 입력하세요.",
      ignoreFocusOut: true,
      validateInput: (value) => {
        try {
          if (value.trim()) {
            serverUrl(value);
          }
          return undefined;
        } catch (error) {
          return error instanceof Error ? error.message : "서버 주소를 확인해 주세요.";
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
      await configuration.update("serverUrl", normalized,
        vscode.workspace.workspaceFolders?.length ? vscode.ConfigurationTarget.Workspace : vscode.ConfigurationTarget.Global);
    } catch {
      void vscode.window.showErrorMessage("서버 주소를 저장할 수 없습니다. 작업 폴더와 설정 파일을 확인해 주세요.");
    }
  }

  private async authenticate() {
    const address = this.address;
    const password = await vscode.window.showInputBox({
      title: "OpenCode 서버 비밀번호",
      prompt: "서버의 OPENCODE_PASSWORD를 입력하세요. 창을 닫으면 비밀번호가 지워집니다.",
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
    const asset = (file: string) => webview.asWebviewUri(vscode.Uri.joinPath(this.context.extensionUri, "media", file));
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
  <section class="connection" aria-labelledby="connection-heading">
    <div class="connection-heading"><h1 id="connection-heading">OpenCode</h1><span id="status">연결 안 됨</span></div>
    <p id="address" class="address"></p>
    <p id="connection-message" role="status" aria-live="polite">서버 연결을 확인하고 있습니다.</p>
    <div class="actions">
      <button id="connect" type="button">다시 연결</button>
      <button id="configure" type="button" class="secondary">서버 주소</button>
      <button id="password" type="button" class="secondary" hidden>비밀번호 입력</button>
    </div>
  </section>
  <main id="messages" role="log" aria-label="채팅 메시지" aria-live="polite">
    <div class="empty-state">
      <h2>OpenCode Chat</h2>
      <p id="empty-message">작업할 프로젝트를 열고<br>OpenCode 서버에 연결해 주세요.</p>
      <p class="hint">현재는 서버 연결을 확인할 수 있습니다.<br>메시지 전송은 아직 지원하지 않습니다.</p>
    </div>
  </main>
  <form id="composer" aria-label="메시지 작성">
    <label for="prompt">메시지</label>
    <textarea id="prompt" rows="3" placeholder="무엇을 도와드릴까요?" aria-describedby="composer-hint"></textarea>
    <div class="composer-footer">
      <small id="composer-hint">채팅 준비 중</small>
      <div class="actions">
        <button type="button" disabled title="실행 중인 작업이 없습니다.">중지</button>
        <button type="submit" disabled title="메시지 전송은 아직 지원하지 않습니다.">전송</button>
      </div>
    </div>
  </form>
  <script nonce="${nonce}" src="${asset("chat.js")}"></script>
</body>
</html>`;
  }
}
