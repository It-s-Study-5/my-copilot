# OpenCode VS Code Extension

OpenCode 서버의 단일 세션과 대화하는 VS Code 확장입니다. 현재 workspace의 첫 번째 폴더에 세션을 만들고 메시지 전송·SSE 스트리밍·취소·승인·질문 응답을 처리합니다. 여러 채팅 탭과 VS Code 재시작 후 세션 복원은 #6의 범위입니다.

기본 위치는 **오른쪽 보조 사이드바**입니다. VS Code의 정식 `secondarySidebar` 기여 지점을 사용하므로 **VS Code 1.106 이상**이 필요합니다. [공식 지원 안내](https://code.visualstudio.com/updates/v1_106#_view-containers-in-secondary-side-bar)

## 개발 실행

VS Code 1.106 이상, Bun 1.4.4 이상, Node.js 22 이상과 PATH의 `code` 명령을 준비합니다. 자동 연결에는 `opencode service start`를 지원하는 OpenCode CLI 2.4.0이 VS Code 프로세스의 PATH에 있어야 합니다. CLI가 없다면 아래의 **소스 서버에 직접 연결** 절차를 사용합니다.

저장소 루트에서 다음 명령을 실행합니다.

```sh
cd extension
bun install --frozen-lockfile
bun run compile
code --new-window --extensionDevelopmentPath="$PWD" ..
```

PowerShell에서는 마지막 명령을 `code --new-window --extensionDevelopmentPath="$($PWD.Path)" ..`로 실행합니다. 새로 열린 **Extension Development Host** 창에서 오른쪽 보조 사이드바의 OpenCode 탭, 명령 팔레트의 `Open opencode Chat`, 또는 `Cmd+Esc`(Windows/Linux: `Ctrl+Esc`)로 채팅을 엽니다.

위 명령의 `..`는 **코드를 읽고 쓸 작업 폴더**입니다. 다른 프로젝트를 작업하려면 그 폴더 경로로 바꾸세요. 확장은 workspace의 첫 번째 폴더를 사용하므로 작업할 프로젝트가 열린 개발 창에서 채팅을 시작해야 합니다.

서버 주소가 비어 있으면 사이드바를 여는 시점에 로컬 서버를 자동 실행·재사용합니다. CLI 설치 후에도 찾지 못하면 VS Code를 완전히 종료한 뒤 PATH가 반영된 환경에서 다시 실행하세요. 화면 코드를 바꾼 뒤에는 `bun run compile`로 다시 빌드하고 개발 창의 `Developer: Reload Window`를 실행합니다.

### 소스 서버에 직접 연결

CLI를 전역 설치하지 않고 저장소의 서버를 사용할 때는 별도 터미널에서 다음을 실행합니다.

```sh
cd opencode
bun install --frozen-lockfile
bun run dev serve --port 4096
```

이 실행 명령은 기본적으로 서버 비밀번호를 생성해 `server password ...`로 출력합니다. 그 뒤의 값을 복사해 둡니다. 서버 실행 시 `OPENCODE_PASSWORD`를 따로 지정했다면 그 값을 사용합니다.

다른 터미널에서 위의 확장 빌드·실행 명령을 실행한 뒤 개발 창에서 연결합니다.

1. **서버 주소 설정** 아이콘에 `http://127.0.0.1:4096`을 저장합니다. 또는 작업 폴더의 `.vscode/settings.json`에 `"opencode.serverUrl": "http://127.0.0.1:4096"`을 지정합니다. 주소가 비어 있으면 수동 서버 대신 PATH의 CLI로 자동 연결을 시도합니다.
2. **인증 필요** 상태에서 **비밀번호 입력** 아이콘을 눌러 서버 터미널의 `server password` 값을 입력합니다. 입력 후 자동 재연결됩니다.
3. **연결됨**을 확인합니다. `HTTP 401`은 비밀번호가 없거나 맞지 않다는 뜻입니다.

수동 연결 중에는 서버 터미널을 유지해야 합니다. 서버 재시작 후 비밀번호가 바뀌면 새 값을 입력하세요. 주소를 지우면 자동 연결로 돌아갑니다.

## 모델 연결

**연결됨** 상태만으로 모델 인증까지 완료된 것은 아닙니다. 실제 답변·파일 생성에는 서버에서 사용할 수 있는 모델이 필요합니다. 자동 연결용 CLI를 사용하는 경우 다음 명령으로 공급자를 연결하고 모델을 확인합니다.

```sh
opencode auth login
opencode models
```

수동 실행한 소스 서버에서는 CLI에도 서버 비밀번호가 필요합니다. 저장소 루트의 별도 터미널에서 다음을 실행하고, 비밀번호 입력 시 서버 터미널의 `server password` 뒤 값을 붙여 넣습니다. 입력한 값은 화면에 표시하지 않습니다.

macOS / Linux (Bash 또는 Zsh):

```sh
cd opencode
printf 'OpenCode server password: '
read -r -s OPENCODE_PASSWORD
printf '\n'
export OPENCODE_PASSWORD
bun run dev auth login --server http://127.0.0.1:4096
bun run dev models --server http://127.0.0.1:4096
```

Windows (PowerShell):

```powershell
cd opencode
$serverPassword = Read-Host 'OpenCode server password' -AsSecureString
$env:OPENCODE_PASSWORD = [System.Net.NetworkCredential]::new('', $serverPassword).Password
bun run dev auth login --server http://127.0.0.1:4096
bun run dev models --server http://127.0.0.1:4096
```

이 환경 변수는 서버 접속 비밀번호이며 모델 공급자의 API 키와는 별개입니다. 수동 서버에 연결하는 CLI 작업을 마치면 Bash/Zsh에서는 `unset OPENCODE_PASSWORD`, PowerShell에서는 `Remove-Item Env:OPENCODE_PASSWORD`로 지웁니다. 확장의 비밀번호 입력창에 넣은 값은 다른 터미널에 자동 전달되지 않습니다.

확장은 새 세션을 만들 때 서버의 기본 모델·에이전트를 사용합니다. 특정 모델을 기본으로 사용하려면 **작업 프로젝트 루트**의 `opencode.json` 또는 `opencode.jsonc`에 아래 설정을 추가합니다. `provider/model`은 모델 목록에서 확인한 실제 값으로 바꾸고, 기존 설정이 있다면 `model` 항목만 추가·수정하세요.

```json
{
  "model": "provider/model"
}
```

설정을 반영하려면 자동 연결 서비스에서는 `opencode service restart`, 수동 소스 서버에서는 서버 터미널을 종료한 뒤 같은 실행 명령으로 다시 시작합니다. 그다음 개발 창의 `Developer: Reload Window`로 기본 모델을 사용하는 새 세션을 엽니다. API 키를 프로젝트 코드나 Git에 기록하지 말고 CLI의 인증 안내를 사용하세요.

무료 모델도 사용 한도가 있을 수 있습니다. `Free usage limit reached`는 모델 공급자의 한도 오류이며, 서버 주소를 바꾸는 대신 사용 가능한 공급자를 연결한 뒤 다시 요청해야 합니다.

## 서버 연결

- 기본은 자동 연결입니다. 사이드바를 열면 `opencode service start`를 호출해 기존 백그라운드 서버를 재사용하고, 없으면 실행합니다. 준비가 끝난 서버 주소와 인증 정보를 CLI에서 받아 연결합니다.
- 연결 상태는 서버 아이콘과 상태 문구 한 줄로 표시합니다. 주소·버전·자세한 오류는 상태 위에 마우스를 올려 확인하고, 재연결·서버 설정·인증은 오른쪽 아이콘을 사용합니다. 아이콘에는 접근성 레이블을 제공합니다.
- `opencode.serverUrl`을 비워 두면 자동 연결합니다. **서버 주소 설정** 아이콘에서 주소를 지우면 자동 연결로 돌아갑니다.
- 서버 주소를 직접 지정하면 해당 서버에만 연결합니다. 연결이 실패해도 다른 서버를 자동 실행하지 않습니다.
- CLI가 없거나 시작에 실패하면 오류와 다음 조치를 표시합니다. CLI를 자동 설치하지는 않습니다.
- 서버의 중복 실행 방지와 백그라운드 수명 관리는 OpenCode CLI의 기존 서비스 기능이 담당합니다. 확장 창을 닫아도 공유 서버를 종료하지 않습니다.
- 확장 프로세스가 `GET /api/info`를 요청하고 서버 정보 형식을 검증합니다. Webview는 서버에 직접 요청하지 않습니다.
- 서버 준비 중, 연결 중, 연결됨, 인증 필요, 연결 오류를 표시합니다. **다시 연결** 아이콘으로 상태를 갱신할 수 있습니다. SSE 연결이 끊기면 오류를 표시하고 1초 후 다시 구독합니다. 같은 서버·workspace에서는 같은 세션의 기록과 대기 중인 승인·질문을 다시 읽습니다.
- 인증이 필요한 서버에서는 **비밀번호 입력** 아이콘을 눌러 서버의 `OPENCODE_PASSWORD`를 입력합니다. Basic 인증의 사용자 이름은 `opencode`입니다.
- 입력한 비밀번호는 확장 메모리에만 유지하고 VS Code 창 종료 또는 서버 주소 변경 시 지웁니다. 설정 파일·로그·Webview에는 전달하거나 저장하지 않습니다.
- 자동 연결은 CLI가 관리하는 서비스 비밀번호를 사용합니다. 수동 주소에 연결할 때는 VS Code 실행 환경의 `OPENCODE_PASSWORD` 또는 직접 입력한 비밀번호를 사용합니다. `.env` 파일은 자동으로 읽지 않습니다.
- HTTP 연결 확인은 최대 5초, CLI의 서버 준비는 최대 130초 동안 기다립니다. 주소 변경·화면 종료·재연결 시 확장의 이전 CLI 호출과 연결 확인을 취소합니다.
- 채팅 입력 초안은 Webview 상태에 유지합니다. 입력창 위의 보이는 라벨과 중지 버튼은 없으며, 전송은 아이콘으로 표시합니다.

대화는 서버에서 설정한 기본 모델·에이전트를 사용합니다. 모델 인증과 서버 접속 비밀번호는 별개이며, 서버 비밀번호를 입력해도 모델 공급자에 로그인되지는 않습니다.

## 채팅 사용

- **Enter** 또는 전송 아이콘: 메시지 전송. **Shift+Enter**: 줄바꿈.
- 채팅에 포커스가 있고 작업이 실행 중일 때 **Esc**: 서버의 `session.interrupt`를 호출해 생성·도구 실행을 취소합니다. 대기 중 Esc는 초안을 지우지 않습니다. IME 조합 중 Enter/Esc는 처리하지 않습니다.
- HTTP 접수 완료 후에도 응답 대기를 유지하고, SSE의 실행 완료·오류·취소로 작업 상태를 갱신합니다. 다른 세션의 이벤트는 화면에 표시하지 않습니다.
- 도구 권한 요청과 추가 질문이 오면 하단 메시지 입력창 대신 응답 패널을 표시합니다. 권한 요청이 뜨면 첫 선택 항목에 자동 포커스합니다. **↑/↓ 또는 ←/→**로 **이번만 허용 / 거절**을 선택한 뒤 **Tab → Enter**로 **응답 보내기**를 실행합니다. 포커스만으로 선택하거나 승인하지 않으며, 스트리밍 갱신은 사용자가 옮긴 포커스를 바꾸지 않습니다. 추가 질문에는 **응답 보내기 / 건너뛰기**로 답합니다. 요청이 처리되면 작성 중이던 초안과 입력창 포커스를 복원합니다. 허용은 요청별이며 자동 승인하거나 영구 허용하지 않습니다. 외부 인증용 form은 안내된 OpenCode CLI에서 진행합니다.
- 전송 실패나 시간 초과 시 초안을 보존하고 자동 재전송하지 않습니다. 서버에 접수됐을 수 있으므로 복구된 기록을 확인한 뒤 다시 보내세요.
- Webview는 서버나 모델에 직접 연결하지 않습니다. 확장 호스트의 공식 `@opencode/client` 2.4.0이 인증된 HTTP/SSE를 처리합니다. 구독을 먼저 연 뒤 전송하고, 서버 기록과 메시지 ID를 기준으로 화면을 복구합니다.

## 기존 터미널 기능

CLI를 별도로 설치한 경우 아래 명령도 계속 사용할 수 있습니다.

- `Open opencode`: 터미널에서 `opencode` 실행 또는 기존 터미널에 포커스
- `Open opencode in new tab`: 새 터미널에서 실행 (`Cmd+Shift+Esc` / `Ctrl+Shift+Esc`)
- `Cmd+Option+K` / `Ctrl+Alt+K`: 활성 OpenCode 터미널에 현재 파일·선택 범위의 참조 삽입

## 검증

```sh
bun run compile
bun run test:unit
bun run test:chat  # 실제 OpenCode CLI 필요, 모델 응답은 로컬 fixture
bun run package
```

단위 테스트는 실제 로컬 HTTP 서버와 CLI 응답 fixture로 경로, 인증, HTTP 오류, 응답 검증, 리다이렉트 거부, 자동 연결의 CLI 명령, CLI 미설치·실패·취소와 시간 초과를 확인합니다. 테스트 환경에서 loopback 포트 바인딩이 허용되어야 합니다.

실제 OpenCode CLI가 PATH에 있으면 `bun run test:server`로 서버 기동·인증·PID 재사용·동시 연결·종료를 통합 검증할 수 있습니다. 이 스크립트는 임시 XDG 디렉터리와 loopback 포트를 사용하므로 기존 사용자 서비스와 분리됩니다. 검증 코드·결과는 `extension/test/`에 모았으며, 자세한 기록은 [test/README.md](test/README.md)에 있습니다. 스크린샷은 `extension/test/screenshots/`에 로컬로만 보관하고 Git 추적에서 제외합니다.

VS Code 개발 창에서는 서버 실행 전후의 **다시 연결**, 잘못된 주소, 비밀번호가 필요한 서버, 서버 주소 변경, 사이드바를 숨겼다가 다시 열기, 좁은 너비와 밝은/어두운 테마를 확인합니다. 입력창과 연결 버튼은 키보드로 이동할 수 있어야 합니다.
