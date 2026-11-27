import assert from "node:assert/strict"
import { mkdtemp, rm, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { test } from "node:test"
import { runSlop } from "../src/slop"

async function withEngine(source: string, run: (engine: string, root: string) => Promise<void>) {
  const root = await mkdtemp(join(tmpdir(), "slop bridge "))
  try {
    const engine = join(root, "gate.py")
    await writeFile(engine, source)
    await run(engine, root)
  } finally {
    await rm(root, { recursive: true, force: true })
  }
}

test("Slop passes an option-looking question and workspace path as literal arguments", async () => {
  await withEngine("import json, sys\nprint(json.dumps(sys.argv[1:]))", async (engine, root) => {
    const question = '--working; echo "test"'
    const text = await runSlop(engine, root, question, new AbortController().signal)
    assert.deepEqual(JSON.parse(text), ["--root", root, "--working", "--request=" + question])
  })
})

for (const code of [0, 1, 2]) {
  test(`Slop displays the engine report on exit ${code}`, async () => {
    await withEngine(`print("검사 근거")\nraise SystemExit(${code})`, async (engine, root) => {
      assert.equal(await runSlop(engine, root, "", new AbortController().signal), "검사 근거")
    })
  })
}

test("Slop reports engine and runtime errors without forwarding Python stderr", async () => {
  await withEngine('raise RuntimeError("private stderr")', async (engine, root) => {
    await assert.rejects(runSlop(engine, root, "확인", new AbortController().signal), /설치 상태/)
    await assert.rejects(runSlop(join(root, "missing.py"), root, "", new AbortController().signal), /엔진이 포함된/)
  })
})

test("Slop cancellation interrupts a running engine", async () => {
  await withEngine("import time\ntime.sleep(30)", async (engine, root) => {
    const controller = new AbortController()
    const pending = runSlop(engine, root, "확인", controller.signal)
    setTimeout(() => controller.abort(), 100)
    await assert.rejects(pending, /취소/)
  })
})

test("cancelling Slop also stops a model subprocess", async () => {
  const { access } = await import("node:fs/promises")
  const source = [
    "import pathlib, subprocess, sys",
    "p = subprocess.Popen([sys.executable, '-c', \"import pathlib,time; pathlib.Path('started').touch(); time.sleep(0.8); pathlib.Path('completed').touch()\"])",
    "p.wait()",
  ].join("\n")
  await withEngine(source, async (engine, root) => {
    const controller = new AbortController()
    const pending = runSlop(engine, root, "검사", controller.signal)
    for (let tries = 0; tries < 100; tries++) {
      if (await access(join(root, "started")).then(() => true, () => false)) { break }
      await new Promise(resolve => setTimeout(resolve, 20))
    }
    await access(join(root, "started"))
    controller.abort()
    await assert.rejects(pending, /취소/)
    await new Promise(resolve => setTimeout(resolve, 900))
    await assert.rejects(access(join(root, "completed")), { code: "ENOENT" })
  })
})
