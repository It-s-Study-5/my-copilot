import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { serverUrl, ServerConnectionError } from "./server";

const execute = promisify(execFile);

export async function ensureLocalServer(signal: AbortSignal, command: readonly string[] = ["opencode"]) {
  const [executable, ...prefix] = command;
  if (!executable) {
    throw new ServerConnectionError("서버 실행 파일을 찾을 수 없습니다.");
  }
  const run = async (args: string[]) => {
    try {
      const result = await execute(executable, [...prefix, "service", ...args], {
        signal,
        timeout: 130_000,
        maxBuffer: 64 * 1024,
        windowsHide: true,
      });
      return result.stdout.trim();
    } catch (error) {
      if (signal.aborted) {
        throw error;
      }
      if (error instanceof Error && "code" in error && error.code === "ENOENT") {
        throw new ServerConnectionError("서버용 CLI를 찾을 수 없습니다. CLI를 설치하고 VS Code를 다시 시작하거나 서버 주소를 지정해 주세요.");
      }
      throw new ServerConnectionError("서버를 준비하지 못했습니다. 터미널에서 opencode service start를 확인하거나 서버 주소를 지정해 주세요.");
    }
  };

  // The CLI owns daemon discovery, concurrent startup, and its stored service credential.
  const url = new URL(serverUrl(await run(["start"])));
  if (url.hostname === "0.0.0.0") {
    url.hostname = "127.0.0.1";
  }
  if (url.hostname === "[::]") {
    url.hostname = "[::1]";
  }
  if (!["localhost", "127.0.0.1", "[::1]"].includes(url.hostname)) {
    throw new ServerConnectionError("로컬 서비스 주소가 아닙니다. 서버 주소를 직접 지정해 주세요.");
  }
  const password = await run(["get", "password"]);
  if (!password) {
    throw new ServerConnectionError("서버 인증 정보를 읽을 수 없습니다. CLI의 서비스 설정을 확인해 주세요.");
  }
  return { address: serverUrl(url.toString()), password };
}
