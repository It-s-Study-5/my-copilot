import { execFile, spawn } from "node:child_process";
import { access } from "node:fs/promises";
import { dirname } from "node:path";

export async function runSlop(engine: string, root: string, question: string, signal: AbortSignal): Promise<string> {
  signal.throwIfAborted();
  try {
    await access(engine);
  } catch {
    throw new Error("확장에 Slop 검사기가 없습니다. 엔진이 포함된 버전을 설치해 주세요.");
  }

  const windows = process.platform === "win32";
  const args = [...(windows ? ["-3"] : []), "-B", "-X", "utf8", engine, "--root", root, "--working", `--request=${question}`];
  signal.throwIfAborted();
  return new Promise((resolve, reject) => {
    const child = spawn(windows ? "py" : "python3", args, {
      cwd: dirname(engine), detached: !windows, windowsHide: true, stdio: ["ignore", "pipe", "ignore"],
    });
    const chunks: Buffer[] = [];
    let bytes = 0;
    let stopped: string | undefined;
    const stop = (reason: string) => {
      if (stopped) { return; }
      stopped = reason;
      if (!child.pid) { return; }
      if (windows) {
        execFile("taskkill.exe", ["/pid", String(child.pid), "/t", "/f"], { windowsHide: true },
          (error) => { if (error && child.exitCode === null) { child.kill(); } });
      } else {
        try { process.kill(-child.pid, "SIGKILL"); }
        catch { child.kill(); }
      }
    };
    const cancel = () => stop("Slop 검사를 취소했습니다.");
    const timeout = setTimeout(() => stop("Slop 검사 시간이 초과됐습니다. 모델 연결을 확인해 주세요."), 240_000);
    signal.addEventListener("abort", cancel, { once: true });
    if (signal.aborted) { cancel(); }
    child.stdout.on("data", (chunk: Buffer) => {
      bytes += chunk.length;
      if (bytes > 1024 * 1024) { stop("Slop 검사 결과가 너무 큽니다. 변경 범위를 줄여 주세요."); }
      else { chunks.push(chunk); }
    });
    child.once("error", (error: NodeJS.ErrnoException) => {
      reject(new Error(error.code === "ENOENT"
        ? `Python 3을 실행할 수 없습니다. ${windows ? "py -3" : "python3"} 설치와 PATH를 확인해 주세요.`
        : "Slop 검사기를 시작할 수 없습니다."));
    });
    child.once("close", (code) => {
      clearTimeout(timeout);
      signal.removeEventListener("abort", cancel);
      const report = Buffer.concat(chunks).toString("utf8").trim();
      if (stopped) { reject(new Error(stopped)); }
      else if (report && (code === 0 || code === 1 || code === 2)) { resolve(report); }
      else { reject(new Error("Slop 검사 결과를 읽을 수 없습니다. Python 3과 검사기 설치 상태를 확인해 주세요.")); }
    });
  });
}
