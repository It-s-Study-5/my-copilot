# code-impact SYSTEM_DESIGN

> 함수 단위 코드 변경 영향도 분석 AI Agent의 내부 구조와 외부 계약.
> 원본 요구사항: `code-impact/text.txt`. 이 문서와 충돌하면 text.txt를 우선하고 이 문서를 고친다. 기능 구현이 다 되면 `code-impact/text.txt` 파일을 삭제해주세요.

---

## 1. 무엇을 만드는가

개발자가 VS Code에서 **수정하려는 함수 안에 커서를 두고 단축키를 누르면**,
그 함수를 **직접·간접 호출하는 함수들을 여러 파일에 걸쳐 계층적으로 찾고**,
각 호출자가 **선택한 함수의 인자·반환값을 실제로 어떻게 쓰는지 코드로 확인**한 뒤,
AI가 **잠재적 변경 영향**을 설명한 **요약·상세 JSON**을 돌려준다.

- 독립 앱이 아니다. 팀의 OpenCode VS Code Extension에 붙는 기능 중 하나다.
- code-impact는 **분석 엔진(Python)** 만 담당한다. 단축키, 커서 위치 읽기, 화면 표시는 `extension/`(TypeScript)이 한다.
- 사용자는 함수명 입력, 드래그, 자연어 질문, **변경 예정 내용 입력을 하지 않는다**. 입력은 커서 위치뿐이다.

### 하지 않는 것 (범위 밖)

- UI 구현 (JSON만 반환)
- 코드 자동 수정, 테스트 자동 실행
- "이 변경은 반드시 오류를 낸다" 같은 확정 판정 (변경 내용을 모르기 때문)

---

## 2. 외부 계약 (extension ↔ code-impact)

### 2.1 호출 방식

```
python -m code_impact analyze \
  --root <프로젝트 루트 절대경로> \
  --file <분석할 파일 절대경로> \
  --line <커서 줄, 0부터> \
  --col  <커서 열, 0부터> \
  [--depth 3]
```

- 성공: exit 0, **stdout에 JSON 객체 1개만** 출력 (3장 스키마)
- 실패: exit 1, stdout에 에러 JSON 1개
- 로그·디버그 출력은 **stderr로만**

### 2.2 에러 JSON

```json
{
  "error": {
    "code": "NOT_IN_FUNCTION",
    "message": "커서가 함수 안에 있지 않습니다."
  }
}
```

| code                   | 상황                                                    |
| ---------------------- | ------------------------------------------------------- |
| `NOT_IN_FUNCTION`      | 커서가 어떤 함수에도 속하지 않음                        |
| `UNSUPPORTED_LANGUAGE` | 지원하지 않는 파일 형식                                 |
| `FILE_NOT_FOUND`       | 파일 또는 root가 없음                                   |
| `MODEL_ERROR`          | 모델 설정 누락 / 호출 실패 (정적 결과도 못 만든 경우만) |

`message`는 사용자에게 그대로 보여줄 수 있는 한국어 문장으로 쓴다.

---

## 3. 출력 JSON (요약 + 상세)

화면은 "선택 함수 → AI 요약 → 주요 영향 후보 목록 → 펼치면 상세 근거" 순서로 그려진다.
JSON도 그 순서를 그대로 담는다.

```json
{
  "target": {
    "name": "calculatePrice",
    "file": "src/price.js",
    "start_line": 1,
    "end_line": 4
  },
  "summary": "계산 결과가 결제 준비, 주문 금액 검증 및 상위 요청 처리 함수까지 연결되어 있습니다. 금액 계산 로직을 변경한다면 해당 함수들의 결과 사용 방식을 검토하는 것이 좋습니다.",
  "impacts": [
    {
      "name": "createOrder",
      "file": "src/order.js",
      "start_line": 10,
      "end_line": 17,
      "depth": 1,
      "relation": "direct",
      "calls": [{ "callee": "calculatePrice", "line": 11, "col": 17 }],
      "facts": [
        "calculatePrice()의 반환값을 amount에 저장한다.",
        "amount를 조건문(amount <= 0)에서 검사한다.",
        "amount를 saveOrder()에 전달한다."
      ],
      "risk": "계산 결과를 금액 유효성 검사에 사용하므로 반환값의 범위·타입이 변경되면 조건문 동작을 확인해야 합니다.",
      "risk_level": "high"
    }
  ],
  "truncated": false,
  "warnings": []
}
```

