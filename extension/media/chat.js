(() => {
  const vscode = acquireVsCodeApi()
  const byId = (id) => document.getElementById(id)
  const prompt = byId("prompt")
  const send = document.querySelector(".send-button")
  const messages = byId("messages")
  const emptyState = byId("empty-state")
  const conversation = byId("conversation")
  const requests = byId("requests")
  const composer = byId("composer")
  const selection = byId("session-selection")
  const agent = byId("active-agent")
  const model = byId("pick-model")
  const modelNotice = byId("model-notice")
  const modelSetup = byId("model-setup")
  const connectOpenAI = byId("connect-openai")
  const continueModel = byId("continue-model")
  let chat = { ready: false, running: false, sending: false, cancelling: false, permissions: [], forms: [] }
  let composing = false
  let submitted
  let requestKey = ""
  const labels = { disconnected: "연결 안 됨", starting: "서버 준비 중", connecting: "연결 중", connected: "연결됨", unauthorized: "인증 필요", error: "연결 오류" }
  const element = (tag, text, className) => {
    const node = document.createElement(tag)
    if (text !== undefined) node.textContent = text
    if (className) node.className = className
    return node
  }
  const save = () => vscode.setState({ draft: prompt.value })
  const needsModelChoice = () => chat.modelSetup === "choose" || chat.modelSetup === "connecting"
  const canSend = () => chat.ready && !!chat.model && !needsModelChoice() && !chat.running && !chat.sending && !chat.pickingModel && !chat.switchingModel && !chat.permissions.length && !chat.forms.length && !!prompt.value.trim()
  const controls = () => {
    composer.hidden = chat.permissions.length > 0 || chat.forms.length > 0
    send.disabled = !canSend()
    selection.hidden = !chat.ready
    agent.textContent = chat.agent ? `에이전트 · ${chat.agent}` : "에이전트 확인 중"
    const modelName = chat.model ? `${chat.model.providerID}/${chat.model.id}` : ""
    model.textContent = modelName || "모델 선택"
    model.title = modelName ? `모델 변경 (${modelName})` : "모델 선택"
    model.setAttribute("aria-label", model.title)
    model.disabled = !chat.ready || chat.running || chat.sending || !!chat.pickingModel || !!chat.switchingModel || chat.modelSetup === "connecting"
    modelNotice.hidden = !chat.ready || !chat.modelNotice
    modelNotice.textContent = chat.modelNotice || ""
    modelSetup.hidden = !chat.ready || !chat.modelSetup
    connectOpenAI.disabled = model.disabled
    connectOpenAI.textContent = chat.modelSetup === "connecting" ? "OpenAI 연결 중…" : "OpenAI API 키 연결"
    continueModel.hidden = !chat.model || chat.modelSetup === "continue"
    continueModel.disabled = model.disabled
    byId("composer-hint").textContent = chat.cancelling ? "취소 요청 중…" : !chat.ready ? "연결을 기다리는 중…" : chat.running ? "응답 중 · Esc 취소" :
      needsModelChoice() ? "먼저 사용할 모델을 선택해 주세요." : chat.notice || "Enter 전송 · Shift+Enter 줄바꿈"
  }
  const submit = () => {
    if (!canSend() || composing) return
    submitted = prompt.value
    chat.sending = true
    controls()
    vscode.postMessage({ type: "send", text: submitted })
  }
  byId("connect").addEventListener("click", () => vscode.postMessage({ type: "connect" }))
  model.addEventListener("click", () => vscode.postMessage({ type: "pickModel" }))
  connectOpenAI.addEventListener("click", () => vscode.postMessage({ type: "connectOpenAI" }))
  continueModel.addEventListener("click", () => vscode.postMessage({ type: "continueModel" }))
  byId("password").addEventListener("click", () => vscode.postMessage({ type: "password" }))
  byId("configure").addEventListener("click", () => vscode.postMessage({ type: "configure" }))
  byId("composer").addEventListener("submit", (event) => { event.preventDefault(); submit() })
  prompt.value = vscode.getState()?.draft ?? ""
  prompt.addEventListener("input", () => { save(); controls() })
  prompt.addEventListener("compositionstart", () => { composing = true })
  prompt.addEventListener("compositionend", () => { composing = false })
  document.addEventListener("keydown", (event) => {
    if (composing || event.isComposing || event.keyCode === 229 || event.defaultPrevented) return
    if (event.key === "Escape" && chat.ready && chat.running && !chat.cancelling) {
      event.preventDefault()
      chat.cancelling = true
      controls()
      vscode.postMessage({ type: "interrupt" })
    } else if (event.target === prompt && event.key === "Enter" && !event.shiftKey && !event.ctrlKey && !event.altKey && !event.metaKey) {
      event.preventDefault()
      submit()
    }
  })

  const renderMessages = (items) => {
    const fragment = document.createDocumentFragment()
    let hasMessages = false
    for (const item of items) {
      const text = item.blocks.filter((block) => !block.tool && block.text.trim())
      const toolErrors = item.blocks.filter((block) => block.tool && block.status === "error" && block.text.trim() && block.text !== item.error)
      if (!text.length && !toolErrors.length && !item.error) continue
      const article = element("article", undefined, `message ${item.role}`)
      article.append(element("strong", item.role === "user" ? "나" : item.agent || "OpenCode"))
      for (const block of text) article.append(element("div", block.text, "message-text"))
      for (const block of toolErrors) article.append(element("p", `${block.tool} 실패 · ${block.text}`, "error"))
      if (item.error) article.append(element("p", item.error, "error"))
      fragment.append(article)
      hasMessages = true
    }
    messages.replaceChildren(hasMessages ? fragment : emptyState)
  }
  const button = (label, action) => {
    const node = element("button", label)
    node.type = "button"
    node.addEventListener("click", action)
    return node
  }
  const renderRequests = (state) => {
    const key = JSON.stringify([state.permissions, state.forms, state.ready])
    if (key === requestKey) return
    requestKey = key
    const existingForms = new Map([...requests.querySelectorAll("form")].map((node) => [node.dataset.id, node]))
    requests.replaceChildren()
    for (const permission of state.permissions) {
      const existing = existingForms.get(permission.id)
      if (existing && existing.dataset.schema === JSON.stringify(permission) && existing.dataset.ready === String(state.ready)) {
        requests.append(existing)
        continue
      }
      const card = element("form", undefined, "request permission-request")
      card.dataset.id = permission.id
      card.dataset.schema = JSON.stringify(permission)
      card.dataset.ready = String(state.ready)
      card.append(element("strong", "권한 확인", "request-heading"), element("p", permission.message || "이 작업을 허용하시겠습니까?"))
      card.append(element("p", `${permission.action}\n${permission.resources.join("\n")}`, "message-text tool"))
      const choices = element("fieldset", undefined, "permission-choices")
      choices.append(element("legend", "권한 선택", "sr-only"))
      const confirm = element("button", "응답 보내기")
      confirm.type = "submit"
      confirm.disabled = true
      let decision
      for (const [value, label, description] of [["once", "이번만 허용", "이 작업을 한 번 허용합니다"], ["reject", "거절", "이 작업을 거절합니다"]]) {
        const row = element("label", undefined, "permission-option")
        const input = element("input")
        input.type = "radio"
        input.name = `permission-${permission.id}`
        input.value = value
        input.required = true
        input.disabled = !state.ready
        input.addEventListener("change", () => { if (input.checked) { decision = value; confirm.disabled = !state.ready } })
        const text = element("span")
        text.append(element("strong", label), element("small", description))
        row.append(input, text)
        choices.append(row)
      }
      card.append(choices, confirm)
      card.addEventListener("submit", (event) => {
        event.preventDefault()
        if (state.ready && decision) vscode.postMessage({ type: "permission", id: permission.id, decision })
      })
      requests.append(card)
    }
    for (const form of state.forms) {
      const existing = existingForms.get(form.id)
      if (existing && existing.dataset.schema === JSON.stringify(form) && existing.dataset.ready === String(state.ready)) requests.append(existing)
      else renderForm(form, state.ready)
    }
  }
  const renderForm = (form, ready) => {
    const card = element("form", undefined, "request")
    card.dataset.id = form.id
    card.dataset.schema = JSON.stringify(form)
    card.dataset.ready = String(ready)
    card.append(element("strong", form.title))
    const controls = new Map()
    for (const field of form.fields) {
      const row = element("label", undefined, "field")
      row.append(element("span", field.title || field.key))
      if (field.description) row.append(element("small", field.description))
      let input
      let custom
      if (field.type === "external") {
        row.append(element("p", field.url, "message-text"))
        row.append(element("small", "OpenCode CLI에서 이 외부 인증 단계를 진행해 주세요."))
      } else if (field.type === "multiselect") {
        input = element("select")
        input.multiple = true
        for (const option of field.options) {
          const node = element("option", option.label)
          node.value = option.value
          node.selected = field.default?.includes(option.value) ?? false
          input.append(node)
        }
      } else if (field.type === "string" && field.options && !field.custom) {
        input = element("select")
        input.append(element("option", "선택해 주세요"))
        input.firstChild.value = ""
        for (const option of field.options) {
          const node = element("option", option.label)
          node.value = option.value
          input.append(node)
        }
        input.value = field.default ?? ""
      } else {
        input = element("input")
        input.type = field.type === "boolean" ? "checkbox" : ["number", "integer"].includes(field.type) ? "number" : field.format === "uri" ? "url" : field.format === "date-time" ? "datetime-local" : field.format || "text"
        if (field.type === "boolean") input.checked = field.default ?? false
        else input.value = field.default ?? ""
        if (field.type === "integer") input.step = "1"
        if (field.type === "number") input.step = "any"
        for (const [source, target] of [["minimum", "min"], ["maximum", "max"], ["minLength", "minLength"], ["maxLength", "maxLength"], ["pattern", "pattern"], ["placeholder", "placeholder"]]) {
          if (field[source] !== undefined) input[target] = field[source]
        }
      }
      if (field.type === "multiselect" && field.custom) {
        custom = element("textarea")
        custom.rows = 2
        custom.placeholder = "추가 답변 (한 줄에 하나)"
        custom.setAttribute("aria-label", `${field.title || field.key} 추가 답변`)
        custom.value = (field.default || []).filter((value) => !field.options.some((option) => option.value === value)).join("\n")
        row.append(custom)
      }
      if (input) {
        input.required = field.required ?? false
        input.disabled = !ready
        row.append(input)
        controls.set(field.key, { field, input, custom, row })
      }
      card.append(row)
    }
    const value = ({ field, input, custom }) => field.type === "boolean" ? input.checked : field.type === "multiselect" ? [...new Set([...input.selectedOptions].map((option) => option.value).concat(custom?.value.split("\n").map((item) => item.trim()).filter(Boolean) || []))] : ["integer", "number"].includes(field.type) ? Number(input.value) : input.value
    const conditions = () => {
      for (const control of controls.values()) {
        const { field, input, custom, row } = control
        control.inactive = !!field.when?.some((when) => {
          const other = controls.get(when.key)
          const match = other && value(other) === when.value
          return when.op === "eq" ? !match : match
        })
        row.hidden = field.hidden || control.inactive
        input.disabled = !ready || row.hidden
        if (custom) custom.disabled = input.disabled
        if (field.type === "multiselect") {
          const count = value(control).length
          input.setCustomValidity((count < (field.minItems ?? (field.required ? 1 : 0)) || count > (field.maxItems ?? Infinity)) ? "선택 개수를 확인해 주세요." : "")
          input.required = field.required && !custom?.value.trim()
        }
      }
    }
    card.addEventListener("input", conditions)
    card.addEventListener("change", conditions)
    conditions()
    const submit = element("button", "응답 보내기")
    submit.type = "submit"
    submit.disabled = !ready || form.fields.some((field) => field.type === "external")
    const cancel = button("건너뛰기", () => vscode.postMessage({ type: "form", id: form.id }))
    cancel.disabled = !ready
    card.append(submit, cancel)
    card.addEventListener("submit", (event) => {
      event.preventDefault()
      const answer = Object.fromEntries([...controls].filter(([, control]) => !control.inactive && (control.field.type === "boolean" || control.input.value !== "" || control.custom?.value.trim() || (control.field.hidden && control.field.default !== undefined))).map(([key, control]) => [key, value(control)]))
      vscode.postMessage({ type: "form", id: form.id, answer })
    })
    requests.append(card)
  }

  window.addEventListener("message", (event) => {
    const state = event.data
    if (state?.type === "sent") {
      if (prompt.value === submitted) { prompt.value = ""; save() }
      submitted = undefined
      controls()
      return
    }
    if (state?.type === "chat") {
      const wasRequest = composer.hidden
      const wasChoosingModel = needsModelChoice()
      const focusPermission = state.ready && state.permissions[0] &&
        (state.permissions[0].id !== chat.permissions[0]?.id || !chat.ready)
      const atBottom = conversation.scrollHeight - conversation.scrollTop - conversation.clientHeight < 48
      chat = state
      byId("chat-error").hidden = !state.error
      byId("chat-error").textContent = state.error || ""
      renderMessages(state.messages)
      renderRequests(state)
      if (atBottom) conversation.scrollTop = conversation.scrollHeight
      controls()
      if (focusPermission) requests.querySelector(".permission-request")?.querySelector("input")?.focus()
      else if (wasRequest && !composer.hidden) prompt.focus()
      else if (wasChoosingModel && !needsModelChoice() && chat.ready && !composer.hidden) prompt.focus()
      return
    }
    if (!state || state.type !== "connection" || !Object.hasOwn(labels, state.status)) return
    byId("status").textContent = labels[state.status]
    const summary = byId("connection-summary")
    summary.dataset.status = state.status
    summary.title = `${state.address}\n${state.message}${state.version ? ` (v${state.version})` : ""}`.trim()
    byId("status").setAttribute("aria-label", `${labels[state.status]}. ${summary.title}`)
    byId("status").setAttribute("role", ["error", "unauthorized"].includes(state.status) ? "alert" : "status")
    byId("connect").disabled = ["connecting", "starting"].includes(state.status)
    byId("password").hidden = state.status !== "unauthorized"
    if (state.status !== "connected") { chat.ready = false; controls() }
    if (byId("empty-message")) byId("empty-message").textContent = state.status === "connected" ? "메시지를 입력해 대화를 시작하세요." : "작업할 프로젝트를 열고 OpenCode 서버에 연결해 주세요."
  })
  controls()
  vscode.postMessage({ type: "ready" })
})()
