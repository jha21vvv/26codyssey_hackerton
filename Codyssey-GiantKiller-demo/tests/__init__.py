"""테스트 공통 환경. 어떤 테스트보다 먼저 실행된다 (ai 설정을 불러오기 전에 정해야 함).

실제 시연 DB(data/jikimi.db)를 건드리지 않도록 임시 폴더를 쓰고, 외부 LLM·음성 API 를 부르지 않는다.
"""
import os
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp(prefix="jikimi-test-"))
os.environ.update({
    "DB_PATH": str(_tmp / "test.db"),
    "UPLOAD_DIR": str(_tmp / "uploads"),
    "CONFIRM_TIMEOUT_SEC": "1",
    "LLM_PROVIDER": "rule",
    "TRANSCRIBE_PROVIDER": "none",
    "AI_SERVER_KEY": "",
    "CLASSIFIER_DIR": "",
    "LLM_USAGE_FILE": str(_tmp / "llm_usage.json"),  # 실제 사용량 기록을 건드리지 않게
})
