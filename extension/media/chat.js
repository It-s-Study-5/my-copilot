(() => {
  const vscode = acquireVsCodeApi()
  const summary = document.getElementById("connection-summary")
  const status = document.getElementById("status")
  const connect = document.getElementById("connect")
  const password = document.getElementById("password")
  const prompt = document.getElementById("prompt")
  const labels = {
    disconnected: "연결 안 됨",
    starting: "서버 준비 중",
    connecting: "연결 중",
    connected: "연결됨",
    unauthorized: "인증 필요",
    error: "연결 오류",
  }

  connect.addEventListener("click", () => vscode.postMessage({ type: "connect" }))
  password.addEventListener("click", () => vscode.postMessage({ type: "password" }))
  document.getElementById("configure").addEventListener("click", () => vscode.postMessage({ type: "configure" }))
  document.getElementById("composer").addEventListener("submit", (event) => event.preventDefault())
  prompt.value = vscode.getState()?.draft ?? ""
  prompt.addEventListener("input", () => vscode.setState({ draft: prompt.value }))

  window.addEventListener("message", (event) => {
    const state = event.data
    if (!state || state.type !== "connection" || !Object.hasOwn(labels, state.status) ||
      typeof state.address !== "string" || typeof state.message !== "string") {
      return
    }
    status.textContent = labels[state.status]
    summary.dataset.status = state.status
    summary.title = `${state.address}\n${state.message}${typeof state.version === "string" ? ` (v${state.version})` : ""}`.trim()
    status.setAttribute("aria-label", `${labels[state.status]}. ${summary.title}`)
    status.setAttribute("role", state.status === "error" || state.status === "unauthorized" ? "alert" : "status")
    connect.disabled = state.status === "connecting" || state.status === "starting"
    password.hidden = state.status !== "unauthorized"
    document.getElementById("empty-message").textContent = state.status === "connected"
      ? "서버 연결이 준비되었습니다."
      : "작업할 프로젝트를 열고 OpenCode 서버에 연결해 주세요."
  })

  vscode.postMessage({ type: "ready" })
})()
