"""허깅페이스 meal-bbang/Korean_message (19,009행, 라이선스 표기 없음) → 학습·평가용 jsonl.

    mkdir -p data/raw/korean_message
    curl -L -o data/raw/korean_message/lgaidataset.csv \
      https://huggingface.co/datasets/meal-bbang/Korean_message/resolve/main/lgaidataset.csv
    python scripts/import_korean_message.py          # → data/sets/korean_message.jsonl

⚠️ 라벨이 우리와 반대다: README 기준 1 = 일상 문자, 2 = 피싱·스미싱. (ai/dataset.py 기본 규칙은 "1"=사기라 그대로 넣으면 뒤집힌다)
⚠️ class 3 (2,700행) 은 README 에 설명이 없다. 내용은 쿠팡·CJ·한진·롯데택배 등 **진짜 배송 안내 틀에 가짜 이름만 바꾼 문자**(틀 44종)
   → '정상 안내'(need_explain)로 넣는다. 택배 사칭과 생김새가 비슷해 오탐을 재기 좋다. 빼려면 --drop-class3
- class 1 은 일상 대화(링크 0%), class 2 에는 도박·카지노 광고도 섞여 있다
- 라이선스·출처 표기가 없다 → 학습에만 쓰고 재배포하지 않는다, 발표에 출처 표기 (data/ 는 gitignore)
"""
import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ai.dataset import dedup, save_jsonl  # noqa: E402

LABEL = {"1": "safe", "2": "scam", "3": "need_explain"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src", nargs="?", default=str(ROOT / "data" / "raw" / "korean_message" / "lgaidataset.csv"))
    ap.add_argument("--out", default=str(ROOT / "data" / "sets" / "korean_message.jsonl"))
    ap.add_argument("--drop-class3", action="store_true")
    a = ap.parse_args()

    rows, skipped = [], Counter()
    with open(a.src, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            cls, text = r["class"].strip(), r["content"].strip()
            if cls not in LABEL or (cls == "3" and a.drop_class3) or not text:
                skipped[cls] += 1
                continue
            rows.append({"text": text, "expect": LABEL[cls], "known": False, "src": "Korean_message", "orig_class": cls})
    before = len(rows)
    rows = dedup(rows)
    save_jsonl(rows, Path(a.out))
    print(f"{before}행 → 중복 빼고 {len(rows)}개 → {a.out}" + (f" (건너뜀 {dict(skipped)})" if skipped else ""))
    for (cls, label), n in sorted(Counter((r["orig_class"], r["expect"]) for r in rows).items()):
        print(f"  class {cls} → {label:<12} {n}")


if __name__ == "__main__":
    main()
