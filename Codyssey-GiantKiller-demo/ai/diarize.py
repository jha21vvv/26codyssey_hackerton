"""통화 녹음 화자 구분: Whisper 단어 시간 + pyannote 화자 구간 → '상대:' / '부모님:' 줄.

팀원이 만든 stt_local.py 의 방식 (faster-whisper word_timestamps + pyannote/speaker-diarization-3.1) 을 옮겼다.
줄 이름을 붙이면 판단 AI·규칙이 지시(앱 설치·이체·현금)를 '상대:' 말에서만 뽑는다 — 부모님이 되묻는 말("앱을요?")을
지시로 잡지 않게 (ai/prompts.py, ai/rules.py other_party).

필요한 것 (GPU 서버 또는 로컬):
    pip install faster-whisper pyannote.audio
    HF_TOKEN=...   # Hugging Face 토큰. pyannote/speaker-diarization-3.1, pyannote/segmentation-3.0 페이지에서 이용 약관 동의
    WHISPER_DIARIZE=1

pyannote·토큰이 없거나 실패하면 화자 구분 없이 받아쓰기만 돌려준다.
"""
import logging
import os
from pathlib import Path

log = logging.getLogger("ai")

_pipeline = None


def enabled() -> bool:
    return os.getenv("WHISPER_DIARIZE", "").strip().lower() in ("1", "true", "yes", "on")


def _hf_token() -> str | None:
    for name in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN", "HUGGINGFACE_TOKEN"):
        if os.getenv(name):
            return os.environ[name]
    return None


def turns(path: str | Path, speakers: int = 2) -> list[tuple[float, float, str]]:
    """pyannote 로 [(시작, 끝, 화자)] 목록. 모델은 한 번만 읽는다."""
    global _pipeline
    import torch
    from faster_whisper.audio import decode_audio
    from pyannote.audio import Pipeline

    if _pipeline is None:
        token = _hf_token()
        if not token:
            raise RuntimeError("HF_TOKEN 이 없어요 (pyannote 모델을 받으려면 Hugging Face 토큰 필요)")
        _pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1", token=token)
        if torch.cuda.is_available():
            _pipeline.to(torch.device("cuda"))
    wav = torch.from_numpy(decode_audio(str(path), sampling_rate=16000)).unsqueeze(0)
    out = _pipeline({"waveform": wav, "sample_rate": 16000}, num_speakers=speakers)
    ann = getattr(out, "speaker_diarization", out)  # pyannote 버전에 따라 결과 모양이 다르다
    return [(t.start, t.end, spk) for t, _, spk in ann.itertracks(yield_label=True)]


def speaker_at(ts: list[tuple[float, float, str]], t0: float, t1: float) -> str:
    """단어 구간과 가장 많이 겹치는 화자. 겹치는 게 없으면 가장 가까운 구간의 화자"""
    best, overlap = None, 0.0
    for s, e, spk in ts:
        o = min(t1, e) - max(t0, s)
        if o > overlap:
            best, overlap = spk, o
    if best is None:
        mid = (t0 + t1) / 2
        best = min(ts, key=lambda x: min(abs(x[0] - mid), abs(x[1] - mid)))[2]
    return best


def merge(words: list[tuple[float, float, str]], ts: list[tuple[float, float, str]]) -> list[list]:
    """단어 [(시작, 끝, 글자)] 를 화자별로 이어 붙인다 → [[시작, 끝, 화자, 말], ...]"""
    out: list[list] = []
    for w0, w1, word in words:
        spk = speaker_at(ts, w0, w1) if ts else "?"
        if out and out[-1][2] == spk:
            out[-1][1] = w1
            out[-1][3] += word
        else:
            out.append([w0, w1, spk, word])
    return out


def roles(segs: list[list]) -> dict[str, str]:
    """화자 → '상대' / '부모님'.
    보이스피싱 통화는 상대(사기범)가 대부분을 말한다 → 말한 시간이 확실히 긴 쪽이 '상대'.
    비슷하면 먼저 말한 쪽이 '부모님' (전화를 받으며 "여보세요").
    화자가 둘이 아니면 '화자1'·'화자2'… 로 둔다 (판단 AI 가 문맥으로 본다)."""
    order = list(dict.fromkeys(s[2] for s in segs))
    if len(order) != 2:
        return {spk: f"화자{i}" for i, spk in enumerate(order, 1)}
    talk = {spk: sum(s[1] - s[0] for s in segs if s[2] == spk) for spk in order}
    a, b = order
    if talk[a] >= talk[b] * 1.2:
        other = a
    elif talk[b] >= talk[a] * 1.2:
        other = b
    else:
        other = b  # 비슷하면 먼저 말한 a 가 부모님
    return {other: "상대", (b if other == a else a): "부모님"}


def to_text(segs: list[list]) -> str:
    names = roles(segs)
    return "\n".join(f"{names[spk]}: {text.strip()}" for _, _, spk, text in segs if text.strip())


def transcribe_with_speakers(model, path: str | Path, language: str = "ko", speakers: int = 2, **opts) -> tuple[str, float]:
    """faster-whisper 모델로 받아쓰고 화자 줄 이름을 붙인다 → (텍스트, 길이 초). 화자 구분이 실패하면 줄 이름 없이.
    opts: model.transcribe 에 더 넘길 옵션 (ai/transcribe.py WHISPER_OPTS)"""
    opts = {"vad_filter": True, "beam_size": 5, **opts}
    segments, info = model.transcribe(str(path), language=language, word_timestamps=True, **opts)
    segments = list(segments)
    try:
        words = [(w.start, w.end, w.word) for s in segments for w in (s.words or [])]
        return to_text(merge(words, turns(path, speakers))), info.duration
    except Exception as e:
        log.warning("화자 구분 실패 → 줄 이름 없이 받아쓰기만: %s", e)
        return "\n".join(s.text.strip() for s in segments), info.duration
