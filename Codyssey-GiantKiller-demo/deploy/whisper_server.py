"""GPU 서버(gp1l4-g3, L4 24GB)용 Whisper 음성 → 텍스트 서버. OpenAI 호환 /v1/audio/transcriptions.

GPU 서버에서 (저장소 루트):
    python3 -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-gpu.txt
    .venv/bin/uvicorn deploy.whisper_server:app --host 0.0.0.0 --port 8100

화자 구분 (통화 받아쓰기에 '상대:' / '부모님:' 줄 이름, ai/diarize.py):
    WHISPER_DIARIZE=1 HF_TOKEN=<Hugging Face 토큰> .venv/bin/uvicorn deploy.whisper_server:app --host 0.0.0.0 --port 8100
    토큰 계정으로 pyannote/speaker-diarization-3.1 · pyannote/segmentation-3.0 페이지에서 약관 동의가 먼저 필요

본 서버 .env:
    TRANSCRIBE_PROVIDER=whisper_api
    WHISPER_API_URL=http://<GPU서버 내부IP>:8100

※ CUDA 라이브러리(cuBLAS·cuDNN) 오류가 나면: .venv/bin/pip install nvidia-cublas-cu12 nvidia-cudnn-cu12
   그래도 안 되면 WHISPER_DEVICE=cpu 로 먼저 동작만 확인.
"""
import os
import tempfile
import time
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from faster_whisper import WhisperModel

from ai import diarize
from ai.transcribe import WHISPER_OPTS, clean_repeats

MODEL = os.getenv("WHISPER_MODEL", "large-v3")
DEVICE = os.getenv("WHISPER_DEVICE", "cuda")
model = WhisperModel(MODEL, device=DEVICE, compute_type="float16" if DEVICE == "cuda" else "int8")

app = FastAPI(title="whisper")


@app.get("/health")
def health():
    return {"ok": True, "model": MODEL, "device": DEVICE, "diarize": diarize.enabled()}


@app.post("/v1/audio/transcriptions")
async def transcriptions(file: UploadFile = File(...), model_name: str = Form("", alias="model"), language: str = Form("ko")):
    suffix = Path(file.filename or "a.m4a").suffix or ".m4a"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as f:
        f.write(await file.read())
        f.flush()
        t0 = time.time()
        if diarize.enabled():
            text, duration = diarize.transcribe_with_speakers(model, f.name, language or "ko", **WHISPER_OPTS)
        else:
            segments, info = model.transcribe(f.name, language=language or "ko", **WHISPER_OPTS)
            text, duration = "\n".join(s.text.strip() for s in segments), info.duration
    return {"text": clean_repeats(text), "duration": duration, "elapsed": round(time.time() - t0, 2), "diarize": diarize.enabled()}
