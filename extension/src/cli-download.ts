import { createHash } from "node:crypto";
import { createReadStream, createWriteStream } from "node:fs";
import { chmod, mkdir, rename, rm, stat } from "node:fs/promises";
import { join } from "node:path";
import { Readable } from "node:stream";
import { pipeline } from "node:stream/promises";
import { createGunzip } from "node:zlib";
import { ServerConnectionError } from "./server";

const RELEASES = "https://github.com/It-s-Study-5/my-copilot/releases/download";
const TARGETS = ["darwin-arm64", "darwin-x64", "linux-arm64", "linux-x64", "win32-arm64", "win32-x64"];

async function fetchOk(url: string, signal: AbortSignal) {
  let response: Response;
  try {
    response = await fetch(url, { signal: AbortSignal.any([signal, AbortSignal.timeout(120_000)]) });
  } catch (error) {
    if (signal.aborted) {
      throw error;
    }
    throw new ServerConnectionError("서버용 CLI를 내려받을 수 없습니다. 네트워크를 확인하거나 opencode.cliPath에 CLI 경로를 지정해 주세요.");
  }
  if (!response.ok || !response.body) {
    throw new ServerConnectionError(`서버용 CLI 다운로드에 실패했습니다. (HTTP ${response.status})`);
  }
  return response;
}

// shortcut: 두 창이 동시에 처음 실행되면 각자 내려받는다(rename이 원자적이라 결과는 안전하다). 문제가 되면 잠금 파일을 추가한다.
export async function ensureCli(storage: string, version: string, signal: AbortSignal, releases = RELEASES) {
  const target = `${process.platform}-${process.arch}`;
  if (!TARGETS.includes(target)) {
    throw new ServerConnectionError(`지원하지 않는 플랫폼(${target})입니다. opencode.cliPath에 CLI 경로를 지정해 주세요.`);
  }
  const directory = join(storage, "cli", version);
  const executable = join(directory, process.platform === "win32" ? "opencode.exe" : "opencode");
  if (await stat(executable).then((file) => file.isFile(), () => false)) {
    return executable;
  }

  const base = `${releases}/cli-v${version}/opencode-${target}.gz`;
  const expected = (await (await fetchOk(`${base}.sha256`, signal)).text()).trim().split(/\s+/)[0]?.toLowerCase();
  const archive = `${executable}.download.gz`;
  const partial = `${executable}.download`;
  await mkdir(directory, { recursive: true });
  try {
    await pipeline(Readable.fromWeb((await fetchOk(base, signal)).body as never), createWriteStream(archive), { signal });
    const hash = createHash("sha256");
    await pipeline(createReadStream(archive), hash, { signal });
    if (hash.digest("hex") !== expected) {
      throw new ServerConnectionError("내려받은 서버용 CLI의 체크섬이 일치하지 않아 사용하지 않습니다.");
    }
    await pipeline(createReadStream(archive), createGunzip(), createWriteStream(partial), { signal });
    await chmod(partial, 0o755);
    await rename(partial, executable);
  } finally {
    await Promise.all([rm(archive, { force: true }), rm(partial, { force: true })]);
  }
  return executable;
}
