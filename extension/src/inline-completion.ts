import * as vscode from "vscode";
import type { ChatSession } from "./chat";
import { collectInlineContext } from "./inline-context";

function settings(document: vscode.TextDocument) {
  const editor = vscode.workspace.getConfiguration("editor", document);
  const opencode = vscode.workspace.getConfiguration("opencode");
  return {
    enabled: document.uri.scheme === "file" && document.languageId !== "plaintext" &&
      editor.get("inlineSuggest.enabled", true) && opencode.get("inlineCompletion.enabled", true),
    delayMs: opencode.get("inlineCompletion.delayMs", 1000),
  };
}

export function registerInlineCompletion(connectedSession: () => ChatSession | undefined) {
  const output = vscode.window.createOutputChannel("OpenCode Inline Completion", { log: true });
  let idleTimer: ReturnType<typeof setTimeout> | undefined;
  let request: AbortController | undefined;

  function cancelIdleTimer() {
    clearTimeout(idleTimer);
    idleTimer = undefined;
  }

  function schedule(editor: vscode.TextEditor) {
    request?.abort();
    cancelIdleTimer();
    const { document } = editor;
    const { enabled, delayMs } = settings(document);
    if (!enabled) { return; }
    const version = document.version;
    idleTimer = setTimeout(() => {
      idleTimer = undefined;
      if (editor === vscode.window.activeTextEditor && document.version === version &&
          editor.selections.length === 1 && editor.selection.isEmpty && settings(document).enabled && connectedSession()) {
        void Promise.resolve(vscode.commands.executeCommand("editor.action.inlineSuggest.trigger")).catch(() => undefined);
      }
    }, delayMs);
  }

  const provider = vscode.languages.registerInlineCompletionItemProvider({ scheme: "file" }, {
    async provideInlineCompletionItems(document, position, context, token) {
      // The idle timer handles changes even when VS Code does not trigger a native automatic request.
      if (context.triggerKind === vscode.InlineCompletionTriggerKind.Automatic) { return; }
      const editor = vscode.window.activeTextEditor;
      const session = connectedSession();
      const options = settings(document);
      const version = document.version;
      const isCurrent = () => editor?.document === document && editor === vscode.window.activeTextEditor &&
        editor.selections.length === 1 && editor.selection.isEmpty && editor.selection.active.isEqual(position) &&
        document.version === version && connectedSession() === session && settings(document).enabled;
      if (!editor || !session || !options.enabled || token.isCancellationRequested ||
          context.selectedCompletionInfo || !isCurrent()) { return; }

      cancelIdleTimer();
      request?.abort();
      const controller = new AbortController();
      request = controller;
      const cancellation = token.onCancellationRequested(() => controller.abort());
      try {
        if (controller.signal.aborted || token.isCancellationRequested || !isCurrent()) { return; }

        const offset = document.offsetAt(position);
        const prefix = document.getText(new vscode.Range(document.positionAt(Math.max(0, offset - 6000)), position));
        const suffix = document.getText(new vscode.Range(position, document.positionAt(offset + 2000)));
        const relatedContext = await collectInlineContext(document, position, controller.signal).catch(() => "");
        if (controller.signal.aborted || token.isCancellationRequested || !isCurrent()) { return; }
        const prompt = [
          "Complete the code at the cursor between the given prefix and suffix.",
          "Return only a short insertion, with the exact required whitespace. Do not repeat surrounding code.",
          "Use no Markdown fences or explanations. Return an empty response if no insertion is useful.",
          "Use existing in-scope names exactly. For new names, follow relevant naming examples in relatedContext when available.",
          JSON.stringify({ language: document.languageId, prefix, suffix, relatedContext: relatedContext || undefined }),
        ].join("\n");
        const signal = AbortSignal.any([controller.signal, AbortSignal.timeout(15_000)]);
        const text = await session.completeCode(prompt, signal);
        const insertion = text?.replace(/^\s*```[^\r\n]*\r?\n([\s\S]*?)\r?\n```\s*$/, "$1");
        if (insertion?.trim() && insertion.length <= 2000 && !signal.aborted &&
            !token.isCancellationRequested && isCurrent()) {
          return [new vscode.InlineCompletionItem(insertion, new vscode.Range(position, position))];
        }
      } catch (error) {
        if (!controller.signal.aborted && !token.isCancellationRequested && isCurrent()) {
          output.warn("OpenCode 인라인 자동완성 요청에 실패했습니다.", error instanceof Error ? error.name : "");
        }
      } finally {
        cancellation.dispose();
        if (request === controller) { request = undefined; }
      }
    },
  });

  const selection = vscode.window.onDidChangeTextEditorSelection(({ textEditor: editor }) => {
    if (editor === vscode.window.activeTextEditor) { schedule(editor); }
  });

  const textChange = vscode.workspace.onDidChangeTextDocument(({ document, contentChanges }) => {
    const editor = vscode.window.activeTextEditor;
    if (contentChanges.length && editor?.document === document) { schedule(editor); }
  });

  const editorChange = vscode.window.onDidChangeActiveTextEditor(() => {
    request?.abort();
    cancelIdleTimer();
  });

  return vscode.Disposable.from(provider, selection, textChange, editorChange, output, {
    dispose() {
      request?.abort();
      cancelIdleTimer();
    },
  });
}
