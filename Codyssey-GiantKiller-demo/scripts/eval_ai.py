"""판단 방식 비교 (C안) — 같은 시험지로 '키워드 규칙 / 작은 모델 / LLM / 규칙+LLM' 을 재서 PPT 표로.

    python scripts/eval_ai.py                                   # 기본 시험지(ai/data/testset.jsonl), 규칙(+작은 모델)만
    python scripts/eval_ai.py --engines rule,llm,hybrid --delay 5   # LLM 까지 (게이트웨이 호출 — 문자 수 × 2회)
    python scripts/eval_ai.py --file data/splits/test.jsonl     # 나눠 둔 평가 파일 (실제 문자만)
    python scripts/eval_ai.py --file smishing100.csv --file normal.txt:safe --engines rule,llm
    python scripts/eval_ai.py --file data/splits/test.jsonl --train data/splits/train.jsonl   # 겹침 검사

방식
- rule   : 키워드 규칙 (ai/rules.py)
- model  : 작은 분류 모델 (CLASSIFIER_DIR 설정 시) — 위험/정상 두 가지만
- llm    : LLM 단독 (규칙 안전망 없이)
- hybrid : 지금 서버 구조 = LLM + 규칙 안전망 (ai.analyze)

함께 재는 것: 폰 1차 필터 — 평범한 문자 중 몇 %가 폰 밖으로 안 나갔나 (개인정보 보호 효과)

⚠️ ai/data/testset.jsonl 은 규칙을 다듬으며 직접 쓴 예시라 rule 점수가 부풀려져 있다.
   발표용 숫자는 처음 보는 실제 문자(split_data.py 로 나눈 test)로만 잴 것.
"""
import argparse
import csv
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ai import analyze, classifier, llm, mask_text, rules  # noqa: E402
from ai.dataset import DANGER, load, text_key  # noqa: E402
from ai.prefilter import prefilter  # noqa: E402
from ai.privacy import sender_kind  # noqa: E402
from ai.prompts import SYSTEM, user_prompt  # noqa: E402
from ai.schema import SchemaError, normalize  # noqa: E402

# 시험 문자의 '저장된 번호' (예전 시연 가족 연락처: 아들·경로당·동생) — testset.jsonl 이 이 번호를 쓴다
KNOWN_PHONES = {"010-1234-5678", "010-2222-3333", "010-5555-6666"}

LABEL = {"rule": "키워드 규칙", "light": "가벼운 모델 (폰 안)", "model": "작은 모델 (BERT)", "llm": "LLM 단독",
         "hybrid": "규칙 + LLM (지금 구조)"}
WHERE = {"rule": "없음 (폰·서버 안)", "light": "없음 (폰 안)", "model": "없음 (GPU 서버)", "llm": "가린 내용만",
         "hybrid": "가린 내용만"}
LIGHT_PATHS = [ROOT / "models" / "light" / "light_model.bin",
               ROOT / "android" / "app" / "src" / "main" / "assets" / "light_model.bin"]


def light():
    """가벼운 1차 모델 (scripts/train_light.py). 없으면 None"""
    from ai.light_model import LightModel
    path = next((p for p in LIGHT_PATHS if p.exists()), None)
    return LightModel.load(path) if path else None


USE_SENDER = True  # --no-sender 면 내용만 보고 판단 (번호 종류 없이)


def ctx_for(row):
    return {"child_relation": "자녀분", "sender_is_child": False, "sender_known": row["known"], "previous_calls": [],
            "sender_kind": sender_kind(row.get("sender", "")) if USE_SENDER else "unknown"}


def run_llm(item, ctx, retries=3):
    for i in range(retries):
        try:
            raw, _ = llm.complete_json(SYSTEM, user_prompt(item, ctx))
            return normalize(raw, item["event_id"])["category"]
        except llm.LLMError as e:
            if "429" in str(e) and i < retries - 1:  # 무료 등급 속도 제한 → 기다렸다 다시
                time.sleep(15 * (i + 1))
                continue
            return "error"
        except SchemaError:
            return "error"
    return "error"


