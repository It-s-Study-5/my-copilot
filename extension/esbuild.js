const esbuild = require("esbuild")
const { copyFile, mkdir } = require("node:fs/promises")
const path = require("node:path")

// Ship only the modules needed to run gate.py on the extension host.
const slopFiles = [
  "gate.py", "conduit_probe.py", "conduit_probe.cjs", "model_client.py",
  "review_edits.py", "slop_agent.py", "staged_slop.py", "user_report.py",
]
const slopSource = path.join(__dirname, "..", "ai-slop")
const slopOutput = path.join(__dirname, "dist", "ai-slop")

async function bundleSlop() {
  await mkdir(slopOutput, { recursive: true })
  await Promise.all(slopFiles.map((file) => copyFile(path.join(slopSource, file), path.join(slopOutput, file))))
}

const production = process.argv.includes("--production")
const watch = process.argv.includes("--watch")

/**
 * @type {import('esbuild').Plugin}
 */
const esbuildProblemMatcherPlugin = {
  name: "esbuild-problem-matcher",

  setup(build) {
    build.onStart(() => {
      console.log("[watch] build started")
    })
    build.onEnd((result) => {
      result.errors.forEach(({ text, location }) => {
        console.error(`✘ [ERROR] ${text}`)
        console.error(`    ${location.file}:${location.line}:${location.column}:`)
      })
      console.log("[watch] build finished")
    })
  },
}

async function main() {
  await bundleSlop()
  const ctx = await esbuild.context({
    entryPoints: ["src/extension.ts"],
    bundle: true,
    format: "cjs",
    minify: production,
    sourcemap: !production,
    sourcesContent: false,
    platform: "node",
    outfile: "dist/extension.js",
    external: ["vscode"],
    logLevel: "silent",
    plugins: [
      /* add to the end of plugins array */
      esbuildProblemMatcherPlugin,
    ],
  })
  if (watch) {
    await ctx.watch()
  } else {
    await ctx.rebuild()
    await ctx.dispose()
  }
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
