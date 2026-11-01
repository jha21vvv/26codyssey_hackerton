"""KsponSpeech 전사(.trn)로 '정상 통화' 텍스트를 만든다. 서버에서 실행한다.

사용: python build_normal_calls.py <train.trn> [--n 3000] [--min_chars 200]
출력: derived/normal_calls.jsonl  (text, label=0, orig_id)
- 전사 표기(b/ o/ n/ l/ u/ + * 잡음 태그)를 걷어내고, (철자)/(발음) 중 철자를 쓴다.
- 같은 녹음 폴더에서 연속된 발화를 이어 붙여 통화 한 토막(min_chars 이상)으로 만든다.
"""
import argparse, json, random, re
from pathlib import Path

D = Path(__file__).resolve().parent
TAG = re.compile(r"(?<!\S)[bonlu]/(?=\s|$)")
PAIR = re.compile(r"\(([^()]*)\)/\(([^()]*)\)")
NOISE = re.compile(r"&[^&\s]*&|@\S+|[*+]")


def clean(t):
    t = PAIR.sub(lambda m: m.group(1), t)
    t = TAG.sub(" ", t)
    t = NOISE.sub("", t)
    return re.sub(r"\s+", " ", t).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("trn")
    ap.add_argument("--n", type=int, default=3000)
    ap.add_argument("--min_chars", type=int, default=200)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()

    by_dir = {}
    for line in open(a.trn, encoding="utf-8"):
        if " :: " not in line:
            continue
        path, text = line.rstrip("\r\n").split(" :: ", 1)
        by_dir.setdefault(path.rsplit("/", 1)[0], []).append((path, clean(text)))

    chunks = []
    for d, utts in sorted(by_dir.items()):
        utts.sort()
        buf, first = [], None
        for path, t in utts:
            if not t:
                continue
            first = first or path
            buf.append(t)
            if sum(len(x) for x in buf) >= a.min_chars:
                chunks.append((first.rsplit("/", 1)[-1].replace(".pcm", ""), " ".join(buf)))
                buf, first = [], None
    rng = random.Random(a.seed)
    rng.shuffle(chunks)
    out = D / "derived" / "normal_calls.jsonl"
    out.parent.mkdir(exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        for oid, text in chunks[: a.n]:
            f.write(json.dumps({"text": text, "label": 0, "orig_id": oid}, ensure_ascii=False) + "\n")
    print(f"후보 {len(chunks)}개 중 {min(a.n, len(chunks))}개 저장: {out}")


if __name__ == "__main__":
    main()
