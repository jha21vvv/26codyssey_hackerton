"""GPU 서버에서 data/voice/*.m4a 전체를 faster-whisper large-v3 로 전사해
data/derived/voice_transcripts_large/ 에 저장한다. 이미 있는 파일은 건너뛴다.
사용: python model/voice_large.py   (CUDA 필요)
"""
import glob, time
from pathlib import Path
from faster_whisper import WhisperModel

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data/derived/voice_transcripts_large"
OUT.mkdir(parents=True, exist_ok=True)
wm = WhisperModel("large-v3", device="cuda", compute_type="float16")
files = sorted(glob.glob(str(ROOT / "data/voice/*.m4a")))
print("files", len(files), flush=True)
for i, f in enumerate(files, 1):
    dst = OUT / (Path(f).stem + ".txt")
    if dst.exists():
        continue
    t0 = time.time()
    segs, info = wm.transcribe(f, language="ko", vad_filter=True, beam_size=5)
    dst.write_text("\n".join(s.text.strip() for s in segs), encoding="utf-8")
    print(f"[{i}/{len(files)}] {dst.name} {info.duration:.0f}s -> {time.time() - t0:.0f}s", flush=True)
print("STT_DONE", flush=True)
