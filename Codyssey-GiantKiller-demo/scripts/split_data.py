"""학습/평가 나누기. 평가에 쓸 실제 문자가 학습에 절대 섞이지 않게.

    # 실제 스미싱 100 + 평범한 문자 → 반은 학습, 반은 평가 (위험/정상 비율 유지)
    python scripts/split_data.py smishing100.csv normal.txt:safe --test-ratio 0.5

    # AI 가 만든 문자는 학습에만 (평가에는 절대 안 들어감)
    python scripts/split_data.py smishing100.csv normal.txt:safe --train-only generated.jsonl

    # 데이터가 적을 때: 5번 나눠 돌리기 (교차검증) → data/splits/fold1..5/
    python scripts/split_data.py smishing100.csv normal.txt:safe --folds 5

결과는 data/splits/ (저장소에 안 올라감 — 외부 데이터 라이선스 보호)
"""
import argparse
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ai.dataset import DANGER, dedup, load, save_jsonl, text_key  # noqa: E402


def summary(name, rows):
    d = sum(r["expect"] in DANGER for r in rows)
    return f"{name}: {len(rows)}개 (위험 {d} / 정상·안내 {len(rows) - d})"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+", help="실제 문자 파일들 (경로 또는 경로:정답)")
    ap.add_argument("--train-only", nargs="*", default=[], help="학습에만 넣을 파일 (AI 생성 문자 등)")
    ap.add_argument("--test-ratio", type=float, default=0.5)
    ap.add_argument("--folds", type=int, default=0)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default=str(ROOT / "data" / "splits"))
    a = ap.parse_args()

    real = dedup([r for spec in a.inputs for r in load(spec)])
    extra = [r for spec in a.train_only for r in load(spec)]
    real_keys = {text_key(r["text"]) for r in real}
    extra = [r for r in dedup(extra) if text_key(r["text"]) not in real_keys]  # 실제 문자와 같은 생성 문자는 버림
    print(summary("실제 문자", real))
    if extra:
        print(summary("학습 전용(생성)", extra))

    rng = random.Random(a.seed)
    danger = [r for r in real if r["expect"] in DANGER]
    benign = [r for r in real if r["expect"] not in DANGER]
    rng.shuffle(danger)
    rng.shuffle(benign)
    out = Path(a.out)

    if a.folds:
        for k in range(a.folds):
            test = danger[k::a.folds] + benign[k::a.folds]
            keys = {text_key(r["text"]) for r in test}
            train = [r for r in real if text_key(r["text"]) not in keys] + extra
            save_jsonl(train, out / f"fold{k + 1}" / "train.jsonl")
            save_jsonl(test, out / f"fold{k + 1}" / "test.jsonl")
            print(f"fold{k + 1} → " + summary("학습", train) + " · " + summary("평가", test))
    else:
        nd, nb = round(len(danger) * a.test_ratio), round(len(benign) * a.test_ratio)
        test = danger[:nd] + benign[:nb]
        train = danger[nd:] + benign[nb:] + extra
        save_jsonl(train, out / "train.jsonl")
        save_jsonl(test, out / "test.jsonl")
        print(summary("학습", train) + f"  → {out / 'train.jsonl'}")
        print(summary("평가", test) + f"  → {out / 'test.jsonl'}")


if __name__ == "__main__":
    main()
