"""스미싱/보이스피싱 판정 단독 실행기. 학습 코드 없이 이 폴더만으로 동작한다.

사용: python judge.py <파일...> [--model base|large]
- 음성(.m4a .mp3 .wav .mp4): faster-whisper large-v3 로 전사한 뒤 판정
- 텍스트(.txt): 그대로 판정. 문자 한 통이면 --sms 를 붙인다(창으로 자르지 않음)
판정: 200자 창(간격 100)마다 스미싱 확률을 구해 사기 판정 창 비율이 30% 이상이면 '사기 의심'.
"""
import argparse, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer
from build_unified import URL_RE, domain_kind

CHUNK, STRIDE, MIN_FRAC = 200, 100, 0.3
AUDIO = {".m4a", ".mp3", ".wav", ".mp4"}


def tokenize_urls(text):
    return URL_RE.sub(lambda m: f"[URL_{domain_kind(m.group(1))}]", text)


def windows(text):
    text = " ".join(text.split())
    if len(text) <= CHUNK:
        return [text] if text else []
    return [text[i:i + CHUNK] for i in range(0, len(text) - CHUNK // 2, STRIDE)]


def transcribe(path):
    from faster_whisper import WhisperModel
    wm = WhisperModel("large-v3", device="cuda", compute_type="float16")
    segs, _ = wm.transcribe(str(path), language="ko", vad_filter=True, beam_size=5)
    return "\n".join(s.text.strip() for s in segs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--model", choices=["base", "large"], default="base")
    ap.add_argument("--sms", action="store_true")
    a = ap.parse_args()
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    mdir = HERE / "models" / a.model
    tok = AutoTokenizer.from_pretrained(mdir)
    model = AutoModelForSequenceClassification.from_pretrained(mdir).to(dev).eval()
    for f in map(Path, a.files):
        text = transcribe(f) if f.suffix.lower() in AUDIO else f.read_text(encoding="utf-8")
        ws = [" ".join(text.split())] if a.sms else windows(text)
        if not ws:
            print(f"{f.name}: 내용 없음"); continue
        enc = tok([tokenize_urls(w) for w in ws], truncation=True, max_length=128, padding=True, return_tensors="pt").to(dev)
        with torch.no_grad():
            p = model(**enc).logits.softmax(-1)[:, 1].cpu().tolist()
        frac = sum(x > 0.5 for x in p) / len(p)
        print(f"{f.name}: {'사기 의심' if frac >= MIN_FRAC else '정상 추정'} (창 {len(p)}개, 사기 판정 {frac:.0%}, 최대 확률 {max(p):.3f})")


if __name__ == "__main__":
    main()
