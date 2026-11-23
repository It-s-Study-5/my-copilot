# OpenCode VS Code Extension

OpenCode 서버에 연결하는 사이드바 채팅 화면입니다. 현재는 서버 연결 확인과 화면 기본 구조를 제공합니다. 실제 메시지 전송·스트리밍은 #4, 여러 채팅 탭과 세션 복원은 #6에서 구현합니다.

## 개발 실행

`opencode service start`를 지원하는 OpenCode CLI를 PATH에 설치합니다. 이 저장소의 CLI 규격은 2.4.0입니다. 확장을 빌드하고 개발용 VS Code 창을 엽니다. Bun과 `code` 명령도 필요합니다.

```sh
cd extension
bun install
bun run compile
code --new-window --extensionDevelopmentPath="$PWD"
```

Activity Bar의 OpenCode 아이콘, 명령 팔레트의 `Open opencode Chat`, 또는 `Cmd+Esc`(Windows/Linux: `Ctrl+Esc`)로 사이드바를 엽니다.

## 서버 연결

- 기본은 자동 연결입니다. 사이드바를 열면 `opencode service start`를 호출해 기존 백그라운드 서버를 재사용하고, 없으면 실행합니다. 준비가 끝난 서버 주소와 인증 정보를 CLI에서 받아 연결합니다.
- 연결 상태는 서버 아이콘과 상태 문구 한 줄로 표시합니다. 주소·버전·자세한 오류는 상태 위에 마우스를 올려 확인하고, 재연결·서버 설정·인증은 오른쪽 아이콘을 사용합니다. 아이콘에는 접근성 레이블을 제공합니다.
- `opencode.serverUrl`을 비워 두면 자동 연결합니다. **서버 주소 설정** 아이콘에서 주소를 지우면 자동 연결로 돌아갑니다.
- 서버 주소를 직접 지정하면 해당 서버에만 연결합니다. 연결이 실패해도 다른 서버를 자동 실행하지 않습니다.
- CLI가 없거나 시작에 실패하면 오류와 다음 조치를 표시합니다. CLI를 자동 설치하지는 않습니다.
- 서버의 중복 실행 방지와 백그라운드 수명 관리는 OpenCode CLI의 기존 서비스 기능이 담당합니다. 확장 창을 닫아도 공유 서버를 종료하지 않습니다.
- 확장 프로세스가 `GET /api/info`를 요청하고 서버 정보 형식을 검증합니다. Webview는 서버에 직접 요청하지 않습니다.
- 서버 준비 중, 연결 중, 연결됨, 인증 필요, 연결 오류를 표시합니다. **다시 연결** 아이콘으로 상태를 갱신할 수 있습니다. 주기적인 상태 감시는 하지 않습니다.
- 인증이 필요한 서버에서는 **비밀번호 입력** 아이콘을 눌러 서버의 `OPENCODE_PASSWORD`를 입력합니다. Basic 인증의 사용자 이름은 `opencode`입니다.
- 입력한 비밀번호는 확장 메모리에만 유지하고 VS Code 창 종료 또는 서버 주소 변경 시 지웁니다. 설정 파일·로그·Webview에는 전달하거나 저장하지 않습니다.
- 자동 연결은 CLI가 관리하는 서비스 비밀번호를 사용합니다. 수동 주소에 연결할 때는 VS Code 실행 환경의 `OPENCODE_PASSWORD` 또는 직접 입력한 비밀번호를 사용합니다. `.env` 파일은 자동으로 읽지 않습니다.
- HTTP 연결 확인은 최대 5초, CLI의 서버 준비는 최대 130초 동안 기다립니다. 주소 변경·화면 종료·재연결 시 확장의 이전 CLI 호출과 연결 확인을 취소합니다.
- 채팅 입력 초안은 Webview 상태에 유지합니다. 입력창의 보이는 라벨과 중지 버튼은 제거하고, 전송은 아이콘으로 표시합니다. 현재 전송 아이콘은 비활성 상태입니다.

저장소의 소스 서버를 수동 실행하는 방식도 계속 지원합니다. 루트 README처럼 `opencode/`에서 `bun run dev serve --port 4096`을 실행한 뒤 확장의 서버 주소를 `http://localhost:4096`으로 지정하세요. 실제 모델 호출은 #4의 범위입니다.

## 기존 터미널 기능

CLI를 별도로 설치한 경우 아래 명령도 계속 사용할 수 있습니다.

- `Open opencode`: 터미널에서 `opencode` 실행 또는 기존 터미널에 포커스
- `Open opencode in new tab`: 새 터미널에서 실행 (`Cmd+Shift+Esc` / `Ctrl+Shift+Esc`)
- `Cmd+Option+K` / `Ctrl+Alt+K`: 활성 OpenCode 터미널에 현재 파일·선택 범위의 참조 삽입

## 검증

```sh
bun run compile
bun run test:unit
bun run package
```

단위 테스트는 실제 로컬 HTTP 서버와 CLI 응답 fixture로 경로, 인증, HTTP 오류, 응답 검증, 리다이렉트 거부, 자동 연결의 CLI 명령, CLI 미설치·실패·취소와 시간 초과를 확인합니다. 테스트 환경에서 loopback 포트 바인딩이 허용되어야 합니다.

실제 OpenCode CLI가 PATH에 있으면 `bun run test:server`로 서버 기동·인증·PID 재사용·동시 연결·종료를 통합 검증할 수 있습니다. 이 스크립트는 임시 XDG 디렉터리와 loopback 포트를 사용하므로 기존 사용자 서비스와 분리됩니다. 검증 코드·결과는 `extension/test/`에 모았으며, 자세한 기록은 [test/README.md](test/README.md)에 있습니다. 스크린샷은 `extension/test/screenshots/`에 로컬로만 보관하고 Git 추적에서 제외합니다.

VS Code 개발 창에서는 서버 실행 전후의 **다시 연결**, 잘못된 주소, 비밀번호가 필요한 서버, 서버 주소 변경, 사이드바를 숨겼다가 다시 열기, 좁은 너비와 밝은/어두운 테마를 확인합니다. 입력창과 연결 버튼은 키보드로 이동할 수 있어야 합니다.
