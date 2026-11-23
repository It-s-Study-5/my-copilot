# Codex 프롬프트 (기능별)

## 사용법

- **P0 → P8 순서대로** 하나씩 보낸다. 앞 단계 작업이 끝난 뒤 다음 단계를 보낸다.
- 각 프롬프트는 그대로 복사해서 보내면 된다. 세부 규칙은 `agent.md`, `system_design.md`에 있으므로 프롬프트에는 "이번에 할 일"만 적었다.
- P5의 `{모델 공급자}`, `{모델명}`은 정해지면 채워서 보낸다. 미정이면 그대로 보내도 FakeModel까지만 만들고 멈춘다.

---

## P0. 뼈대 · 공용 모델 · fixtures

```
code-impact/agent.md를 먼저 읽고 그 규칙을 따라라. 0장에 적힌 문서를 순서대로 모두 읽어라.


이번 작업: system_design.md 4장 구조의 뼈대만 만든다.
1. code-impact/code_impact/ 패키지와 4장의 파일들을 만든다. 각 모듈은 문서의 함수 시그니처만 두고 본문은 NotImplementedError.
2. models.py: Function, CallSite, ImpactNode, AnalysisResult dataclass를 3장 필드 규칙에 맞게 정의한다.
   에러 코드 4개(2.2장)에 대응하는 예외 클래스도 여기 둔다.
3. tests/fixtures/: 5장의 JS 파일 4개를 그대로 만든다.
   추가 fixture(중첩 함수, 화살표 함수, 클래스 메서드, 순환 호출 a↔b, 동명 함수 2개)는 tests/fixtures/edge/ 아래에 만든다.
4. requirements.txt(버전 고정), .env.example(변수 이름만), tests/conftest.py(fixtures 경로 제공).
5. tests/test_models.py: dataclass 생성, relation 값이 depth로 결정되는지 정도만.

하지 말 것: 각 모듈의 실제 로직 구현.
끝나면 agent.md 7장 형식으로 보고하라. pytest 실행 결과를 포함하라.
```

---

## P1. ① Function Resolver

```
code-impact/agent.md를 먼저 읽고 그 규칙을 따라라. 0장에 적힌 문서를 순서대로 모두 읽어라.


이번 작업: system_design.md 4장 ① resolve(file, line, col) -> Function 구현.
- tree-sitter-language-pack으로 JS/TS 파싱 (6장 확장자 목록).
- 커서가 함수 선언부 첫 줄 ~ 마지막 닫는 중괄호 사이 어디든 있으면 그 함수, 중첩이면 가장 안쪽 함수.
- 인식 대상: function 선언, 함수 표현식, 화살표 함수, 클래스 메서드, 객체 메서드.
- 익명 함수 이름 규칙, 함수 밖 → NOT_IN_FUNCTION, 미지원 확장자 → UNSUPPORTED_LANGUAGE, 파일 없음 → FILE_NOT_FOUND.
- 입력 line/col은 0부터, Function의 start_line/end_line은 1부터.
- ② Call Hierarchy Analyzer가 "호출 위치를 감싼 함수"를 찾을 때 재사용할 수 있게,
  이미 파싱된 트리와 위치로 가장 안쪽 함수를 찾는 내부 함수를 분리해 둔다.

테스트(tests/test_resolver.py):
- calculatePrice의 선언 줄 / 본문 중간 줄 / 닫는 중괄호 줄 → 모두 calculatePrice
- 중첩 함수 안쪽 커서 → 안쪽 함수, 바깥 함수 본문 커서 → 바깥 함수
- 화살표 함수, 클래스 메서드 이름 인식
- 함수 밖 커서 → NotInFunction, .txt 파일 → UnsupportedLanguage

하지 말 것: 호출자 탐색 구현.
끝나면 agent.md 7장 형식으로 보고하라.
```

---

## P2. ② Call Hierarchy Analyzer

