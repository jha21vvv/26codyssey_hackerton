"""부모님 지킴이 AI 서버. 백엔드(BE 레포)의 AIClient 가 HTTP 로 부른다. 계약: docs/AI_API.md

    uvicorn ai.server:app --host 0.0.0.0 --port 8100

주소는 BE AIClient 의 두 함수에 맞춘 두 개뿐이고, 응답은 BE 결과 모델(AlertAnalysisResult · CallAnalysisResult) 그대로다.
- 판단: 키워드 규칙 → 팀원 BERT → LLM(코디세이 게이트웨이) → 안전망 (ai/analyzer.py). LLM 이 실패해도 '안전'으로 넘기지 않는다
- 받아쓰기: faster-whisper (GPU 서버 또는 이 컴퓨터). 녹음 원본은 외부 API 로 보내지 않고, 받아쓰기 직후 지운다
- 개인정보: 받은 내용을 한 번 더 가리고, 원문은 로그에 남기지 않는다
"""
import logging
import os
import tempfile
import time
from pathlib import Path

import httpx
from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from . import analyze, llm
from .privacy import mask_text
from .transcribe import _provider as stt_provider
from .transcribe import transcribe

SCHEMA_VERSION = "2"
MAX_AUDIO_MB = int(os.getenv("AI_MAX_AUDIO_MB", "25"))
AUDIO_EXT = {".m4a", ".mp3", ".wav", ".aac", ".ogg", ".flac", ".amr", ".3gp", ".aiff", ".txt"}

# 안 ↔ 밖 값 이름 (밖은 백엔드 표기에 맞춘 대문자)
INSTR_OUT = {"app_install": "INSTALL_APP", "remote_control": "INSTALL_REMOTE", "transfer": "TRANSFER",
             "cash": "CASH", "share_info": "SHARE_INFO"}

# BE 는 내용만 보낸다 → 보낸 번호·자녀 번호·이전 통화 맥락 없이 판단
CONTEXT = {"child_relation": "자녀분", "sender_kind": "unknown", "sender_is_child": False, "sender_known": False,
           "previous_calls": []}

log = logging.getLogger("ai.server")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)

app = FastAPI(title="부모님 지킴이 AI", version=SCHEMA_VERSION)


def _check_key(key: str | None):
    want = os.getenv("AI_SERVER_KEY")
    if want and key != want:
        raise HTTPException(401, "AI 서버 키가 맞지 않아요 (X-AI-Key)")


def to_be(r: dict, with_instructions: bool) -> dict:
    """우리 판단 → BE 결과 형식. classification 은 SCAM | CHILD_IMPERSONATION | NEED_EXPLAIN | SAFE,
    requires_attention 은 사기·사칭일 때만 true (BE: 사칭이면 반드시 true). NEED_EXPLAIN 은 요약 자리에 쉬운 설명."""
    cat = r["category"].upper()
    be = {
        "classification": cat,
        "requires_attention": cat in ("SCAM", "CHILD_IMPERSONATION"),
        "risk_level": r["risk"].upper(),
        "summary": (r["explain"] if cat == "NEED_EXPLAIN" and r["explain"] else r["summary"]) or None,
    }
    if with_instructions:
        apps = ", ".join(r.get("mentioned_apps") or [])
        be["instructions"] = [{"instruction_type": INSTR_OUT[i], "description": (apps or None) if i in ("app_install", "remote_control") else None}
                              for i in r["instructions"] if i in INSTR_OUT]
    return be


def _judge(kind: str, content: str, t0: float) -> dict:
    r = analyze({"event_id": "", "type": kind, "sender": "", "content": content}, CONTEXT)
    # 원문은 남기지 않는다: 분류·엔진·시간만
    log.info("%s → %s/%s %s %dms", kind, r["category"], r["risk"], r.get("engine", ""), int((time.time() - t0) * 1000))
    return r


@app.get("/health")
def health():
    from . import classifier
    return {"ok": True, "schema_version": SCHEMA_VERSION, "llm": llm.provider(), "transcribe": stt_provider(),
            "bert": os.getenv("CLASSIFIER_DIR") if classifier.available() else None}


class AlertIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)


@app.post("/v1/alerts/analyze")
def analyze_alert(body: AlertIn, x_ai_key: str | None = Header(None)):
    """BE AIClient.analyze_alert(text) 용 → {classification, requires_attention, risk_level, summary}"""
    _check_key(x_ai_key)
    return to_be(_judge("message", mask_text(body.text), time.time()), with_instructions=False)


async def _save_audio(file: UploadFile) -> Path:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in AUDIO_EXT:
        raise HTTPException(415, f"지원하지 않는 파일 형식이에요: {suffix or '확장자 없음'} ({', '.join(sorted(AUDIO_EXT))})")
    data = await file.read()
    if len(data) > MAX_AUDIO_MB * 1024 * 1024:
        raise HTTPException(413, f"파일이 너무 커요 (최대 {MAX_AUDIO_MB}MB)")
    if not data:
        raise HTTPException(400, "빈 파일이에요")
    fd, name = tempfile.mkstemp(suffix=suffix)
    os.write(fd, data)
    os.close(fd)
    return Path(name)


async def _transcribe(file: UploadFile) -> str:
    path = await _save_audio(file)
    try:
        text, _ = await run_in_threadpool(transcribe, path)
    except RuntimeError as e:  # 음성 엔진 미설정
        raise HTTPException(503, str(e))
    except (llm.LLMError, httpx.HTTPError) as e:  # Whisper 서버 오류 → 백엔드가 실패로 기록
        raise HTTPException(502, f"음성 변환 실패: {e}")
    finally:
        path.unlink(missing_ok=True)  # 녹음 원본은 바로 지운다
    if not text.strip():
        raise HTTPException(422, "녹음에서 말소리를 찾지 못했어요")
    return text


@app.post("/v1/calls/analyze")
async def analyze_call(file: UploadFile = File(...), x_ai_key: str | None = Header(None)):
    """BE AIClient.analyze_call(file) 용 → {classification, requires_attention, risk_level, summary, instructions}"""
    _check_key(x_ai_key)
    t0 = time.time()
    text = await _transcribe(file)
    r = await run_in_threadpool(_judge, "call", mask_text(text), t0)
    return to_be(r, with_instructions=True)
