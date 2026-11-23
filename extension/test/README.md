# 사이드바 GUI 검증 기록

검증 환경: macOS arm64, VS Code 1.146.0의 Extension Development Host, Bun 1.4.5.

브랜치: `feature/extension-chat`, 기준: `origin/main` (`5609b80999`).

## 검증 범위

실제 VS Code에 로컬 확장을 로드하고 버튼·입력창을 조작해 확인했다. 01~07 화면의 서버 응답은 `server.mjs`의 로컬 HTTP fixture로 재현했다. 이 fixture는 저장소의 OpenCode 2.4.0 `GET /api/info` 응답 형식과 Basic 인증을 사용하지만, OpenCode 본체나 모델을 실행하지 않는다. 화면의 `2.4.0-test-fixture` 표기도 이 구분을 위한 것이다.

08~10 화면은 저장소의 실제 OpenCode CLI와 서버를 Bun으로 실행해 검증했다. 소스 실행의 버전 표시는 `local`이며 fixture가 아니다. 모델 호출은 하지 않았다.

스크린샷은 실제 개발 창에서 캡처한 원본 JPEG이며, 합성하거나 편집하지 않았다. `extension/test/screenshots/`에 로컬로만 보관하고 Git에는 올리지 않는다. 아래 파일명은 로컬 캡처를 찾기 위한 기록이다.

| 화면 | 확인 결과 | 로컬 스크린샷 |
| --- | --- | --- |
| 인증 필요 | HTTP 401 수신 후 인증 안내와 비밀번호 입력 버튼 표시 | `screenshots/01-authentication-required.jpg` |
| 연결 성공 | 테스트 비밀번호 입력 후 연결됨과 서버 버전 표시, 인증 버튼 숨김 | `screenshots/02-connected.jpg` |
| 서버 미실행 | 실행 중인 서버가 없는 `127.0.0.1:41961`로 변경하면 연결 오류 표시 | `screenshots/03-server-unreachable.jpg` |
| 잘못된 주소 | `not-a-url` 입력 후 Enter를 눌러도 저장하지 않고 검증 메시지 표시 | `screenshots/04-invalid-address.jpg` |
| 밝은 테마 | Light Modern에서 텍스트·오류 상태·버튼·입력창 표시 | `screenshots/05-light-theme.jpg` |
| 좁은 사이드바 | 약 240px 너비에서 문구 줄바꿈과 입력창·버튼 배치 유지 | `screenshots/06-narrow-sidebar.jpg` |
| 자동 연결·CLI 미설치 | 서버 주소를 비우면 자동 실행을 시도하고, CLI가 없는 환경에서 설치·수동 주소 안내 표시 | `screenshots/07-cli-not-installed.jpg` |
| 실제 서버 자동 기동 | 실행 중인 서버가 없는 상태에서 사이드바를 열면 실제 OpenCode 서버 기동 후 연결됨과 `vlocal` 표시 | `screenshots/08-real-server-auto-connected.jpg` |
| 한 줄 연결 표시 | 큰 패널을 서버 아이콘·상태·재연결/설정 아이콘 한 줄로 축소. 재연결과 설정 입력창 동작 및 주소·버전의 접근성 레이블 확인 | `screenshots/09-compact-connected.jpg` |
| 입력창 간소화 | 중지 버튼과 입력창 위의 보이는 메시지 라벨 제거, 전송은 종이비행기 아이콘으로 표시. 입력창·전송 아이콘의 접근성 이름 유지 확인 | `screenshots/10-icon-send-composer.jpg` |

추가로 Explorer로 이동했다가 복귀했을 때 입력 초안이 유지되는 것을 확인했다. Developer: Reload Window 후에도 초안은 복원되고, 메모리의 서버 비밀번호는 지워져 인증 필요 상태로 돌아오는 것을 확인했다. 현재 UI에서는 입력창 위의 보이는 라벨과 중지 버튼을 제거하고 전송만 아이콘으로 표시한다. 실제 전송은 아직 구현하지 않아 전송 아이콘은 비활성 상태이며, 입력창과 아이콘의 접근성 이름은 유지한다.

## 재현 방법

저장소 루트에서 테스트 서버를 실행한다. `41960` 포트가 비어 있어야 한다.

```sh
node extension/test/server.mjs
```

