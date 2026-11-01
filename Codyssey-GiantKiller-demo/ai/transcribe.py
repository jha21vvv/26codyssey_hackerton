"""통화 녹음 → 텍스트. .txt 는 그대로 읽는다 (시연·테스트용 대본).

팀원 방식(model/voice_stt.py · stt/stt_local.py)에 맞춤: faster-whisper, 서버에서는 large 모델.
순서: WHISPER_API_URL(GPU 서버 Whisper) → 이 컴퓨터의 faster-whisper. 통화 원본은 외부 API 로 보내지 않는다.
"""
import logging
import os
import re
from pathlib import Path

import httpx

from . import diarize

log = logging.getLogger("ai")

_whisper_model = None

# Whisper 공통 옵션: 팀원 stt_local.py 와 같은 vad_filter·beam_size=5.
# condition_on_previous_text=False 는 우리가 더한 것: 조용한 구간에서 앞 문장을 되풀이해 지어내는 것("네. 네. 네. …") 줄이기
WHISPER_OPTS = {"vad_filter": True, "beam_size": 5, "condition_on_previous_text": False}
_REPEAT_PHRASE = re.compile(r"(\S.{0,30}?)(?:\s*\1){2,}")


def clean_repeats(text: str) -> str:
    """Whisper 가 지어낸 반복 정리: 같은 줄이 연달아 나오면 한 줄로, 한 줄 안에서 같은 말이 3번 이상 이어지면 한 번으로."""
    out: list[str] = []
    for line in text.splitlines():
        line = _REPEAT_PHRASE.sub(r"\1", line).strip()
        if line and (not out or out[-1] != line):
            out.append(line)
    return "\n".join(out)


def _has_faster_whisper() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False


def _provider() -> str:
    p = os.getenv("TRANSCRIBE_PROVIDER", "auto").strip().lower()
    if p != "auto":
        return p
    if os.getenv("WHISPER_API_URL"):
        return "whisper_api"
    if _has_faster_whisper():
        return "whisper_local"
    return "none"


def _whisper_api(path: Path) -> str:
    url = os.environ["WHISPER_API_URL"].rstrip("/") + "/v1/audio/transcriptions"
    with path.open("rb") as f:
        r = httpx.post(url, files={"file": (path.name, f)},
                       data={"model": os.getenv("WHISPER_MODEL", "large-v3"), "language": "ko"}, timeout=300)
    r.raise_for_status()
    return r.json()["text"].strip()


def _whisper_local(path: Path) -> str:
    global _whisper_model
    from faster_whisper import WhisperModel
    if _whisper_model is None:
        _whisper_model = WhisperModel(os.getenv("WHISPER_MODEL", "large-v3"), device="auto")
    if diarize.enabled():  # 화자 구분 → '상대:' / '부모님:' 줄 (ai/diarize.py)
        return diarize.transcribe_with_speakers(_whisper_model, path, **WHISPER_OPTS)[0]
    segments, _ = _whisper_model.transcribe(str(path), language="ko", **WHISPER_OPTS)
    return "\n".join(s.text.strip() for s in segments)


ENGINES = {"whisper_api": _whisper_api, "whisper_local": _whisper_local}


def transcribe(path: str | Path) -> tuple[str, str]:
    """(텍스트, 사용한 엔진). 엔진: text | whisper_api | whisper_local"""
    path = Path(path)
    if path.suffix.lower() == ".txt":
        return path.read_text(encoding="utf-8").strip(), "text"

    p = _provider()
    if p not in ENGINES:
        raise RuntimeError("음성 변환 엔진이 없습니다. WHISPER_API_URL(GPU 서버) 을 설정하거나 faster-whisper 를 설치하거나 .txt 대본을 올려 주세요.")
    text = ENGINES[p](path)
    return clean_repeats(text), p
