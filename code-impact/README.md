# code-impact: 함수 변경 영향도 분석

VS Code에서 **수정하려는 함수 안에 커서를 두고 단축키를 누르면**, 그 함수를 직접·간접 호출하는 함수들을 여러 파일에 걸쳐 찾고, 각 호출자가 인자·반환값을 실제로 어떻게 쓰는지 코드로 확인한 뒤, AI가 잠재적 변경 영향을 설명하는 분석 엔진입니다. 결과는 OpenCode 채팅창에 **함수 영향도 분석** 메시지로 표시됩니다.

이 폴더는 분석 엔진(Python)만 담당합니다. 단축키, 커서 위치 읽기, 화면 표시는 `extension/`(TypeScript)이 합니다. 구조와 입출력 계약은 [system_design.md](system_design.md)에 있습니다.

- 지원 언어: JavaScript / TypeScript (`.js .jsx .ts .tsx .mjs .cjs`)
- 정적 분석(호출 관계, 인자·반환값 사용 방식)으로 확인한 사실은 `facts`, AI가 추정한 영향은 `risk`·`summary`로 **분리해서** 돌려줍니다.

## 개발 실행

Python 3.11 이상이 필요합니다. 저장소 루트에서 다음 명령을 실행합니다.

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

`.venv` 위치는 바꾸지 마세요. VS Code 확장이 `code-impact/.venv`의 Python으로 엔진을 실행합니다.

## 모델 연결

따로 설정할 파일은 없습니다. extension이 채팅에서 선택한 OpenAI 모델과 OpenCode 서버에 저장된 OpenAI API 키를 환경변수(`CODE_IMPACT_MODEL_PROVIDER`, `CODE_IMPACT_MODEL`, `CODE_IMPACT_API_KEY`)로 엔진에 넘깁니다. 채팅 모델이 OpenAI가 아니거나 서버에서 키를 찾지 못하면(서버 환경변수나 OAuth로 연결한 경우 포함) 분석을 실행하지 않고 채팅창에 그 이유를 오류로 표시합니다. 채팅 상단의 **OpenAI API 키 연결**로 키를 등록한 뒤 다시 실행하면 됩니다.

- 설정이 비어 있거나 호출이 실패하면 `summary`와 `risk`가 `null`이 되고, `warnings`에 `AI 분석을 성공적으로 마치지 못했습니다…`가 추가됩니다.
- 모델 API 오류는 키가 노출되지 않도록 HTTP 상태 코드만 남깁니다. `401`은 키 문제, `404`는 모델명 문제, `503`은 공급자의 일시 장애입니다. 일시 장애는 실행 전체에서 1회 재시도합니다.
- 가벼운 모델(예: `gemini-3.5-flash-lite`)은 추가 탐색 도구를 거의 쓰지 않고 바로 답합니다. Agent의 추가 탐색까지 확인하려면 mini급 이상의 모델을 사용하세요.
- 분석할 때마다 현재 채팅 모델을 읽으므로 모델을 바꾸면 다음 분석부터 바로 반영됩니다.

## VS Code에서 사용

