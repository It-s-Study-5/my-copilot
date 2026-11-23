export type ConnectionState = {
  type: "connection"
  status: "disconnected" | "starting" | "connecting" | "connected" | "unauthorized" | "error"
  address: string
  message: string
  version?: string
}

export type SidebarMessage = { type: "ready" | "connect" | "configure" | "password" }

export function isSidebarMessage(message: unknown): message is SidebarMessage {
  return typeof message === "object" && message !== null && "type" in message &&
    typeof message.type === "string" && ["ready", "connect", "configure", "password"].includes(message.type);
}
