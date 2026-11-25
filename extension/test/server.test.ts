import assert from "node:assert/strict"
import { createServer, type RequestListener } from "node:http"
import { test } from "node:test"
import { mkdtemp, readFile, rm } from "node:fs/promises"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { getServerInfo, serverUrl, ServerConnectionError } from "../src/server"
import { isSidebarMessage } from "../src/protocol"
import { ensureLocalServer } from "../src/local-server"

const info = { version: "2.4.0", pid: 123, urls: ["http://localhost:4096"], paths: { tmp: "/tmp/opencode" } }

const cli = `
const fs = require('node:fs');
const config = JSON.parse(process.argv[1]);
const args = process.argv.slice(2);
fs.appendFileSync(config.log, JSON.stringify(args) + '\\n');
if (config.fail) { console.error('test-secret-must-not-leak'); process.exit(1); }
if (config.wait) { setInterval(() => {}, 1000); }
else if (args.join(' ') === 'service start') { console.log(config.address); }
else if (args.join(' ') === 'service get password') { console.log(config.password); }
else { process.exit(2); }
`

async function withCli(
  config: { address: string; password: string; fail?: boolean; wait?: boolean },
  run: (command: string[], log: string) => Promise<void>,
) {
  const directory = await mkdtemp(join(tmpdir(), "opencode-cli-test-"))
  const log = join(directory, "calls.jsonl")
  try {
    await run([process.execPath, "-e", cli, JSON.stringify({ ...config, log })], log)
  } finally {
    await rm(directory, { recursive: true, force: true })
  }
}

async function withServer(handler: RequestListener, run: (address: string) => Promise<void>) {
  const server = createServer(handler)
  await new Promise<void>((resolve, reject) => {
    server.once("error", reject)
    server.listen(0, "127.0.0.1", resolve)
  })
  const address = server.address()
  assert.ok(address && typeof address === "object")
  try {
    await run(`http://127.0.0.1:${address.port}`)
  } finally {
    server.closeAllConnections()
    await new Promise<void>((resolve, reject) => server.close((error) => error ? reject(error) : resolve()))
  }
}

test("normalizes server URLs and rejects credentials and non-HTTP URLs", () => {
  assert.equal(serverUrl(" http://localhost:4096/ "), "http://localhost:4096")
  assert.equal(serverUrl("https://example.com/opencode/"), "https://example.com/opencode")
  for (const address of ["", "localhost:4096", "file:///tmp", "https://user:secret@example.com", "https://example.com?token=secret", "https://example.com/#token"]) {
    assert.throws(() => serverUrl(address), ServerConnectionError)
  }
})

test("checks the actual info endpoint with optional Basic authentication and a base path", async () => {
  await withServer((request, response) => {
    assert.equal(request.url, "/opencode/api/info")
    assert.equal(request.headers.authorization, `Basic ${Buffer.from("opencode:secret").toString("base64")}`)
    response.setHeader("Content-Type", "application/json")
    response.end(JSON.stringify(info))
  }, async (address) => {
    assert.deepEqual(await getServerInfo(`${address}/opencode/`, "secret", new AbortController().signal), info)
  })
})

test("does not send an Authorization header when no password is supplied", async () => {
  await withServer((request, response) => {
    assert.equal(request.headers.authorization, undefined)
    response.end(JSON.stringify(info))
  }, async (address) => {
    assert.deepEqual(await getServerInfo(address, undefined, new AbortController().signal), info)
  })
})

test("distinguishes authentication failures from other HTTP errors", async () => {
  for (const status of [401, 403, 500]) {
    await withServer((_request, response) => {
      response.writeHead(status).end()
    }, async (address) => {
      await assert.rejects(getServerInfo(address, undefined, new AbortController().signal), (error) => {
        assert.ok(error instanceof ServerConnectionError)
        assert.equal(error.needsPassword, status !== 500)
        return true
      })
    })
  }
})

test("rejects unrelated servers and malformed responses", async () => {
  for (const body of ["<html>not OpenCode</html>", "null", '{"version":"2.4.0"}', JSON.stringify({ ...info, pid: -1 })]) {
    await withServer((_request, response) => response.end(body), async (address) => {
      await assert.rejects(getServerInfo(address, undefined, new AbortController().signal), ServerConnectionError)
    })
  }
})

