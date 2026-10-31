"""통화 전사본을 학습된 문자 분류기로 판별한다.
전사본을 CHUNK 자 창(STRIDE 간격)으로 잘라 창마다 스미싱 확률을 구하고,
전사본 단위로 최대 확률과 스미싱 판정 창 비율을 낸다.
금감원 자료는 전부 보이스피싱 사례라 정답은 모두 '스미싱(1)' 이고, 재현율만 계산할 수 있다.
사용: python eval_voice.py <전사본 폴더> <모델 폴더> [<모델 폴더> ...]
"""
import json, sys
from pathlib import Path
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prepare_data import tokenize_urls  # noqa: E402

CHUNK, STRIDE = 200, 100
dev = "cuda" if torch.cuda.is_available() else "cpu"


def windows(text):
    text = " ".join(text.split())
    if len(text) <= CHUNK:
        return [text] if text else []
    return [text[i:i + CHUNK] for i in range(0, len(text) - CHUNK // 2, STRIDE)]


@torch.no_grad()
def run(model_dir, files):
    tok = AutoTokenizer.from_pretrained(model_dir)
    model = AutoModelForSequenceClassification.from_pretrained(model_dir).to(dev).eval()
    res = {}
    for f in files:
        ws = [tokenize_urls(w) for w in windows(f.read_text(encoding="utf-8"))]
        if not ws:
            res[f.stem] = None
            continue
        enc = tok(ws, truncation=True, max_length=128, padding=True, return_tensors="pt").to(dev)
        p = model(**enc).logits.softmax(-1)[:, 1].cpu().tolist()
        res[f.stem] = {"n": len(p), "max": max(p), "frac": sum(x > 0.5 for x in p) / len(p)}
    return res


def main():
    files = sorted(Path(sys.argv[1]).glob("*.txt"))
    summary = {}
    for md in sys.argv[2:]:
        r = run(md, files)
        ok = {k: v for k, v in r.items() if v}
        n = len(ok)
        s = {
            "files": n, "empty": len(r) - n,
            "recall_any_window": sum(v["max"] > 0.5 for v in ok.values()) / n,
            "recall_frac_ge_30pct": sum(v["frac"] >= 0.3 for v in ok.values()) / n,
            "mean_window_flag_frac": sum(v["frac"] for v in ok.values()) / n,
        }
        summary[Path(md).name] = {"summary": s, "per_file": r}
        print(Path(md).name, json.dumps(s, ensure_ascii=False), flush=True)
    out = Path(sys.argv[1]).parent / f"voice_eval_{Path(sys.argv[1]).name}.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", out)


if __name__ == "__main__":
    main()
