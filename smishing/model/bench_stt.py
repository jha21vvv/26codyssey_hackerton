"""전사 모델/장치별 시간을 잰다. 사용: python bench_stt.py <tag> <모델> <cuda|cpu> <compute_type> <threads> <음성> [기준전사본]
출력: data/derived/bench/<tag>.txt, 한 줄 요약(모델 적재 시간, 전사 시간, 오디오 길이, 기준 대비 단어 오류율)
"""
import sys, time
from pathlib import Path

tag, model, dev, ctype, thr, audio = sys.argv[1:7]
ref = sys.argv[7] if len(sys.argv) > 7 else None
out = Path(__file__).resolve().parent.parent / "data/derived/bench"
out.mkdir(parents=True, exist_ok=True)
from faster_whisper import WhisperModel

t0 = time.time()
wm = WhisperModel(model, device=dev, compute_type=ctype, cpu_threads=int(thr))
t_load = time.time() - t0
t0 = time.time()
segs, info = wm.transcribe(audio, language="ko", vad_filter=True, beam_size=5)
text = "\n".join(s.text.strip() for s in segs)
t_stt = time.time() - t0
(out / f"{tag}.txt").write_text(text, encoding="utf-8")


def wer(a, b):
    a, b = a.split(), b.split()
    d = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        prev, d[0] = d[0], i
        for j, y in enumerate(b, 1):
            prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (x != y))
    return d[len(b)] / max(len(a), 1)


w = f" 기준 대비 단어오류율 {wer(Path(ref).read_text(encoding='utf-8'), text):.1%}" if ref else ""
print(f"[{tag}] 적재 {t_load:.1f}s 전사 {t_stt:.1f}s 오디오 {info.duration:.0f}s 배속 {info.duration / t_stt:.2f}x 글자 {len(text)}{w}")
