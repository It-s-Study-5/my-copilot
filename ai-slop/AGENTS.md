# ai-slop 작업 규칙

팀 공통 규칙은 [루트 AGENT.md](../AGENT.md), 이 모듈의 판정과 연동 기준은 [SYSTEM_DESIGN.md](SYSTEM_DESIGN.md)에 있다. 설치와 시연 순서는 [README.md](README.md)를 따른다.

- 입력은 다음 커밋에 들어갈 Git index다. 작업 폴더에서 읽은 내용으로 검사 결과를 대신하면 부분 스테이징에서 잘못 통과할 수 있다.
- 확정한 실패에는 관찰한 근거를 남긴다. 실행 오류나 미지원 환경은 미확인으로 표시한다. 모델이나 DB 대역이 제공한 값과 실제 환경에서 관찰한 값을 구분한다.
- 호출 계약을 바꿀 때는 사람이 읽는 출력, JSON 출력, 종료 코드, 이 폴더의 설계 문서를 함께 확인한다. VS Code와 OpenCode 연결은 #7, #29 담당자와 맞춘다.
- 판정 로직을 바꾸면 팀 저장소 루트에서 `python3 -m unittest discover -s ai-slop -v`를 실행한다. 커밋 훅 변경은 README의 리허설로 Git HEAD와 stage 보존까지 확인한다.
