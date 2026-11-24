import { ChatFixture } from "./chat-fixture"
import { setTimeout as delay } from "node:timers/promises"

const fixture = new ChatFixture()
let turn = 0
fixture.onReply = () => fixture.finish("요청 응답을 받았습니다.", `msg_assistant${turn}`)
fixture.onPrompt = async (text) => {
  const id = `msg_assistant${++turn}`
  fixture.assistant(id)
  fixture.event("session.text.started", { sessionID: fixture.sessionID, assistantMessageID: id, ordinal: 0 })
  if (text.includes("권한")) {
    const request = { id: `per_${turn}`, sessionID: fixture.sessionID, action: "shell", resources: ["pwd (fixture only)"] }
    fixture.permissions.push(request)
    fixture.event("permission.asked", request)
    return
  }
  if (text.includes("질문")) {
    const form = { id: `frm_${turn}`, sessionID: fixture.sessionID, title: "추가 질문 (fixture)", fields: [{ key: "choice", title: "언어 선택", type: "string", required: true, options: [{ label: "TypeScript", value: "ts" }, { label: "Python", value: "py" }] }, { key: "note", title: "추가 설명", type: "string" }] }
    fixture.forms.push(form)
    fixture.event("form.created", { form })
    return
  }
  void (async () => {
    for (const delta of ["안녕하세요. ", "OpenCode 채팅 ", "스트리밍 검증입니다."]) {
      await delay(text.includes("취소") ? 5000 : 400)
      if (!fixture.running) return
      fixture.event("session.text.delta", { sessionID: fixture.sessionID, assistantMessageID: id, ordinal: 0, delta })
    }
    fixture.finish("안녕하세요. OpenCode 채팅 스트리밍 검증입니다.", id)
  })()
}
await fixture.listen(41963)
console.log(`Chat transport fixture (no model): ${fixture.address}`)
process.on("SIGINT", () => { void fixture.close().then(() => process.exit()) })
