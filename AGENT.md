# AGENT.md

## 폴더와 언어

| 폴더 | 역할 | 언어 |
|---|---|---|
| copilot/ | OpenCode 연결, 명령어 처리, 에이전트 호출 | TypeScript |
| extension/ | VS Code 명령, 단축키, 화면 | TypeScript |
| ai-slop/ | AI Slop 검증 | Python |
| code-impact/ | 코드 변경 영향도 분석 | Python |

## 하드 룰

- 브랜치는 기능별로 만든다: `feature/<영역>-<기능>`, 버그는 `fix/<영역>-<내용>`
  - 예: `feature/ai-slop-staged-diff`
- main에 직접 push하지 않는다. PR + 리뷰 1명 이상 승인 후 merge한다.
- 커밋 메시지는 `<type>(<영역>): <요약>` 형식이다.
  - type: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`
- LLM 직접 호출은 Python(ai-slop, code-impact)에서만 한다.
- TypeScript는 화면, VS Code 연결, OpenCode 연결만 담당한다.
- 양식을 바꾸면 PR 제목에 `[양식 변경]`을 붙이고 관련 담당자를 리뷰어로 지정한다.
- 다른 담당 폴더의 코드는 고치지 않는다. 필요하면 이슈를 만든다.
- API key, token은 코드나 커밋에 절대 넣지 않는다.
  - 키는 로컬의 `.env` 파일에만 적고, `.env`는 커밋하지 않는다. (`.gitignore`에 등록되어 있음)
  - 팀원에게 필요한 변수 목록은 값 없이 `.env.example`에 적어 공유한다.
- 실행해 보지 않은 것을 "완료"라고 쓰지 않는다. PR에 실제 확인 방법과 결과를 적는다.

## 문서 위치

- 전체 구조: `SYSTEM_DESIGN.md`
- 폴더 내부 구조: `<폴더>/SYSTEM_DESIGN.md`
- 화면 규칙: `extension/DESIGN.md`
