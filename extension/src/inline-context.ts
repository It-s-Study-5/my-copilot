import { setTimeout as delay } from "node:timers/promises";
import * as vscode from "vscode";

const CONTEXT_LIMIT = 2000;
const LOOKUP_MS = 350;
const WORD = /[A-Za-z_$][\w$]*/g;
const DECLARATION = /\b(?:const|let|var|function|class|type|interface)\s+([A-Za-z_$][\w$]*)/;
const COMMON_WORDS = new Set([
  "const", "let", "var", "return", "await", "async", "function", "new", "this", "export", "import",
  "if", "else", "true", "false", "undefined", "null", "string", "number", "boolean", "void", "from",
]);
const SYMBOL_KINDS = new Set([
  vscode.CompletionItemKind.Variable, vscode.CompletionItemKind.Field,
  vscode.CompletionItemKind.Property, vscode.CompletionItemKind.Constant,
  vscode.CompletionItemKind.Function, vscode.CompletionItemKind.Method,
  vscode.CompletionItemKind.Class, vscode.CompletionItemKind.Interface, vscode.CompletionItemKind.Struct,
]);

function nameParts(name: string) {
  return name.replace(/([a-z0-9])([A-Z])/g, "$1 $2").toLowerCase().split(/[^a-z0-9]+/)
    .filter((word) => word.length > 2 && !COMMON_WORDS.has(word))
    .map((word) => word.length > 3 ? word.replace(/s$/, "") : word);
}

function nearbyWords(document: vscode.TextDocument, position: vscode.Position) {
  const found = new Map<string, vscode.Position>();
  const currentText = document.lineAt(position.line).text;
  const slices = [
    { line: position.line, start: Math.max(0, position.character - 300), end: position.character, reverse: true },
    { line: position.line, start: position.character, end: Math.min(currentText.length, position.character + 100), reverse: false },
  ];
  for (let distance = 1; distance <= 5; distance++) {
    for (const line of [position.line - distance, position.line + distance]) {
      if (line < 0 || line >= document.lineCount) { continue; }
      slices.push({ line, start: 0, end: 300, reverse: line < position.line });
    }
  }
  for (const { line, start, end, reverse } of slices) {
    const matches = [...document.lineAt(line).text.slice(start, end).matchAll(WORD)];
    for (const match of reverse ? matches.reverse() : matches) {
      const name = match[0];
      if (name.length < 2 || COMMON_WORDS.has(name) || found.has(name)) { continue; }
      found.set(name, new vscode.Position(line, start + match.index));
      if (found.size === 12) { return found; }
    }
  }
  return found;
}

function definitionLocation(result: vscode.Location | vscode.LocationLink) {
  return "targetUri" in result
    ? { uri: result.targetUri, line: (result.targetSelectionRange ?? result.targetRange).start.line }
    : { uri: result.uri, line: result.range.start.line };
}