다른 터미널에서 확장을 빌드하고 개발 창을 연다. 평소 VS Code 설정을 보존하려면 별도의 테스트용 profile 및 workspace를 사용한다.

```sh
cd extension
bun run package
code --new-window --extensionDevelopmentPath="$PWD"
```

1. Activity Bar의 OpenCode 아이콘으로 사이드바를 연다.
2. **서버 주소**를 `http://127.0.0.1:41960`으로 변경한다. 인증 필요 상태를 확인한다.
3. **비밀번호 입력**에서 fixture 전용 값 `test-only`를 입력한다. 연결됨과 테스트 버전을 확인한다.
4. 입력 초안을 작성하고 Explorer 전환·복귀 및 Developer: Reload Window로 복원을 확인한다.
5. **서버 주소**에 `not-a-url`을 입력해 주소 검증을 확인한다.
6. 주소를 서버가 없는 `http://127.0.0.1:41961`로 변경해 연결 오류를 확인한다.
7. 테스트용 창에서 밝은 테마와 좁은 사이드바를 확인한다.
8. 테스트 서버는 Ctrl+C로 종료한다.

## 자동 검증 결과

- `cd extension && bun run test:unit`: **16개 통과, 실패 0개**. 실제 loopback HTTP로 경로·Basic 인증·HTTP 오류·응답 검증·리다이렉트 거부·취소·5초 시간 초과를 확인한다. CLI 응답 fixture를 별도 프로세스로 실행해 `service start`와 `service get password` 호출, 인증된 엔드포인트, CLI 미설치·실패·취소, 비로컬 주소 거부, wildcard 주소 변환과 빈 비밀번호를 확인한다.
- `cd extension && bun run package`: TypeScript 검사와 프로덕션 빌드 통과. ESLint 오류 0개, 기존 `extension.ts`의 세미콜론 경고 33개.
- `node --check extension/media/chat.js`: 통과.
- `git diff --check`: 통과.

## 실제 서버 기동 검증

OpenCode 소스 의존성을 `bun install --frozen-lockfile`로 설치한 뒤, 임시 `opencode` launcher로 `opencode/packages/cli/src/index.ts`를 Bun에서 실행했다. 시스템 CLI를 전역 설치하지 않았다. CLI의 설정·상태·데이터·캐시 경로는 임시 XDG 디렉터리로 분리하고, 테스트용 loopback 포트를 사용했다.

`extension/test/real-server.ts`는 fixture 없이 확장의 실제 `ensureLocalServer`와 `getServerInfo`를 호출한다. 다음 검증을 통과했고, 인증 정보가 없는 결과만 [server-startup-result.json](server-startup-result.json)에 저장했다.

- 정지 상태에서 실제 서비스 기동 후 인증된 `/api/info` 응답 수신
- 인증 정보 없이 요청하면 HTTP 401 반환
- 다시 연결해도 주소·인증 정보·PID 재사용
- 두 연결이 동시에 들어와도 같은 서버 PID 재사용
- 검증 완료 후 서비스 종료 및 `service status`의 `stopped` 확인

별도의 VS Code 개발 창에는 동일한 실제 CLI launcher를 PATH로 제공했다. 사전에 `service status`가 `stopped`인 것을 확인한 뒤, 서버 주소가 비어 있는 기본 설정에서 사이드바를 열었다. **서버 준비 중 → 연결됨**, 실제 주소 `http://127.0.0.1:41962`와 `vlocal` 표시를 확인하고 08 스크린샷을 저장했다. 개발 창 종료 후에도 서버가 유지되고 같은 PID로 재연결되는 것을 확인한 다음, 해당 검증용 서버를 종료했다.

`opencode` CLI가 PATH에 설치된 환경에서는 다음 명령으로 통합 검증을 다시 실행할 수 있다. 스크립트가 자체 임시 XDG 경로를 만들고 검증용 서비스만 종료한다. 다른 실행 파일을 사용하려면 명령 뒤에 실행 파일과 필요한 인수를 붙인다.

```sh
cd extension
bun run test:server
```

모델 호출, Windows/Linux 및 최소 지원 VS Code 버전에서의 실행은 확인하지 않았다. 모델 대화·승인/질문·SSE 수신은 #4, 여러 세션과 복원은 #6의 범위다.