### 필드 규칙

| 필드                                      | 만드는 주체 | 규칙                                                          |
| ----------------------------------------- | ----------- | ------------------------------------------------------------- |
| `target`                                  | 정적 분석   | 커서를 감싼 가장 안쪽 함수                                    |
| `impacts[].name/file/start_line/end_line` | 정적 분석   | 실제 파일 경로(root 기준 상대경로), 1부터 시작하는 줄 번호    |
| `impacts[].depth`                         | 정적 분석   | 1 = 직접 호출자, 2 이상 = 간접 호출자                         |
| `impacts[].relation`                      | 정적 분석   | depth 1이면 `"direct"`, 아니면 `"indirect"`                   |
| `impacts[].calls`                         | 정적 분석   | 이 함수 안에서 **바로 아래 단계 함수**를 호출하는 위치        |
| `impacts[].facts`                         | 정적 분석   | **코드로 확인된 사실만**. AI가 쓰지 않는다                    |
| `impacts[].risk`                          | AI          | 추정 설명. 단정 금지 ("확인해야 합니다", "가능성이 있습니다") |
| `impacts[].risk_level`                    | AI          | `"high" \| "medium" \| "low"`                                 |
| `summary`                                 | AI          | 2~3문장 한국어 요약                                           |
| `truncated`                               | 정적 분석   | depth 제한·탐색 상한으로 잘렸으면 true                        |
| `warnings`                                | 전체        | 동명 함수 후보, AI 실패 등 사용자에게 알릴 것                 |

- **핵심 원칙: `facts`(확인된 사실)와 `risk`/`summary`(AI 추정)를 절대 섞지 않는다.**
- AI 호출이 실패해도 정적 결과는 반환한다: `risk`/`risk_level`/`summary`는 `null`, `warnings`에 사유 추가.
- `impacts` 정렬: depth 오름차순 → 같은 depth 안에서 risk_level 높은 순.
- 줄 번호: 입력(`--line`)은 VS Code 기준 0부터, **출력은 사람이 읽는 1부터**.

---

## 4. 내부 구성

```
code-impact/
├── code_impact/
│   ├── __main__.py      CLI 진입점, 에러 → 에러 JSON 변환
│   ├── models.py        공용 dataclass (Function, CallSite, ImpactNode, AnalysisResult)
│   ├── resolver.py      ① Function Resolver
│   ├── hierarchy.py     ② Call Hierarchy Analyzer
│   ├── context.py       ③ Code Context Reader
│   ├── usage.py         ④ Usage Inspector
│   ├── orchestrator.py  ⑤ Agent Orchestrator
│   ├── model.py         ⑥ Model Adapter
│   └── formatter.py     ⑦ Result Formatter
├── tests/
│   ├── fixtures/        샘플 프로젝트 (5장)
│   └── test_*.py
├── requirements.txt
├── .env.example
├── system_design.md
└── agent.md
```

### 처리 흐름

```
CLI 입력(file, line, col)
  → ① resolver   : 커서 → 대상 함수
  → ② hierarchy  : 대상 함수의 호출자를 depth 단계까지 역추적 (여러 파일)
  → ③ context    : 각 함수의 실제 소스코드 + 위치 수집
  → ④ usage      : 각 호출자가 인자/반환값을 어떻게 쓰는지 facts 추출
  ─────────── 여기까지 정적 분석 = "확인된 사실" ───────────
  → ⑤ orchestrator: 정적 근거를 ⑥ model에 전달, 필요 시 추가 탐색 1회
  → ⑥ model      : risk / risk_level / summary 생성 = "AI 추정"
  → ⑦ formatter  : 3장 스키마로 조립·검증 → stdout
```

