"""평가·학습용 문자 데이터 불러오기. 형식이 제각각인 공개 데이터를 한 모양으로 맞춘다.

한 줄 = {"text": 문자, "expect": scam|child_impersonation|need_explain|safe, "known": 아는 번호인가, "src": 출처}

받는 형식
- .jsonl : {"content" 또는 "text", "expect" 또는 "label", "sender"?, "known"?}
- .csv/.tsv : 글·정답 칸 이름을 자동으로 찾는다 (text/content/message/문자/내용, label/expect/class/정답 …)
- .txt : 한 줄에 문자 하나. 정답은 파일 단위로 준다 (예: smishing.txt:scam)
- 끝에 :known 을 붙이면 그 파일 문자는 모두 '아는 번호에서 온 것' (예: family_chat.txt:safe:known)
  → 폰 1차 필터 효과(평범한 문자 중 몇 %가 폰 밖으로 안 나가나)는 이 정보가 있어야 잴 수 있다
"""
import csv
import hashlib
import json
import re
from pathlib import Path

DANGER = {"scam", "child_impersonation"}
TEXT_COLS = ("text", "content", "message", "msg", "sms", "body", "문자", "내용", "본문", "메시지")
LABEL_COLS = ("expect", "label", "category", "class", "is_smishing", "smishing", "y", "정답", "라벨", "분류")
LABEL_MAP = {
    "scam": "scam", "smishing": "scam", "spam": "scam", "phishing": "scam", "fraud": "scam", "1": "scam", "true": "scam",
    "사기": "scam", "스미싱": "scam", "피싱": "scam", "위험": "scam",
    "child_impersonation": "child_impersonation", "자녀사칭": "child_impersonation", "자녀 사칭": "child_impersonation",
    "need_explain": "need_explain", "안내": "need_explain", "설명": "need_explain",
    "safe": "safe", "normal": "safe", "ham": "safe", "0": "safe", "false": "safe", "정상": "safe", "평범": "safe",
}


def norm_label(v) -> str:
    key = str(v).strip().lower()
    if key not in LABEL_MAP:
        raise ValueError(f"정답 값을 모르겠어요: {v!r} (scam/safe/smishing/normal/1/0/사기/정상 …)")
    return LABEL_MAP[key]


def text_key(text: str) -> str:
    """중복·학습/평가 겹침 확인용. 모델이 보는 모양(가린 문자) 기준 + 공백·기호 무시.
    이름만 바꾼 틀 문자("이영희 고객님"/"김철수 고객님")는 가리면 같아지므로 같은 문자로 본다
    → 학습과 평가에 나눠 들어가 점수가 부풀려지는 것을 막는다."""
    from .privacy import mask_text
    return hashlib.sha1(re.sub(r"[\W_]+", "", mask_text(text)).encode()).hexdigest()[:16]


def _pick(cols, wanted, what, path):
    low = {c.lower().strip(): c for c in cols}
    for w in wanted:
        if w in low:
            return low[w]
    raise ValueError(f"{path}: {what} 칸을 못 찾았어요. 칸 이름: {list(cols)}")


def load(spec: str, known_numbers: set[str] | None = None) -> list[dict]:
    """spec = '경로' 또는 '경로:정답' 또는 '경로:정답:known'"""
    path, _, rest = spec.partition(":") if not Path(spec).exists() else (spec, "", "")
    forced, _, flag = rest.partition(":")
    all_known = flag == "known"
    p = Path(path)
    forced = norm_label(forced) if forced else None
    digits = lambda s: re.sub(r"\D", "", s or "")  # noqa: E731
    known_numbers = {digits(n) for n in (known_numbers or set())}
    rows = []

    def add(text, label, known=None, sender=""):
        text = (text or "").strip()
        if not text:
            return
        if all_known:
            known = True
        elif known is None:
            known = bool(sender) and digits(sender) in known_numbers
        rows.append({"text": text, "expect": forced or norm_label(label), "known": bool(known), "src": p.name,
                     "sender": sender or ""})

    suffix = p.suffix.lower()
    if suffix == ".jsonl":
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                add(r.get("content") or r.get("text"), r.get("expect", r.get("label")), r.get("known"), r.get("sender") or "")
    elif suffix in (".csv", ".tsv"):
        with p.open(encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f, delimiter="\t" if suffix == ".tsv" else ",")
            tcol = _pick(reader.fieldnames, TEXT_COLS, "문자", p)
            lcol = None if forced else _pick(reader.fieldnames, LABEL_COLS, "정답", p)
            for r in reader:
                add(r[tcol], r[lcol] if lcol else None)
    elif suffix == ".txt":
        if not forced:
            raise ValueError(f"{p}: .txt 는 정답을 붙여 주세요 (예: {p}:scam)")
        for line in p.read_text(encoding="utf-8").splitlines():
            add(line, None)
    else:
        raise ValueError(f"{p}: 모르는 형식 (.jsonl .csv .tsv .txt)")
    return rows


def dedup(rows: list[dict]) -> list[dict]:
    seen, out = set(), []
    for r in rows:
        k = text_key(r["text"])
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out


def save_jsonl(rows: list[dict], path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