def evaluate(engine, rows, delay):
    preds, times = [], []
    if engine == "light":
        m = light()
        t0 = time.time()
        preds = ["scam" if m.is_scam(r["text"]) else "safe" for r in rows]
        return preds, [(time.time() - t0) * 1000 / max(len(rows), 1)] * len(rows)
    if engine == "model":  # 한 번에 묶어서
        t0 = time.time()
        scores = classifier.danger_scores([mask_text(r["text"]) for r in rows])
        per = (time.time() - t0) * 1000 / max(len(rows), 1)
        return ["scam" if s >= classifier.threshold() else "safe" for s in scores], [per] * len(rows)
    for i, r in enumerate(rows):
        item = {"event_id": f"t{i}", "type": "message", "sender": "", "content": mask_text(r["text"])}
        t0 = time.time()
        if engine == "rule":
            p = rules.analyze(item, ctx_for(r))["category"]
        elif engine == "llm":
            p = run_llm(item, ctx_for(r))
        else:
            p = analyze(item, ctx_for(r))["category"]
        times.append((time.time() - t0) * 1000)
        preds.append(p)
        if engine in ("llm", "hybrid") and delay:
            time.sleep(delay)
        if engine in ("llm", "hybrid") and (i + 1) % 20 == 0:
            print(f"  {LABEL[engine]} {i + 1}/{len(rows)}", file=sys.stderr)
    return preds, times