### ① Function Resolver — `resolve(file, line, col) -> Function`

- 커서가 **함수 선언부 첫 줄 ~ 마지막 닫는 중괄호** 사이 어디든 있으면 그 함수.
- **중첩 함수면 커서를 감싼 가장 안쪽 함수**.
- 함수 밖이면 `NOT_IN_FUNCTION`.
- 인식 대상(JS/TS): `function` 선언, 함수 표현식, 화살표 함수(`const f = () => {}`), 클래스 메서드, 객체 메서드.
- 익명 함수는 변수명/프로퍼티명으로 이름을 정한다. 이름을 못 정하면 `<anonymous>@줄번호`.

### ② Call Hierarchy Analyzer — `find_callers(root, target, depth) -> list[ImpactNode]`

- root 아래 지원 파일 전체에서 `target` 이름의 **호출식(call expression)** 을 찾고,
  그 호출을 감싸는 함수(①의 로직 재사용)를 호출자로 기록한다.
- 찾은 호출자를 새 대상으로 같은 과정을 반복 (BFS), `depth`까지.
- **여러 파일에 걸친 호출**을 찾는다. 같은 이름이 여러 곳에 정의돼 있으면 import/require 경로로 좁히고, 못 좁히면 후보로 모두 넣고 `warnings`에 남긴다.
- 순환 호출은 방문 집합으로 차단. 같은 함수가 여러 경로로 나오면 **가장 작은 depth 한 번만** 기록.
- 제외 디렉터리: `node_modules`, `dist`, `out`, `build`, `.git`, `.venv`.
- 탐색 상한: 노드 50개. 넘으면 중단하고 `truncated: true`.
- 함수 밖(파일 최상위)에서의 호출은 호출자 이름 `<module>`로 기록한다.

### ③ Code Context Reader — `read_context(nodes) -> nodes(+source)`

- 각 함수의 전체 소스와 시작/끝 줄을 채운다. 파일은 한 번만 읽고 캐시.
- 함수가 200줄을 넘으면 호출 줄 앞뒤 30줄만 남기고 잘랐다는 표시를 붙인다 (AI 입력 길이 관리용).

### ④ Usage Inspector — `inspect_usage(caller, callee_name) -> list[str]`

**LLM을 쓰지 않는다.** 구문 트리로 호출부 주변을 보고 확인된 사실만 한국어 문장으로 만든다.
| 확인 항목 | facts 예시 |
|---|---|
| 반환값을 변수에 저장 | `calculatePrice()의 반환값을 amount에 저장한다.` |
| 그 변수를 조건문에서 검사 (if/while/삼항/논리연산) | `amount를 조건문(amount <= 0)에서 검사한다.` |
| 그 변수/호출 결과를 다른 함수 인자로 전달 | `amount를 saveOrder()에 전달한다.` |
| 호출 결과를 그대로 return | `calculatePrice()의 결과를 그대로 반환한다.` |
| 반환값을 사용하지 않음 | `calculatePrice()의 반환값을 사용하지 않는다.` |
| 넘기는 인자 | `price, quantity를 인자로 전달한다.` |
| 반환값의 속성/메서드 접근 | `amount.toFixed()를 호출한다.` |

- 변수 추적은 **같은 함수 안, 한 단계**까지만 (재할당·다른 함수 내부까지 쫓지 않음).

### ⑤ Agent Orchestrator — `analyze(...) -> AnalysisResult`

1. ①~④를 순서대로 실행해 정적 근거를 만든다.
2. ⑥에 대상 함수 코드 + 호출자별 (코드, facts, depth, 호출 경로)를 보낸다.
3. 모델은 JSON으로 호출자별 `risk`, `risk_level`, 전체 `summary`, 선택적으로 `need_more: ["함수명", ...]`를 돌려준다.
4. `need_more`가 있으면 해당 함수 소스를 ③으로 읽어 **딱 1회** 추가 질의한다 (무한 루프 방지).
5. 모델 응답이 유효 JSON이 아니면 1회 재시도, 그래도 실패하면 AI 필드 `null` + `warnings`.

