# my-copilot

It's study 5기 '나만의 코파일럿 만들기'

## VS Code 채팅 확장 실행

`extension/`은 OpenCode 서버와 대화하는 VS Code 확장이고, `opencode/`는 서버와 CLI 소스다. 확장의 **오른쪽 보조 사이드바**에서 채팅과 권한·질문 응답을 처리한다.

### 준비 사항

- VS Code **1.106 이상**
- [Bun](https://bun.sh) **1.4.4 이상**: 의존성 설치와 소스 CLI 실행에 사용
- Node.js **22 이상**: 확장 빌드에 사용
- 터미널에서 실행할 수 있는 `code` 명령
- 자동 연결은 `opencode.cliPath`에 지정된 CLI 또는 확장 버전에 맞는 GitHub 릴리스의 CLI를 사용한다. 배포용 CLI 없이 테스트하려면 아래의 **소스 서버에 직접 연결** 방식으로 실행한다.

Bun이 없다면 다음과 같이 설치한다.

macOS:

```bash
brew install oven-sh/bun/bun
```

Windows (PowerShell, Windows 10 1809 이상):

```powershell
powershell -c "irm bun.sh/install.ps1|iex"
```

설치 후 `bun --version`이 안 되면 `%USERPROFILE%\.bun\bin`을 사용자 PATH에 추가하고 터미널을 다시 연다.

### 기본 실행: 서버 자동 연결

저장소 루트에서 실행한다. 다음 명령은 이 저장소를 작업 폴더로 연다.

macOS / Linux:

```sh
cd extension
bun install --frozen-lockfile
bun run compile
code --new-window --extensionDevelopmentPath="$PWD" ..
```

Windows (PowerShell):

```powershell
cd extension
bun install --frozen-lockfile
bun run compile
code --new-window --extensionDevelopmentPath="$($PWD.Path)" ..
```

새로 열린 **Extension Development Host** 창에서 명령 팔레트의 `Open Pico Chat` 또는 `Cmd+Esc`(Windows/Linux: `Ctrl+Esc`)로 채팅을 연다. 오른쪽 Pico 탭을 사용해도 된다.

- 서버 주소 설정이 비어 있으면 로컬 서버를 자동 실행하거나 기존 서비스를 재사용한다. 별도 서버 터미널은 필요 없다.
- 다른 프로젝트의 코드를 작성하려면 실행 명령의 마지막 `..`를 **그 프로젝트 폴더 경로**로 바꾼다. 확장은 열린 workspace의 첫 번째 폴더에서 세션을 만든다.

### CLI가 없는 경우: 소스 서버에 직접 연결

터미널 1에서 저장소의 OpenCode 소스를 준비하고 서버를 실행한다.

```sh
cd opencode
bun install --frozen-lockfile
bun run dev serve --port 4096
```

이 명령은 기본적으로 서버 접속 비밀번호를 생성하고 터미널에 다음 두 줄을 출력한다. **`server password` 뒤의 값을 복사해 둔다.** 별도로 `OPENCODE_PASSWORD`를 지정했다면 그 값을 사용한다.

```text
server listening on http://127.0.0.1:4096
server password <이번 실행에서 생성된 값>
```

터미널 2에서 위의 확장 빌드·실행 명령을 실행한 뒤, 개발 창에서 다음 순서로 연결한다.

1. Pico 탭의 **서버 주소 설정** 아이콘에 `http://127.0.0.1:4096`을 저장한다. 수동 연결에는 주소 지정이 필요하다.
2. **인증 필요**가 표시되면 **비밀번호 입력** 아이콘에 서버 터미널의 `server password` 값을 입력한다. 입력 후 자동으로 다시 연결한다.
3. **연결됨** 상태를 확인한다. 서버를 재시작해 비밀번호가 바뀌면 새 값을 다시 입력한다.

이 방식에서는 터미널 1의 서버를 실행한 상태로 유지한다.

설정을 파일로 지정하려면 작업 폴더의 `.vscode/settings.json`에 다음 값을 넣는다.

```json
{
  "opencode.serverUrl": "http://127.0.0.1:4096"
}
```

자동 연결로 돌아가려면 서버 주소를 지우거나 값을 빈 문자열로 바꾼다. `HTTP 401` 또는 **인증 필요**는 서버가 비밀번호를 요구한다는 뜻이므로 주소와 서버 비밀번호를 모두 확인한다.

### 모델 연결과 코드 작성

**연결됨**은 OpenCode 서버 연결이 준비됐다는 뜻이다. 실제 답변·코드 생성에는 사용할 수 있는 모델이 필요하다. CLI의 `opencode auth login`으로 공급자를 연결하고 `opencode models`로 사용 가능한 모델을 확인한다. 수동 소스 서버에서는 CLI에도 서버 비밀번호를 전달해야 한다. [모델 연결 안내](extension/README.md#모델-연결)의 `OPENCODE_PASSWORD` 입력과 `--server` 명령을 사용한다.

새 채팅은 **GPT-6.2 Sol**을 우선 사용한다. Sol을 사용할 수 없으면 채팅 상단에서 OpenAI API 키를 연결하거나 표시된 서버 기본 모델로 계속할 수 있다. 모델 이름을 눌러 서버에서 활성화된 OpenAI GPT 모델을 선택할 수 있다. 실제 OpenAI 모델로 수동 테스트하거나 API 키 없이 자동 테스트하려면 [확장 테스트 절차](extension/README.md#검증)를 참고한다.

- Enter: 전송 / Shift+Enter: 줄바꿈 / 실행 중 Esc: 취소
- 권한 요청은 하단 입력창 대신 표시된다. 자동 포커스된 항목에서 방향키로 선택하고 Tab → Enter로 확정한다.
- 모델이 만드는 파일은 위에서 연 작업 폴더에 생성된다. 파일 쓰기·명령 실행 권한 요청이 오면 내용을 확인하고 응답한다.

여러 채팅 탭과 VS Code 재시작 후 세션 복원은 아직 구현하지 않았다. 자세한 연결·사용·검증 방법은 [extension/README.md](extension/README.md)에 정리했다.

## 선택: 터미널 화면으로 서버에 연결

소스 서버가 실행 중일 때 별도 터미널에서 실행한다. 먼저 위 모델 연결 안내에 따라 이 터미널의 `OPENCODE_PASSWORD`에 서버 비밀번호를 설정한다. VS Code 확장을 사용하는 데 필요한 단계는 아니다.

```sh
cd opencode
bun run dev --server http://127.0.0.1:4096
```

`--hostname 0.0.0.0`이나 `--remote`는 서버를 외부에 노출하므로 로컬에서만 쓸 때는 붙이지 않는다.

## 함수 변경 영향도 분석 (code-impact)

수정하려는 함수 안에 커서를 두고 단축키를 누르면, 그 함수를 직접·간접 호출하는 함수들과 각 호출자가 인자·반환값을 어떻게 쓰는지 찾아 AI가 변경 영향을 설명한다. 결과는 채팅창에 **함수 영향도 분석** 메시지로 표시된다. 분석 엔진은 `code-impact/`(Python), 단축키와 화면은 `extension/`이 담당한다.

- 에디터에 포커스를 둔 상태에서 Mac은 **`Ctrl+Option+i`**(Shift 없이), Windows/Linux는 **`Ctrl+Alt+Shift+i`**를 누른다.
- 로컬 환경에 따라 단축키가 동작하지 않으면 **`Command+Shift+P`**(Windows/Linux는 **`Ctrl+Shift+P`**)로 명령 팔레트를 열고 **Code Impact: 이 함수의 변경 영향도 분석**을 직접 실행한다.

### 준비 사항

- 위의 **VS Code 채팅 확장 실행** 준비 사항
- Python **3.11 이상**
- 모델 공급자(OpenAI) API 키

저장소 루트에서 한 번만 실행한다.

macOS / Linux:

```sh
cd code-impact
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Windows (PowerShell):

```powershell
cd code-impact
py -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

영향도 분석은 채팅에서 선택한 OpenAI 모델과 OpenCode 서버에 저장된 OpenAI API 키를 그대로 쓴다. 모델이 OpenAI가 아니거나 서버에서 키를 찾지 못하면 채팅창에 오류를 표시한다. `.env`는 필요 없다.

### VS Code에서 테스트

저장소 루트에서 실행한다. 마지막 인자에는 분석할 JavaScript 또는 TypeScript 프로젝트의 폴더 경로를 넣는다.

```sh
cd extension
bun install --frozen-lockfile
bun run compile
code --new-window --extensionDevelopmentPath="$PWD" "/path/to/your/project"
```

PowerShell에서는 `--extensionDevelopmentPath="$($PWD.Path)"`를 사용한다.

1. 새로 열린 **Extension Development Host**에서 OpenCode 서버에 연결한다. 채팅 상단의 **OpenAI API 키 연결**로 키를 등록하고 OpenAI 모델을 선택한다.
2. 프로젝트에서 다른 함수가 호출하는 함수를 하나 고른다. 해당 파일을 열고 함수 본문을 클릭해 에디터에 포커스를 둔다.
3. 분석 단축키를 누른다. 로컬에서 단축키가 동작하지 않으면 명령 팔레트에서 **Code Impact: 이 함수의 변경 영향도 분석**을 실행한다.
4. Pico 채팅의 **함수 영향도 분석** 카드에서 대상 함수, AI 요약, 영향 후보를 확인한다. 후보의 파일 링크를 눌러 실제 호출 위치로 이동하는지도 확인한다.
5. 함수 밖에 커서를 두고 다시 실행했을 때 `커서가 함수 안에 있지 않습니다.`가 표시되는지 확인한다.

화면 코드(`extension/media/`)를 고친 뒤에는 개발 창에서 `Developer: Reload Webviews`, 확장 코드(`extension/src/`)를 고친 뒤에는 `bun run compile` 후 `Developer: Reload Window`를 실행한다.
