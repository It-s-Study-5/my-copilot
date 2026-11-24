# my-copilot
It's study 5기 '나만의 코파일럿 만들기'

## VS Code 채팅 확장 실행

`extension/`은 OpenCode 서버와 대화하는 VS Code 확장이고, `opencode/`는 서버와 CLI 소스다. 확장의 **오른쪽 보조 사이드바**에서 채팅과 권한·질문 응답을 처리한다.

### 준비 사항

- VS Code **1.106 이상**
- [Bun](https://bun.sh) **1.4.4 이상**: 의존성 설치와 소스 CLI 실행에 사용
- Node.js **22 이상**: 확장 빌드에 사용
- 터미널에서 실행할 수 있는 `code` 명령
- 자동 연결을 사용하려면 `opencode service start`를 지원하는 **OpenCode CLI 2.4.0**이 VS Code 프로세스의 PATH에 있어야 한다. CLI가 없으면 아래의 **소스 서버에 직접 연결** 방식으로 실행한다.

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

새로 열린 **Extension Development Host** 창에서 명령 팔레트의 `Open opencode Chat` 또는 `Cmd+Esc`(Windows/Linux: `Ctrl+Esc`)로 채팅을 연다. 오른쪽 OpenCode 탭을 사용해도 된다.

- 서버 주소 설정이 비어 있으면 로컬 서버를 자동 실행하거나 기존 서비스를 재사용한다. 별도 서버 터미널은 필요 없다.
- 다른 프로젝트의 코드를 작성하려면 실행 명령의 마지막 `..`를 **그 프로젝트 폴더 경로**로 바꾼다. 확장은 열린 workspace의 첫 번째 폴더에서 세션을 만든다.
- CLI를 설치했는데도 찾지 못하면 PATH가 반영되도록 VS Code를 완전히 종료한 뒤 다시 연다.

### CLI가 없는 경우: 소스 서버에 직접 연결

터미널 1에서 저장소의 OpenCode 소스를 준비하고 서버를 실행한다.

```sh
cd opencode
bun install --frozen-lockfile
bun run dev serve --port 4096
```

터미널 2에서 위의 확장 빌드·실행 명령을 실행한다. 개발 창의 OpenCode 탭에서 **서버 주소 설정** 아이콘을 눌러 `http://127.0.0.1:4096`을 저장한다. 이 방식에서는 터미널 1의 서버를 실행한 상태로 유지한다.

설정을 파일로 지정하려면 작업 폴더의 `.vscode/settings.json`에 다음 값을 넣는다.

```json
{
  "opencode.serverUrl": "http://127.0.0.1:4096"
}
```

자동 연결로 돌아가려면 서버 주소를 지우거나 값을 빈 문자열로 바꾼다. 비밀번호가 있는 서버에서는 개발 창의 **비밀번호 입력** 아이콘을 사용한다.

### 모델 연결과 코드 작성

**연결됨**은 OpenCode 서버 연결이 준비됐다는 뜻이다. 실제 답변·코드 생성에는 사용할 수 있는 모델이 필요하다. CLI의 `opencode auth login`으로 공급자를 연결하고 `opencode models`로 사용 가능한 모델을 확인한다. 소스 서버를 사용한다면 다음 명령으로 같은 서버에 연결한다.

```sh
cd opencode
bun run dev auth login --server http://127.0.0.1:4096
bun run dev models --server http://127.0.0.1:4096
```

기본 모델 설정은 [확장 실행 안내의 모델 연결](extension/README.md#모델-연결)을 참고한다. 무료 모델도 사용 한도가 있을 수 있으며, `Free usage limit reached`가 나오면 사용 가능한 공급자를 연결해야 한다.

- Enter: 전송 / Shift+Enter: 줄바꿈 / 실행 중 Esc: 취소
- 권한 요청은 하단 입력창 대신 표시된다. 자동 포커스된 항목에서 방향키로 선택하고 Tab → Enter로 확정한다.
- 모델이 만드는 파일은 위에서 연 작업 폴더에 생성된다. 파일 쓰기·명령 실행 권한 요청이 오면 내용을 확인하고 응답한다.

여러 채팅 탭과 VS Code 재시작 후 세션 복원은 아직 구현하지 않았다. 자세한 연결·사용·검증 방법은 [extension/README.md](extension/README.md)에 정리했다.

## 선택: 터미널 화면으로 서버에 연결

소스 서버가 실행 중일 때 별도 터미널에서 실행한다. VS Code 확장을 사용하는 데 필요한 단계는 아니다.

```sh
cd opencode
bun run dev --server http://127.0.0.1:4096
```

`--hostname 0.0.0.0`이나 `--remote`는 서버를 외부에 노출하므로 로컬에서만 쓸 때는 붙이지 않는다.
