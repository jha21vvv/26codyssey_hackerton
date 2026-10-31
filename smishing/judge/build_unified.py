"""data/ 의 외부 데이터를 하나의 스키마(jsonl)로 통일한다. 원본은 수정하지 않는다.

출력: data/derived/unified.jsonl
스키마: text, domain_type, label(0=일반 1=스미싱/스팸 null=라벨 불확실, 학습 제외), source, channel, origin, group_id, orig_id, license
입력:
  - Korean_message/lgaidataset.csv         (class 1->0, 2->1, 3->조건부: 낯선 도메인 링크가 있으면 1, 아니면 라벨 없음)
  - KR-MOB-SMISHING-v2/incidents/*.json    (malicious->1, benign/benign_lookalike->0)
  - derived/voice_transcripts.jsonl        (있을 때만. 필드: text,label,orig_id)
  - derived/normal_calls.jsonl             (있을 때만. build_normal_calls.py 산출)
"""
import csv, glob, json, re
from pathlib import Path

D = Path(__file__).resolve().parent
OUT = D / "derived" / "unified.jsonl"
LIC = {"korean_message": "unspecified", "kr_mob_smishing_v2": "CC-BY-NC-4.0", "fss_voice": "unverified", "kspon_speech": "aihub-terms"}


SHORTENERS = {"bit.ly", "me2.do", "url.kr", "han.gl", "vo.la", "t.ly", "tinyurl.com", "is.gd", "naver.me", "buly.kr"}
BRANDS = {"coupang.com", "naver.com", "kakao.com", "toss.im", "tosspayments.com", "post.go.kr", "epost.go.kr",
          "musinsa.com", "11st.co.kr", "gmarket.co.kr", "auction.co.kr", "kbstar.com", "shinhan.com",
          "wooribank.com", "hanabank.com", "nonghyup.com", "ebay.com"}  # 필요하면 추가한다
URL_RE = re.compile(r"(?:https?://)?((?:[\w-]+\.)+[a-z]{2,})(?:/\S*)?", re.I)  # 날짜(23.02.22)는 TLD 가 숫자라 걸리지 않는다
PRIORITY = ["lookalike", "unknown", "short", "brand"]


def edit_distance(a, b):
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[-1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def domain_kind(dom):
    dom = dom.lower().strip(".")
    if dom in SHORTENERS:
        return "short"
    if dom in BRANDS or any(dom.endswith("." + b) for b in BRANDS):
        return "brand"
    if not dom.isascii():
        return "lookalike" if any(0 < edit_distance(dom, b) <= 2 for b in BRANDS) else "unknown"
    if any(0 < edit_distance(dom, b) <= 2 for b in BRANDS):
        return "lookalike"  # 정상 브랜드와 한두 글자 차이
    return "unknown"


def domain_type(text):
    """링크 종류. none/brand/short/unknown/lookalike 중 가장 위험한 것을 돌려준다."""
    kinds = {domain_kind(m.group(1)) for m in URL_RE.finditer(text)}
    for k in PRIORITY:
        if k in kinds:
            return k
    return "none"


def group_id(text):
    return re.sub(r"\d+", "0", text)[-30:]


def rec(text, label, source, channel, origin, orig_id):
    return {"text": text, "label": label, "source": source, "channel": channel, "origin": origin,
            "group_id": group_id(text), "domain_type": domain_type(text), "orig_id": orig_id, "license": LIC[source]}


URL = re.compile(r"(?:https?://)?((?:[\w-]+\.)+(?:com|kr|net|me|ly|co|xyz|top|cc|vip|info|org|app|link|site|club))", re.I)
BRAND_OK = {"coupang.com"}  # 라벨 3 에 나오는 정상 브랜드 도메인


def class3_label(text):
    """택배 사칭 템플릿(class 3)은 정상 브랜드가 아닌 낯선 도메인 링크가 있을 때만 스미싱(1).
    그 외는 정상 알림과 구분되지 않으므로 라벨 없음(None)으로 두어 학습에서 제외한다."""
    doms = {d.lower() for d in URL.findall(text)}
    return 1 if doms - BRAND_OK else None


def korean_message():
    m = {"1": 0, "2": 1}
    with open(D / "Korean_message/lgaidataset.csv", encoding="utf-8-sig", newline="") as f:
        for i, r in enumerate(csv.DictReader(f)):
            t = r["content"].strip()
            if not t or r["class"] not in (*m, "3"):
                continue
            label = m[r["class"]] if r["class"] in m else class3_label(t)
            yield rec(t, label, "korean_message", "sms", "real", f"row{i}:class{r['class']}")


def kr_mob():
    for fp in sorted(glob.glob(str(D / "KR-MOB-SMISHING-v2/incidents/*.json"))):
        d = json.load(open(fp, encoding="utf-8"))
        label = 1 if d["case_type"] == "malicious" else 0
        for k, s in enumerate(d["message_samples_used"]):
            t = re.sub(r"^\[TRAINING\]\s*", "", s["text"]).strip()
            yield rec(t, label, "kr_mob_smishing_v2", "sms", "synthetic", f"{d['incident_id']}#{k}:{d['case_type']}")


def voice():
    p = D / "derived/voice_transcripts.jsonl"
    if p.exists():
        for l in open(p, encoding="utf-8"):
            r = json.loads(l)
            yield rec(r["text"], r["label"], "fss_voice", "voice", "real", r["orig_id"])


def normal_calls():
    p = D / "derived/normal_calls.jsonl"  # build_normal_calls.py 가 만든다
    if p.exists():
        for l in open(p, encoding="utf-8"):
            r = json.loads(l)
            yield rec(r["text"], r["label"], "kspon_speech", "voice", "real", r["orig_id"])


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    seen, rows = set(), []
    for r in [*korean_message(), *kr_mob(), *voice(), *normal_calls()]:
        key = (r["source"], r["text"])
        if key not in seen:  # 같은 출처 안의 정확히 같은 문자열만 제거
            seen.add(key); rows.append(r)
    with open(OUT, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    from collections import Counter
    for k, v in sorted(Counter((r["label"] if r["label"] is not None else -1, r["domain_type"]) for r in rows).items()):
        print("label", k[0], "domain_type", k[1], v)
    for k, v in sorted(Counter((r["source"], str(r["label"])) for r in rows).items()):
        print(k, v)
    print("total", len(rows))


if __name__ == "__main__":
    main()
