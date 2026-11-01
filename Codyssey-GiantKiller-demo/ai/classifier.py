"""작은 분류 모델: 팀원이 학습한 한국어 BERT (스미싱/스팸 이진 분류) 를 불러 쓴다.

학습·데이터는 팀원 것을 그대로 쓴다 (서버 ~/nahyun/model: prepare_data.py → train.py, 결과 out/best · out/best_large).
- 라벨: 0 일반, 1 스미싱/스팸. 4가지 분류·설명 문구는 LLM·규칙이 맡는다
- 입력 전처리도 팀원과 같게: 링크를 [URL_종류] 로 바꾼다 (prepare_data.tokenize_urls · data/build_unified.domain_kind)
.env 에 CLASSIFIER_DIR=<팀원 out/best 경로> 를 넣었을 때만 동작하고, transformers·torch 가 필요하다 (requirements-gpu.txt).
"""
import os
import re

_model = None

# ── 팀원 data/build_unified.py 와 같은 규칙 (링크 종류: short/brand/lookalike/unknown) ──
SHORTENERS = {"bit.ly", "me2.do", "url.kr", "han.gl", "vo.la", "t.ly", "tinyurl.com", "is.gd", "naver.me", "buly.kr"}
BRANDS = {"coupang.com", "naver.com", "kakao.com", "toss.im", "tosspayments.com", "post.go.kr", "epost.go.kr",
          "musinsa.com", "11st.co.kr", "gmarket.co.kr", "auction.co.kr", "kbstar.com", "shinhan.com",
          "wooribank.com", "hanabank.com", "nonghyup.com", "ebay.com"}
URL_RE = re.compile(r"(?:https?://)?((?:[\w-]+\.)+[a-z]{2,})(?:/\S*)?", re.I)


def _edit_distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[-1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def domain_kind(dom: str) -> str:
    dom = dom.lower().strip(".")
    if dom in SHORTENERS:
        return "short"
    if dom in BRANDS or any(dom.endswith("." + b) for b in BRANDS):
        return "brand"
    if any(0 < _edit_distance(dom, b) <= 2 for b in BRANDS):
        return "lookalike"  # 정상 브랜드와 한두 글자 차이
    return "unknown"


def tokenize_urls(text: str) -> str:
    """링크를 [URL_종류] 토큰으로 (모델이 도메인 문자열을 외우지 않고 종류로 판단하게) — 팀원 prepare_data.py 와 같음"""
    return URL_RE.sub(lambda m: f"[URL_{domain_kind(m.group(1))}]", text)


def available() -> bool:
    return bool(os.getenv("CLASSIFIER_DIR"))


def threshold() -> float:
    return float(os.getenv("CLASSIFIER_THRESHOLD", "0.5"))


def _load():
    global _model
    if _model is None:
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        path = os.environ["CLASSIFIER_DIR"]
        device = "cuda" if torch.cuda.is_available() else "cpu"
        tok = AutoTokenizer.from_pretrained(path)
        model = AutoModelForSequenceClassification.from_pretrained(path).to(device).eval()
        _model = (tok, model, device, torch)
    return _model


def danger_scores(texts: list[str], max_len: int = 128) -> list[float]:
    """각 문자가 스미싱/스팸(라벨 1)일 확률. max_len 128 은 팀원 학습 설정과 같음"""
    tok, model, device, torch = _load()
    out = []
    for i in range(0, len(texts), 32):
        batch = tok([tokenize_urls(t) for t in texts[i:i + 32]], truncation=True, max_length=max_len, padding=True,
                    return_tensors="pt").to(device)
        with torch.no_grad():
            probs = torch.softmax(model(**batch).logits, dim=-1)[:, 1]
        out += probs.tolist()
    return out


def classify(text: str) -> dict:
    p = danger_scores([text])[0]
    return {"category": "scam" if p >= threshold() else "safe", "score": round(p, 4)}