```
code-impact/agent.md를 먼저 읽고 그 규칙을 따라라. 0장에 적힌 문서를 순서대로 모두 읽어라.


이번 작업: system_design.md 4장 ② find_callers(root, target, depth) -> list[ImpactNode] 구현.
- root 아래 지원 파일 전체에서 target 이름의 call expression을 찾고, 호출을 감싼 함수를 ①의 로직으로 찾아 호출자로 기록.
- BFS로 depth 단계까지 역추적. depth 1 = direct, 그 이상 = indirect.
- ImpactNode.calls에 "바로 아래 단계 함수를 호출하는 위치"(1부터 줄 번호)를 채운다.
- 동명 함수: import/require 경로로 좁히고, 못 좁히면 모두 후보로 넣고 warnings에 남긴다.
- 순환 호출 차단, 같은 함수는 가장 작은 depth로 한 번만.
- 제외 디렉터리, 노드 50개 상한 → truncated, 파일 최상위 호출 → <module>.
- root 밖 파일은 읽지 않는다.

테스트(tests/test_hierarchy.py):
- system_design.md 5장 기대 결과표와 정확히 일치 (preparePayment 1, createOrder 1, handleOrderRequest 2)
- 순환 호출에서 무한루프 없이 종료
- 동명 함수 fixture에서 import로 올바른 쪽만 잡히는지
- depth=1이면 handleOrderRequest 없음 + truncated=true
- node_modules 안의 호출은 무시

하지 말 것: obj[name]() 같은 동적 호출, 콜백 전달 추적 (6장: 추후 구현). 한계는 주석으로 남긴다.
끝나면 agent.md 7장 형식으로 보고하라.
```

---

## P3. ③ Code Context Reader

```
code-impact/agent.md를 먼저 읽고 그 규칙을 따라라. 0장에 적힌 문서를 순서대로 모두 읽어라.


이번 작업: system_design.md 4장 ③ read_context(nodes) 구현.
- 각 노드에 함수 전체 소스와 정확한 시작/끝 줄을 채운다. 같은 파일은 한 번만 읽는다.
- 200줄 초과 함수는 호출 줄 앞뒤 30줄만 남기고 잘렸다는 표시를 남긴다.
- 대상 함수(target)의 소스도 같은 방식으로 채운다.

테스트(tests/test_context.py):
- createOrder 소스가 fixture 파일의 해당 부분과 글자 단위로 일치
- 긴 함수 fixture로 자르기 동작 확인
- 같은 파일의 노드 여러 개일 때 파일을 한 번만 여는지

끝나면 agent.md 7장 형식으로 보고하라.
```

---

## P4. ④ Usage Inspector

```
code-impact/agent.md를 먼저 읽고 그 규칙을 따라라. 0장에 적힌 문서를 순서대로 모두 읽어라.


이번 작업: system_design.md 4장 ④ inspect_usage(caller, callee_name) -> list[str] 구현.
- LLM을 절대 호출하지 않는다. tree-sitter 구문 트리만으로 판단한다.
- 4장 ④ 표의 7가지 확인 항목을 모두 구현하고, facts 문장은 표의 예시 문장 형식을 그대로 따른다.
- 변수 추적은 같은 함수 안, 한 단계까지만.
- 한 함수에서 callee를 여러 번 호출하면 호출마다 facts를 만들고 중복 문장은 제거한다.

테스트(tests/test_usage.py):
- createOrder → "amount에 저장", "조건문(amount <= 0)에서 검사", "saveOrder()에 전달" 3개 포함
- preparePayment → "결과를 그대로 반환한다" 포함
- handleOrderRequest(callee=createOrder) → "결과를 그대로 반환한다" 포함
- 반환값 미사용, 삼항 연산자 검사, 메서드 접근(amount.toFixed()) 케이스를 fixture에 추가해 검증

하지 말 것: 재할당 추적, 다른 함수 내부까지 추적 (한계는 주석으로).
끝나면 agent.md 7장 형식으로 보고하라.
```

---

## P5. ⑥ Model Adapter

```
code-impact/agent.md를 먼저 읽고 그 규칙을 따라라. 0장에 적힌 문서를 순서대로 모두 읽어라.


이번 작업: system_design.md 4장 ⑥ complete(system, user) -> str 구현.
- 설정은 .env의 CODE_IMPACT_MODEL_PROVIDER, CODE_IMPACT_MODEL, CODE_IMPACT_API_KEY에서 읽는다 (python-dotenv).
- 공급자: {모델 공급자}, 모델: {모델명}. 이 공급자 1개만 구현한다.
  ※ 위 값이 비어 있거나 중괄호 그대로면 공급자는 구현하지 말고 FakeModel과 공급자 선택 자리만 만든 뒤 보고하라.
- FakeModel: 생성자에 응답 문자열(또는 응답 목록)을 받아 순서대로 반환. 받은 system/user를 기록해 테스트에서 확인 가능하게.
- 설정 누락, API 오류 → MODEL_ERROR 예외. 키 값은 어떤 메시지·로그에도 넣지 않는다.
- .env.example에 변수 이름만 추가.

테스트(tests/test_model.py):
- FakeModel 동작
- 환경변수 누락 시 MODEL_ERROR
- 예외 메시지에 키 문자열이 포함되지 않는지
- 실제 API 호출 테스트는 만들지 않는다.

끝나면 agent.md 7장 형식으로 보고하라.
```

