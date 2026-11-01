"""가벼운 1차 모델 학습 (이 맥 CPU에서 수십 초, 설치 불필요).

    python scripts/import_korean_message.py                      # 라벨 반대(1=정상, 2=사기) 처리된 jsonl
    python scripts/split_data.py data/sets/korean_message.jsonl --test-ratio 0.1
    python scripts/train_light.py                                # → models/light/light_model.bin (+ 안드로이드 assets 복사)
    python scripts/eval_ai.py --engines rule,light --file data/splits/test.jsonl

- 위험(사기·사칭)=1 / 정상·안내=0. class 3(진짜 배송 안내)은 0 — 택배 사칭과 생김새가 비슷한 좋은 오답 연습
- 학습 파일의 10% 를 떼어 1차 통과 기준(gate)을 정한다: 떼어 둔 위험 문자의 GATE_RECALL 이상이 통과하는 가장 높은 점수
- 평가 파일(test.jsonl)은 학습·기준 정하기 어디에도 쓰지 않는다
- 고정 예시(tests/data/light_examples.json)를 다시 만든다 → 파이썬·안드로이드 일치 테스트에 쓰임
"""
import argparse
import base64
import json
import random
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ai.dataset import DANGER, text_key  # noqa: E402
from ai.light_model import quantize, train  # noqa: E402

ASSET = ROOT / "android" / "app" / "src" / "main" / "assets" / "light_model.bin"
EXAMPLES = ROOT / "tests" / "data" / "light_examples.json"
GATE_MAX = 0.3  # 1차 통과 기준 상한: 실제 문자는 학습 데이터보다 어려우니 낮게 (애매하면 서버로)
EXAMPLE_TEXTS = [
    "[국제택배] 주소지 불일치로 배송 보류. 확인: http://kr-post-check.xyz/a1",
    "엄마 나 폰 액정 깨져서 수리 맡겼어. 이 번호로 문자줘",
    "[행복아파트] 10월 관리비 245,300원이 자동이체될 예정입니다.",
    "내일 아침 10시에 노래교실 있어요. 늦지 말고 와요~",
    "⚜️빅토리카지노⚜️신규보너스 vtⓡ⑦*⑦.com",
    "고객님 저금리 대환대출 승인되셨습니다. 상담 문의 바랍니다",
    "엄마 저녁 먹었어? 이번 주말에 갈게",
    "[Web발신] 인증번호 [482913]를 입력해주세요.",
    "  Hello\tWORLD 123  ",
    "😀 이모지와 한글 ABC",
    "",
    "가",
]


def read(path):
    rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    return [r["text"] for r in rows], [int(r["expect"] in DANGER) for r in rows]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", default=str(ROOT / "data" / "splits" / "train.jsonl"))
    ap.add_argument("--test", default=str(ROOT / "data" / "splits" / "test.jsonl"))
    ap.add_argument("--out", default=str(ROOT / "models" / "light" / "light_model.bin"))
    ap.add_argument("--epochs", type=int, default=6)
    ap.add_argument("--gate-recall", type=float, default=0.99, help="1차 통과 기준: 떼어 둔 위험 문자 중 이 비율 이상 통과")
    ap.add_argument("--no-asset", action="store_true", help="안드로이드 assets 로 복사하지 않음")
    a = ap.parse_args()

    xs, ys = read(a.train)
    test_keys = {text_key(t) for t in read(a.test)[0]} if Path(a.test).exists() else set()
    if any(text_key(x) in test_keys for x in xs):
        sys.exit("❌ 평가 문자가 학습 파일에 섞여 있어요. split_data.py 로 다시 나눠 주세요.")

    # 기준 정하기용 10% 떼기 (위험/정상 비율 유지)
    rng = random.Random(42)
    pos = [i for i, y in enumerate(ys) if y]
    neg = [i for i, y in enumerate(ys) if not y]
    rng.shuffle(pos)
    rng.shuffle(neg)
    val = set(pos[: len(pos) // 10] + neg[: len(neg) // 10])
    tr = [i for i in range(len(xs)) if i not in val]
    print(f"학습 {len(tr)}개 · 기준 정하기 {len(val)}개 (위험 {len(pos)} / 정상 {len(neg)})")

    t0 = time.time()
    w, b = train([xs[i] for i in tr], [ys[i] for i in tr], epochs=a.epochs)
    print(f"학습 {time.time() - t0:.1f}초")
    model = quantize(w, b)

    vp = sorted(model.score(xs[i]) for i in val if ys[i])
    gate = vp[max(0, int(len(vp) * (1 - a.gate_recall)) - 1)] if vp else 0.2
    model = quantize(w, b, gate=min(gate, GATE_MAX))
    vn = [model.score(xs[i]) for i in val if not ys[i]]
    print(f"1차 통과 기준(gate) {model.gate:.3f}: 떼어 둔 위험 {sum(s >= model.gate for s in vp)}/{len(vp)} 통과, "
          f"정상 {sum(s < model.gate for s in vn)}/{len(vn)} 폰에 남음")

    model.save(a.out)
    print(f"저장: {a.out} ({Path(a.out).stat().st_size / 1024:.0f}KB)")
    if not a.no_asset:
        ASSET.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(a.out, ASSET)
        print(f"안드로이드 assets: {ASSET}")
    EXAMPLES.parent.mkdir(parents=True, exist_ok=True)
    EXAMPLES.write_text(json.dumps([{"text": t, "score": model.score(t)} for t in EXAMPLE_TEXTS],
                                   ensure_ascii=False, indent=1), encoding="utf-8")
    # 안드로이드 단위 테스트용 (JSON 라이브러리 없이 읽게): 점수<TAB>base64(UTF-8 글)
    EXAMPLES.with_suffix(".tsv").write_text("".join(
        f"{model.score(t)!r}\t{base64.b64encode(t.encode()).decode()}\n" for t in EXAMPLE_TEXTS), encoding="utf-8")
    print(f"고정 예시 {len(EXAMPLE_TEXTS)}개: {EXAMPLES} (+ .tsv)")


if __name__ == "__main__":
    main()
