// This method is called when your extension is deactivated
export function deactivate() {}

import { execFile } from "node:child_process";
import * as path from "node:path";
import * as vscode from "vscode";
import { ChatSidebar } from "./sidebar";
import { registerInlineCompletion } from "./inline-completion";

const TERMINAL_NAME = "opencode";

export function activate(context: vscode.ExtensionContext) {
  const sidebar = new ChatSidebar(context);
  context.subscriptions.push(
    sidebar,
    registerInlineCompletion(() => sidebar.completionSession),
    vscode.window.registerWebviewViewProvider("opencode.chat", sidebar),
    vscode.commands.registerCommand("opencode.openChat", () =>
      vscode.commands.executeCommand("opencode.chat.focus"),
    ),
  );
  const openNewTerminalDisposable = vscode.commands.registerCommand(
    "opencode.openNewTerminal",
    async () => {
      await openTerminal();
    },
  );

  const openTerminalDisposable = vscode.commands.registerCommand(
    "opencode.openTerminal",
    async () => {
      // An opencode terminal already exists => focus it
      const existingTerminal = vscode.window.terminals.find(
        (t) => t.name === TERMINAL_NAME,
      );
      if (existingTerminal) {
        existingTerminal.show();
        return;
      }

      await openTerminal();
    },
  );

  let addFilepathDisposable = vscode.commands.registerCommand(
    "opencode.addFilepathToTerminal",
    async () => {
      const fileRef = getActiveFile();
      if (!fileRef) {
        return;
      }

      const terminal = vscode.window.activeTerminal;
      if (!terminal) {
        return;
      }

      if (terminal.name === TERMINAL_NAME) {
        terminal.sendText(fileRef, false);
        terminal.show();
      }
    },
  );

  context.subscriptions.push(
    openNewTerminalDisposable,
    openTerminalDisposable,
    addFilepathDisposable,
  );

  let analysisId = 0;
  context.subscriptions.push(
    vscode.commands.registerCommand("opencode.analyzeImpact", async () => {
      const editor = vscode.window.activeTextEditor;
      const root =
        editor &&
        vscode.workspace.getWorkspaceFolder(editor.document.uri)?.uri.fsPath;
      if (!editor || !root) {
        void vscode.window.showWarningMessage(
          "작업 폴더 안의 파일에서 함수에 커서를 두고 실행해 주세요.",
        );
        return;
      }
      if (editor.document.isDirty && !(await editor.document.save())) {
        return;
      }
      const file = editor.document.uri.fsPath;
      const { line, character } = editor.selection.active; // VS Code와 CLI 모두 0부터, 열은 UTF-16 단위
      const shown = {
        id: ++analysisId,
        file: vscode.workspace.asRelativePath(file, false),
        line: line + 1,
      };
      sidebar.showImpact({ type: "impact", status: "running", ...shown }, root);
      await vscode.commands.executeCommand("opencode.chat.focus");
      // ponytail: 저장소 안의 code-impact와 .venv를 쓰는 개발용 경로. 확장을 배포할 때 opencode.codeImpactPath 설정으로 바꾼다.
      const engine = path.join(context.extensionPath, "..", "code-impact");
      const python =
        process.platform === "win32"
          ? path.join(engine, ".venv", "Scripts", "python.exe")
          : path.join(engine, ".venv", "bin", "python");
      const args = [
        "-m",
        "code_impact",
        "analyze",
        "--root",
        root,
        "--file",
        file,
        "--line",
        String(line),
        "--col",
        String(character),
      ];
      // 채팅에서 선택한 OpenAI 모델과 서버에 저장된 키를 쓴다. 하나라도 없으면 엔진을 돌리지 않고 이유를 보여준다.
      // (AI 분석이 없으면 카드가 영향 후보를 숨기므로 엔진을 돌려도 보여줄 것이 없다.)
      const model = sidebar.model;
      const key = model?.providerID === "openai" ? await sidebar.openAIKey() : undefined;
      const missing = !model
        ? "Pico 채팅이 연결되지 않아 사용할 모델을 알 수 없습니다. 채팅에 연결한 뒤 다시 실행해 주세요."
        : model.providerID !== "openai"
          ? `함수 영향도 분석은 OpenAI 모델이 필요합니다. 현재 채팅은 OpenAI 키 없이 서버 기본 모델(${model.providerID}/${model.id})을 쓰고 있습니다. OpenAI API 키를 연결해 주세요.`
          : !key
            ? "OpenCode 서버에서 OpenAI API 키를 찾지 못했습니다. 채팅에서 OpenAI API 키를 연결한 뒤 다시 실행해 주세요."
            : undefined;
      if (missing) {
        sidebar.showImpact(
          { type: "impact", status: "done", ...shown, result: { error: { code: "MODEL_ERROR", message: missing } } },
          root,
        );
        return;
      }
      // 명령 인자는 ps로 보이므로 환경변수로 넘긴다.
      const env: NodeJS.ProcessEnv = {
        ...process.env,
        CODE_IMPACT_MODEL_PROVIDER: "openai",
        CODE_IMPACT_MODEL: model!.id,
        CODE_IMPACT_API_KEY: key,
      };
      const done = new Promise<void>((resolve) => {
        // 분석마다 id가 달라 채팅에 각자 메시지로 남으므로, 연달아 실행해도 서로 덮어쓰지 않는다.
        execFile(
          python,
          args,
          { cwd: engine, env, timeout: 180_000, maxBuffer: 10 * 1024 * 1024 },
          (error, stdout, stderr) => {
            resolve();
            if (stderr) {
              console.warn("[code-impact]", stderr);
            }
            let result: unknown;
            try {
              // 실패(exit 1)여도 stdout에 에러 JSON이 오므로 stdout을 먼저 읽는다.
              result = JSON.parse(stdout);
            } catch {
              console.error("[code-impact]", error);
              result = {
                error: {
                  code: "ENGINE_ERROR",
                  message: `분석 엔진을 실행하지 못했습니다. ${engine}/.venv 설치를 확인해 주세요.`,
                },
              };
            }
            sidebar.showImpact(
              { type: "impact", status: "done", ...shown, result },
              root,
            );
          },
        );
      });
      vscode.window.setStatusBarMessage(
        "$(sync~spin) 함수 영향도 분석 중…",
        done,
      );
    }),
  );

  async function openTerminal() {
    // Create a new terminal in split screen
    const terminal = vscode.window.createTerminal({
      name: TERMINAL_NAME,
      iconPath: {
        light: vscode.Uri.file(
          context.asAbsolutePath("images/button-dark.svg"),
        ),
        dark: vscode.Uri.file(
          context.asAbsolutePath("images/button-light.svg"),
        ),
      },
      location: {
        viewColumn: vscode.ViewColumn.Beside,
        preserveFocus: false,
      },
      env: {
        OPENCODE_CALLER: "vscode",
      },
    });

    terminal.show();
    terminal.sendText("opencode");
  }

  function getActiveFile() {
    const activeEditor = vscode.window.activeTextEditor;
    if (!activeEditor) {
      return;
    }

    const document = activeEditor.document;
    const workspaceFolder = vscode.workspace.getWorkspaceFolder(document.uri);
    if (!workspaceFolder) {
      return;
    }

    // Get the relative path from workspace root
    const relativePath = vscode.workspace.asRelativePath(document.uri);
    let filepathWithAt = `@${relativePath}`;

    // Check if there's a selection and add line numbers
    const selection = activeEditor.selection;
    if (!selection.isEmpty) {
      // Convert to 1-based line numbers
      const startLine = selection.start.line + 1;
      const endLine = selection.end.line + 1;

      if (startLine === endLine) {
        // Single line selection
        filepathWithAt += `#${startLine}`;
      } else {
        // Multi-line selection
        filepathWithAt += `#${startLine}-${endLine}`;
      }
    }

    return filepathWithAt;
  }
}
