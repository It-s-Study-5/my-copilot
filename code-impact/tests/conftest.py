from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def log_file(tmp_path: Path, monkeypatch) -> Path:
    # 테스트 실행이 실제 logs/trace.jsonl에 쌓이지 않게 한다. subprocess도 환경변수를 물려받는다.
    path = tmp_path / "trace.jsonl"
    monkeypatch.setenv("CODE_IMPACT_LOG_FILE", str(path))
    return path


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def edge_dir(fixtures_dir: Path) -> Path:
    return fixtures_dir / "edge"