[루트 README의 VS Code 테스트 절차](../README.md#vs-code에서-테스트)에 따라 원하는 JavaScript 또는 TypeScript 프로젝트를 Extension Development Host에서 엽니다. OpenCode 서버에 연결한 뒤 다른 함수에서 호출하는 함수의 본문에 커서를 둡니다.

- 에디터에 포커스를 둔 상태에서 Mac은 **`Ctrl+Option+i`**(Shift 없이), Windows/Linux는 **`Ctrl+Alt+Shift+i`**를 누릅니다.
- 로컬 환경에 따라 단축키가 동작하지 않으면 **`Command+Shift+P`**(Windows/Linux는 **`Ctrl+Shift+P`**)로 명령 팔레트를 열고 **Code Impact: 이 함수의 변경 영향도 분석**을 직접 실행합니다.

채팅창에는 다음 순서로 표시됩니다.

- 분석 함수와 파일 위치
- AI 요약(`summary`)과 경고(`warnings`)
- 영향 후보: 위험도(높음·보통·낮음) 순으로, 각 호출자의 위치, 정적 분석 사실(`facts`), **영향도 분석**(`risk`)
- 파일 최상위 코드의 호출은 `<module>` 항목 하나로 묶어 맨 아래에 표시

파일 경로를 누르면 해당 코드로 이동합니다. 함수 밖에서 실행하면 `커서가 함수 안에 있지 않습니다.`를 표시합니다.

## CLI로 직접 실행

확장 없이 엔진만 실행해 응답 JSON을 확인할 수 있습니다. AI 분석까지 보려면 위 세 환경변수를 셸에서 지정합니다(예: `CODE_IMPACT_MODEL_PROVIDER=openai CODE_IMPACT_MODEL=gpt-6.2-sol CODE_IMPACT_API_KEY=… .venv/bin/python -m code_impact …`). 지정하지 않으면 정적 분석 결과에 경고만 붙습니다. 아래 예제에서 프로젝트와 파일의 절대 경로, 함수 본문에 해당하는 줄과 열을 지정합니다. `--line`과 `--col`은 모두 **0부터** 셉니다.

```sh
cd code-impact
.venv/bin/python -m code_impact analyze \
  --root "/path/to/your/project" \
  --file "/path/to/your/project/src/example.ts" \
  --line 2 --col 2
```

- 성공하면 exit 0과 함께 stdout에 JSON 하나를 출력합니다. 필드는 `target`, `summary`, `impacts`, `truncated`, `warnings`, `trace`이며, 각 필드의 규칙은 [system_design.md 3장](system_design.md#3-출력-json-요약--상세)에 있습니다.
- 실패하면 exit 1과 함께 `{"error": {"code", "message"}}`를 출력합니다. 코드는 `NOT_IN_FUNCTION`, `UNSUPPORTED_LANGUAGE`, `FILE_NOT_FOUND`, `MODEL_ERROR`입니다.
- 로그와 디버그 출력은 stderr로만 나갑니다. `jq`가 있으면 `| jq`로 보기 좋게 확인할 수 있습니다.

## Agent 동작과 실행 기록

1. 정적 분석으로 호출자를 `--depth`(기본 3)까지 찾고, 각 호출자의 `facts`를 만듭니다.
2. 모델은 최종 답을 하거나, 판단에 코드가 더 필요하면 도구를 요청합니다.
   - `read_function(name)`: 함수 본문 읽기
   - `find_callers(name)`: 그 함수의 직접 호출자와 `facts`
3. 도구 결과를 붙여 다시 묻습니다. 모델 호출은 최종 답을 포함해 **최대 5회**, 한 번에 도구 **3개**까지입니다. 상한은 `code_impact/orchestrator.py`의 `MAX_TURNS`에서 바꿉니다.

각 단계는 응답의 `trace`에 남고, 채팅창에는 표시하지 않습니다. 대신 CLI가 성공할 때마다 `logs/trace.jsonl`에 한 줄씩 기록합니다. 이 폴더는 Git에 올라가지 않습니다.

```sh
tail -n 1 logs/trace.jsonl | jq '.trace'
jq -c '.trace[] | [.step, .actor, .tool, .reason, .result]' logs/trace.jsonl
```

`actor`는 항상 실행하는 정적 단계(`static`)와 모델이 고른 도구(`agent`)를 구분합니다. `reason`은 모델이 도구를 고른 이유입니다. 로그 위치는 환경 변수 `CODE_IMPACT_LOG_FILE`로 바꿀 수 있습니다(테스트에서 사용).

## 검증

저장소 루트에서 실행합니다. 두 명령은 서로 독립적이라 순서와 상관없습니다.

```sh
(cd code-impact && .venv/bin/python -m pytest)
(cd extension && bun test ./test/impact.test.ts)
```

- `code-impact` 테스트는 `tests/fixtures/`의 샘플 프로젝트로 함수 인식, 여러 파일에 걸친 호출자 탐색, `facts` 추출, 모델 응답 검증, 도구 루프와 상한, 재시도, 출력 형식, CLI 동작과 로그 기록을 확인합니다. 모델은 `FakeModel`로 대체하고, 테스트 중에는 모델 환경변수를 지우므로(`tests/conftest.py`) 셸에 API 키가 있어도 실제 모델을 호출하지 않습니다.
- `extension/test/impact.test.ts`는 채팅창의 분석 메시지 렌더링, 채팅 사이 위치 유지, AI 실패 시 표시, 파일 이동 메시지를 확인합니다.
