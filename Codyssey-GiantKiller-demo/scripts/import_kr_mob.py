"""KR-MOB-SMISHING v1 (합성 데이터, CC BY-NC 4.0) → 평가용 jsonl.

    unzip KR-MOB-SMISHING-100-v1.zip -d data/raw
    python scripts/import_kr_mob.py data/raw/KR-MOB-SMISHING-100-v1      # → data/sets/kr_mob_smishing_v1.jsonl
    python scripts/eval_ai.py --file data/sets/kr_mob_smishing_v1.jsonl

정답은 '사건 결과'가 아니라 '문자 내용' 기준으로 매긴다.
- malicious        (킬체인 완성)           → scam
- benign_lookalike (공격 문자, 사용자 중단) → scam   ← 문자 자체는 공격이므로
- benign           (공식 번호의 정상 안내)  → safe   ← 사기와 생김새가 비슷한 '헷갈리는 정상'
모든 문자 앞의 [TRAINING] 표시는 뗀다 (LLM 이 훈련용이라고 눈치채지 않게).
출처 표기: KR-MOB-SMISHING v1, CC BY-NC 4.0 (비상업). 원본·변환본 모두 저장소에 올리지 않는다 (data/ 는 gitignore).
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ai.dataset import dedup, save_jsonl  # noqa: E402

LABEL = {"malicious": "scam", "benign_lookalike": "scam", "benign": "safe"}
# 데이터의 발신자 종류 → 대표 번호 (번호 '종류'만 판단에 쓰므로 실제 번호는 필요 없다)
SENDER = {"verified_sender": "1588-0000", "personal_number": "010-0000-0000", "short_code": "#1004"}


def main():
    src = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "data" / "raw" / "KR-MOB-SMISHING-100-v1")
    out = Path(sys.argv[2] if len(sys.argv) > 2 else ROOT / "data" / "sets" / "kr_mob_smishing_v1.jsonl")
    rows = []
    for f in sorted((src / "incidents").glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        for m in d.get("message_samples_used", []):
            text = re.sub(r"^\s*\[TRAINING\]\s*", "", m.get("text", "")).strip()
            if not text or m.get("delivery_channel", "SMS") != "SMS":
                continue
            rows.append({"text": text, "expect": LABEL[d["case_type"]], "known": False, "src": "KR-MOB-SMISHING-v1",
                         "sender": SENDER.get(m.get("sender_type"), ""),
                         "incident_id": d["incident_id"], "case_type": d["case_type"], "theme": d.get("theme"),
                         "sender_type": m.get("sender_type"), "difficulty": d.get("difficulty_tier")})
    before = len(rows)
    rows = dedup(rows)
    save_jsonl(rows, out)
    c = Counter((r["case_type"], r["expect"]) for r in rows)
    print(f"문자 {before}개 → 중복 빼고 {len(rows)}개 → {out}")
    for (case, label), n in sorted(c.items()):
        print(f"  {case:<17} → {label:<5} {n}")


if __name__ == "__main__":
    main()
