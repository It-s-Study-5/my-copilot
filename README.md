# my-copilot
It's study 5기 '나만의 코파일럿 만들기'

## opencode 서버 띄우기

opencode 본체는 `opencode/`에 있다. 서버를 따로 띄우고 화면은 그 서버에 붙여서 본다.

### 준비

[Bun](https://bun.sh)이 필요하다. npm으로는 동작하지 않는다.

macOS:

```bash
brew install oven-sh/bun/bun
```

Windows (PowerShell, Windows 10 1809 이상):

```powershell
powershell -c "irm bun.sh/install.ps1|iex"
```

설치 후 `bun --version`이 안 되면 `%USERPROFILE%\.bun\bin`을 사용자 PATH에 추가하고 터미널을 다시 연다.

공통:

```bash
cd opencode
bun install
```

### 서버 실행 (터미널 1)

```bash
cd opencode
bun run dev serve --port 4096
```

### 화면 붙이기 (터미널 2)

```bash
cd opencode
bun run dev --server http://localhost:4096
```

브라우저로 보려면 `bun run dev pair --url http://localhost:4096`이 출력하는 링크를 연다.

`--hostname 0.0.0.0`이나 `--remote`는 서버를 외부에 노출하므로 로컬에서만 쓸 때는 붙이지 않는다.
