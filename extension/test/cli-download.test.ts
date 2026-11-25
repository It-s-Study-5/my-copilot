import assert from "node:assert/strict"
import { createHash } from "node:crypto"
import { createServer } from "node:http"
import { test } from "node:test"
import { mkdtemp, readFile, rm, stat } from "node:fs/promises"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { gzipSync } from "node:zlib"
import { ensureCli } from "../src/cli-download"

const target = `${process.platform}-${process.arch}`
const body = Buffer.from("#!/bin/sh\necho fake-cli\n")

async function withReleases(checksum: string, run: (url: string, hits: string[]) => Promise<void>) {
  const hits: string[] = []
  const gz = gzipSync(body)
  const server = createServer((request, response) => {
    hits.push(request.url ?? "")
    if (request.url === `/cli-v1.0.0/opencode-${target}.gz.sha256`) {
      response.end(`${checksum || createHash("sha256").update(gz).digest("hex")}  opencode-${target}.gz\n`)
    } else if (request.url === `/cli-v1.0.0/opencode-${target}.gz`) {
      response.end(gz)
    } else {
      response.statusCode = 404
      response.end()
    }
  })
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve))
  try {
    await run(`http://127.0.0.1:${(server.address() as { port: number }).port}`, hits)
  } finally {
    server.close()
  }
}

test("downloads, verifies and caches the CLI", async () => {
  const storage = await mkdtemp(join(tmpdir(), "opencode-cli-"))
  try {
    await withReleases("", async (url, hits) => {
      const path = await ensureCli(storage, "1.0.0", new AbortController().signal, url)
      assert.deepEqual(await readFile(path), body)
      if (process.platform !== "win32") assert.ok(((await stat(path)).mode & 0o111) !== 0)
      const count = hits.length
      assert.equal(await ensureCli(storage, "1.0.0", new AbortController().signal, url), path)
      assert.equal(hits.length, count)
    })
  } finally {
    await rm(storage, { recursive: true, force: true })
  }
})

test("rejects a checksum mismatch and leaves no executable", async () => {
  const storage = await mkdtemp(join(tmpdir(), "opencode-cli-"))
  try {
    await withReleases("0".repeat(64), async (url) => {
      await assert.rejects(ensureCli(storage, "1.0.0", new AbortController().signal, url), /체크섬/)
      await assert.rejects(stat(join(storage, "cli", "1.0.0", "opencode")))
    })
  } finally {
    await rm(storage, { recursive: true, force: true })
  }
})

test("reports a missing release", async () => {
  const storage = await mkdtemp(join(tmpdir(), "opencode-cli-"))
  try {
    await withReleases("", async (url) => {
      await assert.rejects(ensureCli(storage, "9.9.9", new AbortController().signal, url), /HTTP 404/)
    })
  } finally {
    await rm(storage, { recursive: true, force: true })
  }
})
