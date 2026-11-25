export type ConnectionState = {
  type: "connection"
  status: "disconnected" | "starting" | "connecting" | "connected" | "unauthorized" | "error"
  address: string
  message: string
  version?: string
}

import type { FormInfo, ModelRef, PermissionRequest } from "@opencode/client";

export type ChatMessage = { id: string; role: "user" | "assistant"; agent?: string; blocks: { id: string; text: string; tool?: string; status?: string }[]; error?: string };
export type ChatState = {
  type: "chat"; ready: boolean; running: boolean; sending: boolean; cancelling: boolean;
  agent?: string; model?: ModelRef; modelNotice?: string; pickingModel?: boolean; switchingModel?: boolean;
  modelSetup?: "choose" | "connecting" | "continue";
  messages: ChatMessage[]; permissions: PermissionRequest[]; forms: FormInfo[]; error?: string; notice?: string;
};
export type Answer = Record<string, string | number | boolean | string[]>;
export type SidebarMessage = { type: "ready" | "connect" | "configure" | "password" | "interrupt" | "pickModel" | "connectOpenAI" | "continueModel" }
  | { type: "send"; text: string }
  | { type: "permission"; id: string; decision: "once" | "reject" }
  | { type: "form"; id: string; answer?: Answer };

export function isSidebarMessage(message: unknown): message is SidebarMessage {
  if (typeof message !== "object" || message === null || !("type" in message)) { return false; }
  if (["ready", "connect", "configure", "password", "interrupt", "pickModel", "connectOpenAI", "continueModel"].includes(String(message.type))) { return true; }
  if (message.type === "send") {
    return "text" in message && typeof message.text === "string" && !!message.text.trim() && message.text.length <= 100_000;
  }
  if (!("id" in message) || typeof message.id !== "string" || !message.id) { return false; }
  if (message.type === "permission") { return "decision" in message && ["once", "reject"].includes(String(message.decision)); }
  if (message.type !== "form") { return false; }
  if (!("answer" in message) || message.answer === undefined) { return true; }
  return typeof message.answer === "object" && message.answer !== null && !Array.isArray(message.answer) &&
    Object.values(message.answer).every((value) => typeof value === "string" || typeof value === "boolean" ||
      (typeof value === "number" && Number.isFinite(value)) || (Array.isArray(value) && value.every((item) => typeof item === "string")));
}