export async function collectInlineContext(
  document: vscode.TextDocument, position: vscode.Position, signal: AbortSignal,
) {
  const root = vscode.workspace.getWorkspaceFolder(document.uri)?.uri.toString();
  if (!root || signal.aborted) { return ""; }

  const words = nearbyWords(document, position);
  const cursor = document.offsetAt(position);
  const terms = new Set([...words.keys()].flatMap(nameParts));
  const matches = (name: string) => words.has(name) || nameParts(name).some((part) => terms.has(part));
  const timeout = new AbortController();
  const lookup = AbortSignal.any([signal, timeout.signal]);
  const symbols: string[] = [];
  const types = new Map<number, string>();
  const definitions = new Map<string, { rank: number; lines: string[] }>();
  const open = new Map<string, Promise<vscode.TextDocument | undefined>>();

  async function scopeSymbols() {
    const result = await vscode.commands.executeCommand<vscode.CompletionList | undefined>(
      "vscode.executeCompletionItemProvider", document.uri, position,
    );
    if (lookup.aborted) { return; }
    for (const item of result?.items ?? []) {
      const label = typeof item.label === "string" ? item.label : item.label.label;
      if (item.kind === undefined || !SYMBOL_KINDS.has(item.kind) || !matches(label)) { continue; }
      const detail = item.detail ?? (typeof item.label === "string" ? undefined : item.label.detail);
      symbols.push(detail ? `${label} — ${detail.split(/\r?\n/, 1)[0]}`.slice(0, 180) : label.slice(0, 180));
      if (symbols.length >= 8) { break; }
    }
  }

  async function symbolType(wordPosition: vscode.Position, rank: number) {
    const hovers = await vscode.commands.executeCommand<vscode.Hover[] | undefined>(
      "vscode.executeHoverProvider", document.uri, wordPosition,
    );
    if (lookup.aborted) { return; }
    for (const content of hovers?.flatMap((hover) => hover.contents) ?? []) {
      if (typeof content === "string") { continue; }
      const signature = ("language" in content ? content.value :
        /^```[^\r\n]*\r?\n([\s\S]*?)\r?\n```/m.exec(content.value)?.[1])?.trim();
      if (signature) {
        types.set(rank, `Type: ${signature.replace(/\s+/g, " ").slice(0, 180)}`);
        return;
      }
    }
  }

  async function relatedDefinition(wordPosition: vscode.Position, rank: number) {
    const results = await vscode.commands.executeCommand<Array<vscode.Location | vscode.LocationLink> | undefined>(
      "vscode.executeDefinitionProvider", document.uri, wordPosition,
    );
    if (lookup.aborted) { return; }
    for (const result of results?.slice(0, 2) ?? []) {
      const { uri, line } = definitionLocation(result);
      const key = uri.toString();
      const relative = vscode.workspace.asRelativePath(uri, false);
      if (uri.scheme !== "file" || vscode.workspace.getWorkspaceFolder(uri)?.uri.toString() !== root ||
          relative.split(/[\\/]/).some((part) => part === "node_modules" || part === ".git")) { continue; }
      if (key === document.uri.toString()) {
        const lineOffset = document.offsetAt(new vscode.Position(line, 0));
        if (lineOffset >= cursor - 6000 && lineOffset < cursor + 2000) { continue; }
      }
      if (!open.has(key)) {
        if (open.size >= 4) { continue; }
        const loaded = vscode.workspace.textDocuments.find((item) => item.uri.toString() === key);
        open.set(key, loaded ? Promise.resolve(loaded) : Promise.resolve(vscode.workspace.fs.stat(uri)).then((stat) =>
          !lookup.aborted && stat.size <= 256_000 ? vscode.workspace.openTextDocument(uri) : undefined,
        ));
      }
      const target = await open.get(key);
      if (lookup.aborted || !target || line >= target.lineCount) { continue; }
      const snippet = (index: number) => `${relative}:${index + 1} ${target.lineAt(index).text.trim()}`.slice(0, 260);
      const keyAtLine = `${key}:${line}`;
      const existing = definitions.get(keyAtLine);
      if (existing) {
        existing.rank = Math.min(existing.rank, rank);
        continue;
      }
      const related: number[] = [];
      for (let index = Math.max(0, line - 80); index < Math.min(target.lineCount, line + 81); index++) {
        if (index === line) { continue; }
        const declaration = DECLARATION.exec(target.lineAt(index).text.slice(0, 300));
        if (declaration && matches(declaration[1])) { related.push(index); }
      }
      related.sort((a, b) => Math.abs(a - line) - Math.abs(b - line));
      definitions.set(keyAtLine, { rank, lines: [snippet(line), ...related.slice(0, 2).map(snippet)] });
    }
  }

  const positions = [...words.values()];
  const jobs = [
    scopeSymbols(),
    ...positions.slice(0, 2).map(symbolType),
    ...positions.slice(0, 6).map(relatedDefinition),
  ];
  try {
    await Promise.race([
      Promise.allSettled(jobs),
      delay(LOOKUP_MS, undefined, { signal: lookup }),
    ]);
  } catch {
    return "";
  } finally {
    timeout.abort();
  }
  if (signal.aborted) { return ""; }

  const targets = [...definitions.values()].sort((a, b) => a.rank - b.rank).map(({ lines }) => lines);
  const lines = [
    ...[...new Set(symbols)].slice(0, 3).map((symbol) => `Symbol candidate: ${symbol}`),
    ...[...types.entries()].sort(([a], [b]) => a - b).map(([, type]) => type),
    ...targets.flat(),
  ];
  let context = "";
  for (const line of new Set(lines)) {
    const addition = context ? `\n${line}` : line;
    if (context.length + addition.length <= CONTEXT_LIMIT) { context += addition; }
  }
  return context;
}
