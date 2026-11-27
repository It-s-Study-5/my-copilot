# OpenCode VS Code Extension

OpenCode 서버의 단일 세션과 대화하는 VS Code 확장입니다. 현재 workspace의 첫 번째 폴더에 세션을 만들고 메시지 전송·SSE 스트리밍·취소·승인·질문 응답을 처리합니다. 여러 채팅 탭과 VS Code 재시작 후 세션 복원은 #6의 범위입니다.

기본 위치는 **오른쪽 보조 사이드바**입니다. VS Code의 정식 `secondarySidebar` 기여 지점을 사용하므로 **VS Code 1.106 이상**이 필요합니다. [공식 지원 안내](https://code.visualstudio.com/updates/v1_106#_view-containers-in-secondary-side-bar)

## 개발 실행

VS Code 1.106 이상, Bun 1.4.4 이상, Node.js 22 이상과 PATH의 `code` 명령을 준비합니다. 배포용 CLI 없이 이 저장소의 코드로 테스트하려면 [소스 서버에 직접 연결](#소스-서버에-직접-연결)합니다.

저장소 루트에서 다음 명령을 실행합니다.

```sh
cd extension
bun install --frozen-lockfile
bun run compile
code --new-window --extensionDevelopmentPath="$PWD" ..
```

PowerShell에서는 마지막 명령을 `code --new-window --extensionDevelopmentPath="$($PWD.Path)" ..`로 실행합니다. 새로 열린 **Extension Development Host** 창에서 오른쪽 보조 사이드바의 OpenCode 탭, 명령 팔레트의 `Open opencode Chat`, 또는 `Cmd+Esc`(Windows/Linux: `Ctrl+Esc`)로 채팅을 엽니다.

위 명령의 `..`는 **코드를 읽고 쓸 작업 폴더**입니다. 다른 프로젝트를 작업하려면 그 폴더 경로로 바꾸세요. 확장은 workspace의 첫 번째 폴더를 사용하므로 작업할 프로젝트가 열린 개발 창에서 채팅을 시작해야 합니다.

서버 주소가 비어 있으면 사이드바를 열 때 로컬 서버를 자동 실행하거나 재사용합니다. 자동 연결용 CLI는 `opencode.cliPath` 또는 [CLI 배포](#cli-배포)에 설명된 릴리스에서 가져옵니다. 소스 변경을 반영하려면 `bun run compile`로 다시 빌드하고 기존 개발 창에서 `Developer: Reload Window`를 실행합니다. 이때 새 채팅 세션이 열립니다.

### 소스 서버에 직접 연결

CLI를 전역 설치하지 않고 저장소의 서버를 사용할 때는 별도 터미널에서 다음을 실행합니다.

```sh
cd opencode
bun install --frozen-lockfile
bun run dev serve --port 4096
```

이 실행 명령은 기본적으로 서버 비밀번호를 생성해 `server password ...`로 출력합니다. 그 뒤의 값을 복사해 둡니다. 서버 실행 시 `OPENCODE_PASSWORD`를 따로 지정했다면 그 값을 사용합니다.

다른 터미널에서 위의 확장 빌드·실행 명령을 실행한 뒤 개발 창에서 연결합니다.

1. **서버 주소 설정** 아이콘에 `http://127.0.0.1:4096`을 저장합니다. 또는 작업 폴더의 `.vscode/settings.json`에 `"opencode.serverUrl": "http://127.0.0.1:4096"`을 지정합니다.
2. **인증 필요** 상태에서 **비밀번호 입력** 아이콘을 눌러 서버 터미널의 `server password` 값을 입력합니다. 입력 후 자동 재연결됩니다.
3. **연결됨**을 확인합니다. `HTTP 401`은 비밀번호가 없거나 맞지 않다는 뜻입니다.

수동 연결 중에는 서버 터미널을 유지해야 합니다. 서버 재시작 후 비밀번호가 바뀌면 새 값을 입력하세요. 주소를 지우면 자동 연결로 돌아갑니다.

## 채팅에서 Slop 검사

Conduit에서 코파일럿에 `제목이 비어 있으면 게시글을 등록할 수 없게 해줘`라고 요청합니다. 수정 파일을 저장한 뒤 같은 채팅에서 `/slop 방금 고친 거, 스페이스만 넣어도 등록이 막혀?`라고 물어보세요. Slop은 저장된 글 등록 코드를 직접 호출해 그 입력에서 글 생성을 시도하는지 알려줍니다. 허점이 있으면 `그것도 막아줘`라고 보내세요. 직전 질문과 확인 결과가 코파일럿에 함께 전달됩니다.

검사는 Git이 추적하는 파일에서 실행되며 stage 전에도 사용할 수 있습니다. 질문을 생략하면 이번 변경을 전반적으로 확인합니다. Esc로 실행 중인 검사를 취소할 수 있습니다.

확장 빌드는 저장소의 `ai-slop/` 런타임을 설치 파일에 포함합니다. 실행하는 곳에는 Python 3, Git, Node.js가 필요합니다. 확장의 `/slop`은 OpenAI API 키를 사용합니다. 로컬 채팅에서 **OpenAI API 키 연결**로 등록하면 현재 작업 폴더의 키가 VS Code 보안 저장소에 보관됩니다. Slop은 해당 키를 우선 사용하고, 저장된 키가 없으면 확장 호스트의 `OPENAI_API_KEY`를 사용합니다. 기존에 OpenCode 서버에만 키가 저장돼 있고 확장 호스트에도 `OPENAI_API_KEY`가 없으면 첫 `/slop`에서 비밀번호 입력창이 열립니다. Slop에 저장한 키를 교체하려면 명령 팔레트에서 **OpenCode: 이 폴더의 Slop API 키 설정**을 실행합니다. 신뢰하는 작업공간에서 같은 호스트의 OpenCode 서버에 연결한 뒤 실행하세요.

## CLI 배포

설치된 확장은 서버 주소가 비어 있으면 확장 버전과 같은 `cli-v<버전>` GitHub Release에서 OpenCode CLI를 처음 한 번 내려받아 `globalStorage`에 저장하고 체크섬을 검증합니다. 직접 빌드한 CLI를 쓰려면 `opencode.cliPath`에 실행 파일 경로를 지정합니다.

릴리스 자산은 저장소 루트 기준으로 다음과 같이 만듭니다. 업로드는 스크립트가 출력하는 `gh release create` 명령을 직접 실행합니다. 확장 버전을 올리면 같은 버전의 릴리스를 먼저 올려야 합니다.

```sh
cd extension
./script/release-cli
```

## 모델 연결

실제 답변·파일 생성에는 OpenCode 서버의 OpenAI 연결이 필요합니다. `auth login`에서 **OpenAI**를 선택하고 사용할 계정이나 API 키를 연결합니다. OpenAI는 한국에서 API를 지원하며, API 키를 사용할 때 모델 접근 권한과 사용량은 키가 속한 프로젝트를 따릅니다. 모델 인증 정보는 OpenCode 서버가 관리합니다. [OpenAI 지원 지역](https://help.openai.com/en/articles/7947663-chatgpt-and-openai-api-supported-countries-and-territories) · [OpenAI API 과금](https://help.openai.com/en/articles/9039756-managing-billing-for-chatgpt-and-the-api-platform)

자동 연결용 CLI를 사용할 때는 다음 명령으로 OpenAI를 연결하고 모델을 확인합니다.

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

새 채팅은 GPT Sol을 사용할 수 있을 때 `openai/gpt-6.2-sol`로 시작합니다. Sol을 사용할 수 없으면 채팅 상단에 서버 기본 모델과 **OpenAI API 키 연결**, **현재 모델로 계속**을 표시합니다. 모델을 선택하기 전에는 메시지 전송이 잠시 비활성화됩니다. 키는 VS Code의 비밀번호 입력창에서 받아 연결된 OpenCode 서버에 등록하며, Sol이 사용 가능해지면 현재 채팅을 Sol로 전환합니다. 서버 기본 모델은 다른 공급자의 모델일 수 있습니다. 모델 선택 목록은 서버 카탈로그에 활성화된 OpenAI GPT 텍스트·코드 모델로 제한합니다.

## 서버 연결

- 기본은 자동 연결입니다. 사이드바를 열면 `opencode service start`를 호출해 기존 백그라운드 서버를 재사용하고, 없으면 실행합니다. 준비가 끝난 서버 주소와 인증 정보를 CLI에서 받아 연결합니다.
- 연결 상태는 서버 아이콘과 상태 문구 한 줄로 표시합니다. 주소·버전·자세한 오류는 상태 위에 마우스를 올려 확인하고, 재연결·서버 설정·인증은 오른쪽 아이콘을 사용합니다. 아이콘에는 접근성 레이블을 제공합니다.
- `opencode.serverUrl`을 비워 두면 자동 연결합니다. **서버 주소 설정** 아이콘에서 주소를 지우면 자동 연결로 돌아갑니다.
- 서버 주소를 직접 지정하면 해당 서버에만 연결합니다. 연결이 실패해도 다른 서버를 자동 실행하지 않습니다.
- CLI 다운로드나 서버 시작에 실패하면 오류를 표시합니다. 릴리스가 없는 경우 소스 서버에 직접 연결할 수 있습니다.
- 서버의 중복 실행 방지와 백그라운드 수명 관리는 OpenCode CLI의 기존 서비스 기능이 담당합니다. 확장 창을 닫아도 공유 서버를 종료하지 않습니다.
- 확장 프로세스가 `GET /api/info`를 요청하고 서버 정보 형식을 검증합니다. Webview는 서버에 직접 요청하지 않습니다.
- 서버 준비 중, 연결 중, 연결됨, 인증 필요, 연결 오류를 표시합니다. **다시 연결** 아이콘으로 상태를 갱신할 수 있습니다. SSE 연결이 끊기면 오류를 표시하고 1초 후 다시 구독합니다. 같은 서버·workspace에서는 같은 세션의 기록과 대기 중인 승인·질문을 다시 읽습니다.
- 인증이 필요한 서버에서는 **비밀번호 입력** 아이콘을 눌러 서버의 `OPENCODE_PASSWORD`를 입력합니다. Basic 인증의 사용자 이름은 `opencode`입니다.
- 입력한 비밀번호는 확장 메모리에만 유지하고 VS Code 창 종료 또는 서버 주소 변경 시 지웁니다. 설정 파일·로그·Webview에는 전달하거나 저장하지 않습니다.
- 자동 연결은 CLI가 관리하는 서비스 비밀번호를 사용합니다. 수동 주소에 연결할 때는 VS Code 실행 환경의 `OPENCODE_PASSWORD` 또는 직접 입력한 비밀번호를 사용합니다. `.env` 파일은 자동으로 읽지 않습니다.
- HTTP 연결 확인은 최대 5초, CLI의 서버 준비는 최대 130초 동안 기다립니다. 주소 변경·화면 종료·재연결 시 확장의 이전 CLI 호출과 연결 확인을 취소합니다.
- 채팅 입력 초안은 Webview 상태에 유지합니다. 입력창 위의 보이는 라벨과 중지 버튼은 없으며, 전송은 아이콘으로 표시합니다.

## 채팅 사용

- 연결 상태 아래에 활성 에이전트와 모델이 표시됩니다. 각 답변 위에는 해당 답변을 생성한 에이전트가 표시됩니다.
- 모델 이름을 누르면 현재 채팅의 모델을 바꿀 수 있습니다. 모델을 고르는 동안 메시지 전송이 잠시 비활성화되며, 작성 중인 초안은 유지됩니다.
- 채팅 기록에는 질문, 답변, 응답·도구 오류가 표시됩니다. `skill`, `execute` 같은 정상적인 중간 실행 기록과 빈 응답 줄은 숨깁니다.
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

### 실제 OpenAI 모델로 수동 테스트

1. 첫 번째 터미널에서 [소스 서버 실행 명령](#소스-서버에-직접-연결)을 실행합니다. 두 번째 터미널에서 [모델 연결](#모델-연결) 절차로 OpenAI를 연결하고 `bun run dev models --server http://127.0.0.1:4096` 출력에서 `openai/gpt-6.2-sol`을 확인합니다.
2. [개발 실행](#개발-실행) 절차로 Extension Development Host를 엽니다. OpenCode 채팅에서 실행 중인 서버 주소와 비밀번호를 입력합니다. **연결됨** 아래에 서버의 활성 에이전트와 `openai/gpt-6.2-sol`이 보이는지 확인합니다.
3. `루트 README를 읽고 이 저장소의 목적을 한 문장으로 설명해 줘`를 보냅니다. 답변이 스트리밍되고 응답 에이전트 이름이 표시되는지 확인합니다. 도구가 실행돼도 `skill`, `execute` 같은 기록이나 빈 에이전트 줄은 채팅에 나타나지 않습니다. 서버가 권한을 요청하면 내용을 확인하고 응답합니다.
4. 모델 이름을 눌러 서버에서 활성화된 공개 OpenAI GPT 텍스트·코드 모델만 표시되는지 확인합니다. 다른 모델이 있다면 선택하고, 상단에 선택한 모델이 표시되는지 확인합니다.
5. 개발 창에서 `Developer: Reload Window`를 실행하고 OpenCode 채팅을 다시 엽니다. 새 세션의 모델이 `openai/gpt-6.2-sol`인지 확인합니다. 수동 서버 비밀번호를 입력창에서 설정했다면 다시 입력합니다.

### OpenAI 키 없이 모델 선택 화면 확인

`extension/`에서 `bun run test/chat-server.ts --fallback`을 실행합니다. 개발 창의 OpenCode 사이드바에서 서버 주소를 `http://127.0.0.1:41963`으로 설정합니다.

1. `qa/chat`과 두 선택지가 보이고, 선택하기 전에는 메시지 전송이 비활성화되는지 확인합니다.
2. **현재 모델로 계속**을 눌러 작성 중인 초안이 유지되고 `qa/chat`에서 테스트 응답이 스트리밍되는지 확인합니다.
3. **OpenAI API 키 연결**을 눌러 비밀번호 입력창에 테스트 값 `fixture-only`를 넣습니다. 현재 채팅이 `openai/gpt-6.2-sol`로 전환되는지 확인합니다.

이 테스트 서버는 `fixture-only`를 받아 모델 연결을 흉내 냅니다. 실제 OpenAI 키는 일반 OpenCode 서버에 연결할 때 사용하세요. 처음부터 다시 확인하려면 테스트 서버를 `Ctrl+C`로 종료하고 같은 명령으로 다시 실행한 뒤 개발 창을 새로고침합니다.

### API 키 없이 자동 테스트

저장소 루트에서 실행합니다. 테스트 프로세스가 로컬 loopback 포트에 바인딩할 수 있어야 합니다.

```sh
cd extension
bun install --frozen-lockfile
bun run compile
bun run test:unit
```

단위 테스트는 모델 선택 필터, GPT Sol 기본값, 대체 모델 선택과 키 연결, 재연결 시 모델 유지, 채팅 표시, 키보드 입력, 서버 연결과 인증을 검증합니다.

실제 OpenCode 서버와 채팅 실행기를 검증하려면 **저장소 루트**에서 소스 의존성을 준비한 뒤 통합 테스트를 실행합니다.

```sh
cd opencode
bun install --frozen-lockfile
cd ../extension
bun run test:chat bun run --cwd ../opencode/packages/cli src/index.ts
```

OpenCode CLI 2.4.0이 PATH에 있으면 `extension/`에서 `bun run test:chat`으로 실행할 수 있습니다. 통합 테스트는 임시 서버와 로컬 모델 응답 fixture로 스트리밍, 취소, 승인·거절, 추가 질문과 오류를 검증합니다. OpenAI API 요청은 발생하지 않습니다.

실제 OpenCode CLI가 PATH에 있으면 `bun run test:server`로 서버 기동·인증·PID 재사용·동시 연결·종료를 통합 검증할 수 있습니다. 이 스크립트는 임시 XDG 디렉터리와 loopback 포트를 사용하므로 기존 사용자 서비스와 분리됩니다. 검증 코드·결과는 `extension/test/`에 모았으며, 자세한 기록은 [test/README.md](test/README.md)에 있습니다. 스크린샷은 `extension/test/screenshots/`에 로컬로만 보관하고 Git 추적에서 제외합니다.

VS Code 개발 창에서는 서버 실행 전후의 **다시 연결**, 잘못된 주소, 비밀번호가 필요한 서버, 서버 주소 변경, 사이드바를 숨겼다가 다시 열기, 좁은 너비와 밝은/어두운 테마를 확인합니다. 입력창과 연결 버튼은 키보드로 이동할 수 있어야 합니다.