test("does not follow redirects carrying server credentials", async () => {
  let redirected = false
  await withServer((_request, response) => {
    redirected = true
    response.end(JSON.stringify(info))
  }, async (destination) => {
    await withServer((_request, response) => response.writeHead(302, { Location: destination }).end(), async (address) => {
      await assert.rejects(getServerInfo(address, "secret", new AbortController().signal), ServerConnectionError)
    })
  })
  assert.equal(redirected, false)
})

test("cancels an in-flight connection when its owner is disposed", async () => {
  await withServer(() => {}, async (address) => {
    const controller = new AbortController()
    const request = getServerInfo(address, undefined, controller.signal)
    controller.abort()
    await assert.rejects(request, { name: "AbortError" })
  })
})

test("times out when the server never responds", async () => {
  await withServer(() => {}, async (address) => {
    await assert.rejects(getServerInfo(address, undefined, new AbortController().signal), /응답 시간이 초과/)
  })
})

test("accepts only supported Webview actions", () => {
  for (const type of ["ready", "connect", "configure", "password"]) {
    assert.equal(isSidebarMessage({ type }), true)
  }
  for (const message of [null, undefined, "connect", {}, { type: 1 }, { type: "send" }, { type: "__proto__" }]) {
    assert.equal(isSidebarMessage(message), false)
  }
})

test("uses the CLI service lifecycle and authenticates the returned local endpoint", async () => {
  await withServer((request, response) => {
    assert.equal(request.headers.authorization, `Basic ${Buffer.from("opencode:managed-password").toString("base64")}`)
    response.end(JSON.stringify(info))
  }, async (address) => {
    await withCli({ address, password: "managed-password" }, async (command, log) => {
      const endpoint = await ensureLocalServer(new AbortController().signal, command)
      assert.equal(endpoint.address, address)
      assert.deepEqual(await getServerInfo(endpoint.address, endpoint.password, new AbortController().signal), info)
      assert.equal(await readFile(log, "utf8"), '["service","start"]\n["service","get","password"]\n')
      assert.deepEqual(await ensureLocalServer(new AbortController().signal, command), endpoint)
    })
  })
})

test("reports a missing CLI without exposing an internal process error", async () => {
  await assert.rejects(
    ensureLocalServer(new AbortController().signal, [join(tmpdir(), "nonexistent-opencode-for-test", "opencode")]),
    /OpenCode CLI를 찾을 수 없습니다/,
  )
})

test("reports CLI startup failure without leaking its stderr", async () => {
  await withCli({ address: "http://localhost:4096", password: "test-only", fail: true }, async (command) => {
    await assert.rejects(ensureLocalServer(new AbortController().signal, command), (error) => {
      assert.ok(error instanceof ServerConnectionError)
      assert.match(error.message, /서버를 준비하지 못했습니다/)
      assert.doesNotMatch(error.message, /test-secret-must-not-leak/)
      return true
    })
  })
})

test("rejects remote CLI addresses before reading the service credential", async () => {
  await withCli({ address: "https://example.com", password: "test-only" }, async (command, log) => {
    await assert.rejects(ensureLocalServer(new AbortController().signal, command), /로컬 OpenCode 서비스 주소가 아닙니다/)
    assert.equal(await readFile(log, "utf8"), '["service","start"]\n')
  })
})

test("uses loopback when the local service advertises a wildcard bind", async () => {
  for (const [address, expected] of [["http://0.0.0.0:4096", "http://127.0.0.1:4096"], ["http://[::]:4096", "http://[::1]:4096"]]) {
    await withCli({ address, password: "test-only" }, async (command) => {
      assert.equal((await ensureLocalServer(new AbortController().signal, command)).address, expected)
    })
  }
})

test("rejects missing local service credentials", async () => {
  await withCli({ address: "http://localhost:4096", password: "" }, async (command) => {
    await assert.rejects(ensureLocalServer(new AbortController().signal, command), /인증 정보를 읽을 수 없습니다/)
  })
})

test("cancels a pending CLI startup", async () => {
  await withCli({ address: "http://localhost:4096", password: "test-only", wait: true }, async (command) => {
    const controller = new AbortController()
    const pending = ensureLocalServer(controller.signal, command)
    const timer = setTimeout(() => controller.abort(), 100)
    try {
      await assert.rejects(pending, { name: "AbortError" })
    } finally {
      clearTimeout(timer)
    }
  })
})