---

## P6. ⑤ Agent Orchestrator

```
code-impact/agent.md를 먼저 읽고 그 규칙을 따라라. 0장에 적힌 문서를 순서대로 모두 읽어라.


이번 작업: system_design.md 4장 ⑤ analyze(root, file, line, col, depth, model) -> AnalysisResult 구현.
- ① → ② → ③ → ④ 순서로 정적 근거를 만든다.
- model은 인자로 주입받는다 (테스트에서 FakeModel 사용).
- 4장 ⑤의 "모델에게 주는 규칙"을 시스템 프롬프트에 모두 포함한다. 모델 응답 JSON 형식도 프롬프트에 명시한다:
  {"impacts": [{"name", "file", "risk", "risk_level"}], "summary": "...", "need_more": ["함수명"]}
- need_more가 오면 ③으로 해당 소스를 읽어 딱 1회만 추가 질의.
- 응답이 유효 JSON이 아니면 1회 재시도, 또 실패하면 AI 필드 null + warnings.
- 모델 응답의 impacts는 정적 분석으로 찾은 함수(name+file)에만 매칭한다. 모델이 없는 함수를 지어내면 버린다.
- 모델 응답은 facts에 절대 넣지 않는다.

테스트(tests/test_orchestrator.py), 전부 FakeModel:
- 정상 응답 → risk/risk_level/summary가 채워지고 facts는 ④ 결과 그대로
- 잘못된 JSON 2번 → AI 필드 null, warnings 있음, 정적 결과는 그대로
- need_more 응답 → 모델 호출이 정확히 2번
- 모델이 존재하지 않는 함수를 응답 → 결과에 없음
- 시스템 프롬프트에 "변경 내용은 주어지지 않았다" 취지 문구가 포함되는지

끝나면 agent.md 7장 형식으로 보고하라.
```

---

## P7. ⑦ Result Formatter + CLI 연결

```
code-impact/agent.md를 먼저 읽고 그 규칙을 따라라. 0장에 적힌 문서를 순서대로 모두 읽어라.


이번 작업:
1. formatter.py: system_design.md 3장 스키마로 조립. 정렬(depth 오름차순 → risk_level 높은 순),
   필수 필드와 값 범위(relation, risk_level) 검증, 파일 경로는 root 기준 상대경로.
2. __main__.py: 2.1장 CLI 완성. 성공 시 stdout에 JSON 1개 + exit 0, 실패 시 2.2장 에러 JSON + exit 1.
   로그는 stderr로만. stdout에 다른 출력이 섞이지 않아야 한다.
   모델은 .env 설정으로 만들고, 테스트에서는 FakeModel을 주입할 수 있게 한다.

테스트:
- tests/test_formatter.py: 정렬, 검증 실패, AI 필드 null 허용
- tests/test_e2e.py: subprocess로 CLI 실행 (FakeModel 주입)
  - price.js calculatePrice 안쪽 커서 → 3장 스키마 통과, 5장 기대 결과표와 일치, stdout이 JSON으로 파싱됨
  - 함수 밖 커서 → exit 1 + NOT_IN_FUNCTION
  - 없는 파일 → FILE_NOT_FOUND

끝나면 agent.md 7장 형식으로 보고하라.
```

---

## P8. 마무리 (전체 점검 + text.txt 정리)

```
code-impact/agent.md를 먼저 읽고 그 규칙을 따라라. 0장에 적힌 문서를 순서대로 모두 읽어라.


이번 작업: 전체 기능을 text.txt 요구사항과 대조해 점검하고 정리한다.
1. text.txt의 기능 ①~⑤와 "3. AI Agent 내부 기능" 표의 7개 구성을 하나씩 대조해,
   각각 어느 파일·테스트가 충족하는지 표로 만들어 보고하라. 못 채운 항목이 있으면 여기서 멈추고 보고만 하라.
2. 모두 충족하면:
   - text.txt의 내용 중 system_design.md에 없는 요구사항이 있으면 system_design.md 1장에 옮겨 적는다.
   - code-impact/text.txt를 삭제한다.
   - system_design.md와 agent.md에서 text.txt를 가리키는 문구를 지우고, 문서 우선순위를 "루트 AGENT.md > system_design.md"로 고친다.
3. pytest 전체 실행 결과 첨부.

끝나면 agent.md 7장 형식으로 보고하라.
```
