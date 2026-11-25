# AI Slop 커밋 검사

Conduit에서 AI가 게시글 작성을 수정한 뒤 커밋하는 시연용이다. 새로 추가한 프론트엔드 디버그 흔적을 찾고 스테이징한 백엔드 코드로 글 생성 조건을 실행한다. 파일 위치, 실패한 조건과 미확인 범위를 코파일럿에 다시 전달할 수 있다.

## 이틀 MVP 계획

1. 첫날에는 staged diff에서 디버그 흔적을 찾고 Conduit 글 생성 컨트롤러에 공백 제목과 정상 제목을 전달한다. 같은 Git tree를 두 검사에 사용한다.
2. 둘째 날에는 커밋 훅과 수정 피드백을 연결하고, 실패 후 작업 파일만 고친 경우와 다시 stage한 경우를 비교해 촬영한다. 검사 오류도 커밋을 막아야 한다.

커밋 판정에는 모델이나 API 키가 필요하지 않다. 사용자가 실패 근거로 수정을 요청하면 코드 수정은 팀의 기본 코파일럿이 맡는다.

## 시연하기

Git과 Python 3, Node.js가 필요하다. 검사는 index 안의 JavaScript를 실제 실행하므로 본인이 신뢰하는 로컬 시연 저장소에서 사용한다. 별도 DB 없이 컨트롤러를 호출하고 모델과 HTTP 요청/응답은 대역을 사용한다. 브라우저, 라우터 연결과 실제 저장 여부는 미확인으로 남긴다.

다음 명령은 **시연용 Conduit 복제본의 루트**에서 실행한다. 첫 줄은 팀 저장소의 실제 경로로 바꾼다.

```sh
SLOP_DIR=/absolute/path/to/my-copilot/ai-slop
python3 "$SLOP_DIR/gate.py"
python3 "$SLOP_DIR/gate.py" --json
```

시연용 복제본에서만 다음처럼 훅을 연결한다. 기존 훅을 운용하는 저장소에서는 기존 pre-commit에서 gate.py를 호출하고 실패 코드를 전달한다. hooksPath 설정은 해당 복제본의 다른 Git 훅 경로도 바꾼다.

```sh
git config --local aiSlop.gate "$SLOP_DIR/gate.py"
git config --local core.hooksPath "$SLOP_DIR"
```

1. AI가 글 작성 화면만 수정했거나 서버에서 공백을 놓친 상태를 stage한다. 프론트엔드 변경에 임시 디버그 출력이 남아 있다면 줄 위치도 함께 뜬다.
2. 커밋을 시도한다. FAIL 근거를 기본 코파일럿에 전달한다. 예를 들어 “공백 제목이 생성 경로까지 도달했어. 공백 처리를 고치고 표시된 디버그 로그도 정리해줘”라고 요청한다.
3. 수정 후 다시 stage하고 커밋한다. 같은 조건의 검사가 통과하면 Git이 커밋을 계속한다.

종료 코드 0은 검사한 범위 통과, 1은 위반, 2는 판정 불가다. 일부 검사가 실패하고 다른 검사가 미확인이면 전체는 실패이며 JSON에서 개별 상태를 확인할 수 있다. 도구 연동에는 `--json`을 사용한다. 종료 코드가 1이나 2일 때도 stdout에 결과가 있다.

## 리허설과 테스트

기준 앱은 TonyMckes/conduit-realworld-example-app의 커밋 `5e127d8`이다. 준비된 기준 앱의 로컬 경로를 넘기면 임시 복제본에서만 커밋 두 단계를 재현한다.

```sh
python3 ai-slop/rehearse.py /path/to/conduit
python3 -m unittest discover -s ai-slop -v
```

디버그 검사는 frontend/src의 제품 JS와 TS에서 새로 추가한 한 줄짜리 독립 console.log 또는 debugger 문장을 대상으로 한다. 일반 로그의 의도나 코드의 AI 작성 여부는 판단하지 않는다.
