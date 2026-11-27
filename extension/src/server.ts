export type ServerInfo = {
  version: string
  pid: number
  urls: string[]
  paths: { tmp: string }
}

export class ServerConnectionError extends Error {
  readonly needsPassword: boolean;

  constructor(message: string, needsPassword = false) {
    super(message);
    this.needsPassword = needsPassword;
  }
}

export function serverUrl(value: string) {
  let url: URL;
  try {
    url = new URL(value.trim());
  } catch {
    throw new ServerConnectionError("http://localhost:4096 형식의 서버 주소를 입력해 주세요.");
  }
  if (!["http:", "https:"].includes(url.protocol) || url.username || url.password || url.search || url.hash) {
    throw new ServerConnectionError("HTTP(S) 주소를 사용하고, 비밀번호·쿼리·#은 주소에 넣지 마세요.");
  }
  return url.toString().replace(/\/+$/, "");
}

// shortcut: 연결 확인만 직접 요청한다. 채팅 API를 추가할 때 @opencode/client로 통합한다.
export async function getServerInfo(address: string, password: string | undefined, signal: AbortSignal) {
  const url = `${serverUrl(address)}/api/info`;
  const timeout = AbortSignal.timeout(5_000);
  let response: Response;
  try {
    response = await fetch(url, {
      headers: {
        Accept: "application/json",
        ...(password ? { Authorization: `Basic ${Buffer.from(`opencode:${password}`).toString("base64")}` } : {}),
      },
      redirect: "error",
      signal: AbortSignal.any([signal, timeout]),
    });
  } catch (error) {
    if (signal.aborted) {
      throw error;
    }
    throw new ServerConnectionError(
      timeout.aborted
        ? "서버 응답 시간이 초과되었습니다. 서버 상태를 확인하고 다시 연결해 주세요."
        : "서버에 연결할 수 없습니다. 주소와 서버 실행 상태를 확인해 주세요.",
    );
  }
  if (response.status === 401 || response.status === 403) {
    throw new ServerConnectionError("인증에 실패했습니다. 서버 비밀번호를 입력하고 다시 연결해 주세요.", true);
  }
  if (!response.ok) {
    throw new ServerConnectionError(`서버가 오류를 반환했습니다. (HTTP ${response.status})`);
  }
  let info: unknown;
  try {
    info = await response.json();
  } catch {
    throw new ServerConnectionError("서버 정보를 읽을 수 없습니다. 서버 주소인지 확인해 주세요.");
  }
  if (!isServerInfo(info)) {
    throw new ServerConnectionError("지원하는 서버 응답이 아닙니다. 서버 주소와 버전을 확인해 주세요.");
  }
  return info;
}

function isServerInfo(info: unknown): info is ServerInfo {
  return (
    typeof info === "object" && info !== null &&
    "version" in info && typeof info.version === "string" && info.version.trim().length > 0 &&
    "pid" in info && typeof info.pid === "number" && Number.isInteger(info.pid) && info.pid >= 0 &&
    "urls" in info && Array.isArray(info.urls) && info.urls.every((url) => typeof url === "string") &&
    "paths" in info && typeof info.paths === "object" && info.paths !== null &&
    "tmp" in info.paths && typeof info.paths.tmp === "string"
  );
}
