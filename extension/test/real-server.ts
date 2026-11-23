import assert from "node:assert/strict"
import { execFile } from "node:child_process"
import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises"
import { createServer } from "node:net"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { promisify } from "node:util"
import { ensureLocalServer } from "../src/local-server"
import { getServerInfo } from "../src/server"

const command = process.argv.slice(2)
if (command.length === 0) command.push("opencode")
const execute = promisify(execFile)
const root = await mkdtemp(join(tmpdir(), "opencode-real-server-"))
console.log(`Isolated server verification: ${root}`)
for (const name of ["config", "state", "data", "cache"] as const) {
  const directory = join(root, name)
  await mkdir(directory)
  process.env[`XDG_${name.toUpperCase()}_HOME`] = directory
}
for (const name of ["OPENCODE_CONFIG_DIR", "OPENCODE_CONFIG", "OPENCODE_CONFIG_CONTENT", "OPENCODE_PASSWORD", "OPENCODE_SERVER_PASSWORD"]) {
  delete process.env[name]
}
process.env.OPENCODE_CONFIG_PROJECT_DISABLE = "1"
process.env.OPENCODE_DISABLE_MODELS_FETCH = "1"
const run = async (args: string[]) => (await execute(command[0], [...command.slice(1), ...args], {
  timeout: 130_000, maxBuffer: 64 * 1024, windowsHide: true,
})).stdout.trim()

const socket = createServer()
await new Promise<void>((resolve, reject) => {
  socket.once("error", reject)
  socket.listen(0, "127.0.0.1", resolve)
})
const listening = socket.address()
assert.ok(listening && typeof listening === "object")
const port = listening.port
await new Promise<void>((resolve, reject) => socket.close((error) => error ? reject(error) : resolve()))

let report
try {
  assert.equal(await run(["service", "status"]), "stopped")
  await run(["service", "set", "port", String(port)])
  const first = await ensureLocalServer(new AbortController().signal, command)
  const info = await getServerInfo(first.address, first.password, new AbortController().signal)
  assert.ok(info.pid > 0)
  assert.ok(!info.version.includes("fixture"))
  assert.equal(new URL(first.address).port, String(port))
  assert.equal((await fetch(`${first.address}/api/info`)).status, 401)

  const again = await ensureLocalServer(new AbortController().signal, command)
  assert.equal(again.address, first.address)
  assert.ok(again.password === first.password, "service credential must be reused")
  assert.equal((await getServerInfo(again.address, again.password, new AbortController().signal)).pid, info.pid)
  const concurrent = await Promise.all([
    ensureLocalServer(new AbortController().signal, command),
    ensureLocalServer(new AbortController().signal, command),
  ])
  for (const endpoint of concurrent) {
    assert.equal(endpoint.address, first.address)
    assert.equal((await getServerInfo(endpoint.address, endpoint.password, new AbortController().signal)).pid, info.pid)
  }
  report = { verifiedAt: new Date().toISOString(), version: info.version, pid: info.pid, address: first.address,
    coldStart: true, authenticatedInfo: true, unauthenticatedStatus: 401, reusedPid: true, concurrentReuse: true }
} finally {
  await run(["service", "stop"])
  assert.equal(await run(["service", "status"]), "stopped")
  await rm(root, { recursive: true, force: true })
}
const result = { ...report, stopped: true }
await writeFile(new URL("./server-startup-result.json", import.meta.url), JSON.stringify(result, null, 2) + "\n")
console.log(JSON.stringify(result, null, 2))