**모델에게 주는 규칙 (시스템 프롬프트에 반드시 포함)**

- 사용자는 변경 내용을 알려주지 않았다. "이 함수가 변경된다면 각 호출자에서 확인해야 할 지점"을 설명하라.
- facts에 없는 동작을 사실처럼 쓰지 마라. 추정은 추정이라고 표현하라.
- "반드시 오류가 발생한다" 같은 단정 금지.
- 각 호출자의 risk는 1~2문장, 한국어.
- risk_level 기준: high = 반환값/인자가 조건·검증·저장·외부 전달에 쓰임, medium = 가공 후 전달, low = 간접 전달만 하거나 결과를 쓰지 않음.

### ⑥ Model Adapter — `complete(system, user) -> str`

- 설정은 `.env`에서 읽는다: `CODE_IMPACT_MODEL_PROVIDER`, `CODE_IMPACT_MODEL`, `CODE_IMPACT_API_KEY`.
- 공급자는 교체 가능하게 이 함수 하나로 감싼다. 처음엔 공급자 1개만 구현.
- 테스트용 `FakeModel`(정해진 응답 반환)을 제공한다.

### ⑦ Result Formatter — `to_json(result) -> str`

- 3장 스키마로 조립, 정렬, 필수 필드·값 범위 검증 후 출력.

---

## 5. 테스트 기준 (fixtures)

`tests/fixtures/` 아래 이 구조를 만들고 모든 단계를 여기에 대해 검증한다.

```js
// price.js
export function calculatePrice(price, quantity) {
  const amount = price * quantity;
  return amount;
}

// payment.js
import { calculatePrice } from "./price.js";
export function preparePayment(price, quantity) {
  return calculatePrice(price, quantity);
}

// order.js
import { calculatePrice } from "./price.js";
export function createOrder(price, quantity) {
  const amount = calculatePrice(price, quantity);
  if (amount <= 0) {
    throw new Error("Invalid amount");
  }
  return saveOrder(amount);
}

// handler.js
import { createOrder } from "./order.js";
export function handleOrderRequest(req) {
  return createOrder(req.price, req.quantity);
}
```

기대 결과 (`price.js`의 calculatePrice 본문에 커서):
| 함수 | depth | relation | 꼭 있어야 할 facts |
|---|---|---|---|
| preparePayment | 1 | direct | 결과를 그대로 반환 |
| createOrder | 1 | direct | amount에 저장 / 조건문 검사 / saveOrder()에 전달 |
| handleOrderRequest | 2 | indirect | createOrder() 결과를 그대로 반환 |

> text.txt의 예시 그림은 preparePayment → createOrder → handleOrderRequest를 1·2·3단계로 그렸지만,
> 예시 코드상 createOrder는 calculatePrice를 직접 호출한다. **실제 코드 기준으로 depth를 계산한다.**

추가 fixture: 중첩 함수, 화살표 함수, 클래스 메서드, 순환 호출(a↔b), 동명 함수 2개.

---

## 6. 결정 사항 / 미정

| 항목             | 결정                                                                                                                                             |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| 언어             | Python 3.11+                                                                                                                                     |
| 파서             | tree-sitter (`tree-sitter-language-pack`)                                                                                                        |
| 1차 지원 언어    | JavaScript / TypeScript (`.js .jsx .ts .tsx .mjs .cjs`). 이후 Python 추가                                                                        |
| 기본 depth       | 3                                                                                                                                                |
| 호출 탐색 방식   | 이름 기반 + import 경로로 좁히기 (동적 호출, `obj[name]()`, 콜백 전달은 못 찾음 → 추후 구현할 예정임)                                            |
| 추후 구현할 내용 | VS Code 내장 Call Hierarchy(extension 측)을 사용하지 않고, 우선 위의 내용들로 정적 분석을 한 후, `obj[name]()`, 콜백 전달은 나중에 구현할 예정임 |
| **미정**         | 사용할 모델 공급자/모델명                                                                                                                        |