def metrics(rows, preds, times, binary_only):
    y = [r["expect"] in DANGER for r in rows]
    p = [x in DANGER for x in preds]
    tp = sum(a and b for a, b in zip(y, p))
    pos, neg = sum(y), len(y) - sum(y)
    fp = sum((not a) and b for a, b in zip(y, p))
    exact = sum(r["expect"] == x for r, x in zip(rows, preds))
    return {
        "recall": tp / pos if pos else None,
        "false_alarm": fp / neg if neg else None,
        "acc4": None if binary_only else exact / len(rows),
        "ms": sorted(times)[len(times) // 2] if times else 0,
        "errors": sum(x == "error" for x in preds),
    }


def pct(v):
    return "-" if v is None else f"{v:.0%}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", action="append", help="시험지 (여러 번 가능, 경로:정답 형식 가능)")
    ap.add_argument("--engines", default="auto",
                    help="rule,model,llm,hybrid 중 고르기. 기본은 규칙(+작은 모델)만 — LLM 은 무료 한도를 쓰므로 직접 지정할 때만")
    ap.add_argument("--train", help="학습 파일 — 시험지와 겹치는 문자가 있으면 멈춘다")
    ap.add_argument("--delay", type=float, default=float(os.getenv("EVAL_LLM_DELAY", "0")),
                    help="LLM 요청 사이 쉬는 초 (게이트웨이 속도 제한이 있으면 4~6)")
    ap.add_argument("--out", default=str(ROOT / "data" / "eval"), help="결과 표(.md)·틀린 문자(.csv) 저장 폴더")
    ap.add_argument("--rule", action="store_true", help="(예전 옵션) --engines rule 과 같음")
    ap.add_argument("--no-sender", action="store_true", help="보낸 번호 종류 없이 내용만 보고 판단")
    a = ap.parse_args()
    global USE_SENDER
    USE_SENDER = not a.no_sender

    files = a.file or [str(ROOT / "ai" / "data" / "testset.jsonl")]
    known = KNOWN_PHONES
    rows = [r for f in files for r in load(f, known)]
    if a.train:
        overlap = {text_key(r["text"]) for r in load(a.train)} & {text_key(r["text"]) for r in rows}
        if overlap:
            sys.exit(f"❌ 시험지 문자 {len(overlap)}개가 학습 파일에도 있어요. 이 점수는 믿을 수 없어요.")

    if a.rule:
        engines = ["rule"]
    elif a.engines == "auto":
        engines = ["rule"] + (["light"] if light() else []) + (["model"] if classifier.available() else [])
    else:
        engines = [e.strip() for e in a.engines.split(",")]
    if "model" in engines and not classifier.available():
        sys.exit("❌ 작은 모델: .env 에 CLASSIFIER_DIR 를 넣어 주세요 (scripts/train_classifier.py)")
    n_calls = len(rows) * len({"llm", "hybrid"} & set(engines))
    if n_calls:
        if llm.provider() == "rule":
            sys.exit("❌ LLM: .env 에 CODY_CLAUDE_KEY(또는 CODY_GPT_KEY) 나 OPENAI_BASE_URL 을 넣어 주세요")
        print(f"⚠️ LLM 호출 약 {n_calls}회 (무료 한도 사용)")

    binary_only = all(r["expect"] in ("scam", "safe") for r in rows)  # 위험/정상 두 가지만 있는 시험지
    n_d = sum(r["expect"] in DANGER for r in rows)
    print(f"시험지 {len(rows)}개 (위험 {n_d} / 정상·안내 {len(rows) - n_d}) · 파일: {', '.join(Path(f.split(':')[0]).name for f in files)}")
    if any("testset.jsonl" in f for f in files):
        print("⚠️ 기본 시험지는 규칙을 다듬으며 쓴 예시 → 키워드 규칙 점수가 부풀려져 있음. 발표용 아님")
    print(f"LLM: {llm.provider()} · 보낸 번호 종류: {'사용' if USE_SENDER else '안 씀 (내용만)'}\n")

    results, misses = {}, []
    for e in engines:
        preds, times = evaluate(e, rows, a.delay)
        results[e] = metrics(rows, preds, times, binary_only or e in ("model", "light"))
        misses += [(LABEL[e], r["expect"], p, r["text"]) for r, p in zip(rows, preds)
                   if (r["expect"] in DANGER) != (p in DANGER) or p == "error"]

    # 폰 1차 필터: 규칙만 / 규칙 + 가벼운 모델
    def gate_line(name, model):
        sent = [prefilter(r["text"], r["known"], model)[0] for r in rows]
        d_sent = sum(s for s, r in zip(sent, rows) if r["expect"] in DANGER)
        benign = [s for s, r in zip(sent, rows) if r["expect"] not in DANGER]
        kept = sum(not s for s in benign)
        return (f"폰 1차 필터 ({name}): 위험 문자 {d_sent}/{n_d} 서버로 보냄 · 평범·안내 문자 {kept}/{len(benign)}"
                f" ({kept / max(len(benign), 1):.0%}) 는 폰 밖으로 안 나감")

    lines = ["| 방식 | 위험 잡은 비율 | 정상 잘못 막은 비율 | 4가지 분류 정확도 | 1건 처리 (중앙값) | 외부 전송 |",
             "|---|---|---|---|---|---|"]
    for e, m in results.items():
        err = f" (오류 {m['errors']})" if m["errors"] else ""
        lines.append(f"| {LABEL[e]} | {pct(m['recall'])}{err} | {pct(m['false_alarm'])} | {pct(m['acc4'])} | "
                     f"{m['ms']:.0f}ms | {WHERE[e]} |")
    lm = light()
    gate = gate_line("규칙만", None) + (("\n" + gate_line(f"규칙 + 가벼운 모델 기준 {lm.gate:.2f}", lm)) if lm else "")
    table = "\n".join(lines)
    print(table + "\n\n" + gate)

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    head = f"시험지: {', '.join(files)} ({len(rows)}개) · 보낸 번호 종류 {'사용' if USE_SENDER else '안 씀'}"
    (out / "result.md").write_text(f"{head}\n\n{table}\n\n{gate}\n", encoding="utf-8")
    with (out / "misses.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["방식", "정답", "판단", "문자"])
        w.writerows(misses)
    print(f"\n저장: {out / 'result.md'} · 틀린 문자 {len(misses)}개 → {out / 'misses.csv'}")


if __name__ == "__main__":
    main()
