"""data/derived/unified.jsonl (data/build_unified.py 가 생성)을 학습용 train/val/test + 외부 평가셋으로 나눈다.

출력: model/out/{train,val,test,ext_test}.jsonl  (text, label: 0=일반, 1=스미싱/스팸)
- Korean_message: class 1 -> 0, class 2 -> 1, class 3(택배 템플릿)은 라벨 없음이라 제외 (build_unified.py 참고)
- 정확히 같은 문자열은 하나만 남긴다.
- 숫자를 0으로 바꾼 뒤 끝 30자가 같은 문자는 한 그룹으로 묶어 같은 분할에 넣는다
  (class 3 처럼 이름만 바뀐 템플릿이 train/test 에 갈라져 점수가 부풀려지는 것을 막는다).
- KR-MOB-SMISHING-v2 합성 사례는 사건(incident) 단위로 train 50% / val 20% / ext_test 30% 로 나눈다.
  같은 사건의 문자가 여러 분할에 걸리지 않게 하고, train 몫은 SYN_REPEAT 배 반복해 비중을 키운다.
  (실제 문자의 정상 문자는 일상 대화체뿐이라, 공지체 정상 문자를 배울 근거가 합성 사례뿐이다.)
- 통화(channel=voice)는 금감원 보이스피싱 창(fss_voice, 통화 단위)과 KsponSpeech 정상 통화(kspon_speech)를
  각각 50/20/30 으로 나눠 train/val/voice_test 에 넣는다. 한쪽만 학습에 들어가 통화체가 라벨의 지름길이 되는 것을 막는다.
- 그 밖의 출처는 전부 ext_test 로 둔다.
"""
import json, sys
from pathlib import Path
from sklearn.model_selection import GroupShuffleSplit

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "out"
SEED = 42
SYN_REPEAT = 10
SYN = "kr_mob_smishing_v2"
LABEL = {"1": 0, "2": 1, "3": 1}


sys.path.insert(0, str(ROOT / "data"))
from build_unified import URL_RE, domain_kind  # noqa: E402
import build_unified  # noqa: E402


def tokenize_urls(text):
    """링크를 [URL_종류] 토큰으로 바꾼다. 모델이 도메인 문자열을 외우지 않고 종류로 판단하게 한다."""
    return URL_RE.sub(lambda m: f"[URL_{domain_kind(m.group(1))}]", text)


def load_unified():
    if not (ROOT / "data/derived/unified.jsonl").exists():
        build_unified.main()  # 통합 파일이 없으면 원본에서 만든다
    rows = [json.loads(l) for l in open(ROOT / "data/derived/unified.jsonl", encoding="utf-8")]
    for r in rows:
        r["text_tok"] = tokenize_urls(r["text"])
    return rows


def dump(name, rows):
    with open(OUT / f"{name}.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    pos = sum(r["label"] for r in rows)
    print(f"{name}: {len(rows)} (스미싱 {pos}, 일반 {len(rows) - pos})")


def split_synthetic(rows):
    """사건 단위 분할. benign / benign_lookalike / malicious 각각에서 50/20/30 으로 나눈다."""
    import random
    by_type = {}
    for r in rows:
        inc, case = r["orig_id"].split("#")[0], r["orig_id"].split(":")[-1]
        by_type.setdefault(case, {}).setdefault(inc, []).append(r)
    rng = random.Random(SEED)
    parts = {"train": [], "val": [], "test": []}
    for case, incs in sorted(by_type.items()):
        ids = sorted(incs)
        rng.shuffle(ids)
        n = len(ids)
        cut = {"train": ids[: round(n * 0.5)], "val": ids[round(n * 0.5): round(n * 0.7)], "test": ids[round(n * 0.7):]}
        for k, v in cut.items():
            for i in v:
                parts[k] += incs[i]
    return parts


VOICE = ("fss_voice", "kspon_speech")


def split_voice(rows):
    """통화 단위(fss_voice: 파일, kspon_speech: 각 행) 50/20/30 분할."""
    import random
    units = {}
    for r in rows:
        key = r["orig_id"].split("#")[0] if r["source"] == "fss_voice" else r["orig_id"]
        units.setdefault(key, []).append(r)
    ids = sorted(units)
    random.Random(SEED).shuffle(ids)
    n = len(ids)
    cut = {"train": ids[: round(n * 0.5)], "val": ids[round(n * 0.5): round(n * 0.7)], "test": ids[round(n * 0.7):]}
    return {k: [r for i in v for r in units[i]] for k, v in cut.items()}


def main():
    OUT.mkdir(exist_ok=True)
    allrows = load_unified()
    rows = [r for r in allrows if r["source"] == "korean_message" and r["label"] is not None]  # 라벨이 확정된 실제 문자
    groups = [r["group_id"] for r in rows]
    gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=SEED)
    tr_idx, rest_idx = next(gss.split(rows, groups=groups))
    rest = [rows[i] for i in rest_idx]
    rg = [groups[i] for i in rest_idx]
    v_idx, t_idx = next(GroupShuffleSplit(n_splits=1, test_size=0.5, random_state=SEED).split(rest, groups=rg))
    syn = split_synthetic([r for r in allrows if r["source"] == SYN])
    voice = {k: split_voice([r for r in allrows if r["source"] == k]) for k in VOICE}
    vp = {p: [r for k in VOICE for r in voice[k][p]] for p in ("train", "val", "test")}
    dump("train", [rows[i] for i in tr_idx] + syn["train"] * SYN_REPEAT + vp["train"])
    dump("val", [rest[i] for i in v_idx] + syn["val"] + vp["val"])
    dump("voice_test", vp["test"])  # 통화 평가(금감원 사기 창 + 정상 통화)
    dump("test", [rest[i] for i in t_idx])  # 같은 출처 실제 문자(참고용, 쉬운 평가)
    # 외부 평가셋: 학습에 쓰지 않은 합성 사건 + 그 밖의 출처(음성 전사본)
    dump("ext_test", syn["test"] + [r for r in allrows if r["source"] not in ("korean_message", SYN, *VOICE)])


if __name__ == "__main__":
    sys.exit(main())
