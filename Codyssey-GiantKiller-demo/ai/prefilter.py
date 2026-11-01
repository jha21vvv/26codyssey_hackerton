"""폰 안 1차 필터 (C안의 '1차 키워드 규칙'). 서버로 보낼지 말지만 정한다.

실제로는 폰에서 돈다: android/.../Guard.kt prefilter().
이 파일은 같은 규칙을 파이썬으로 옮긴 것 — 평가(scripts/eval_ai.py)에서 '1차 필터 효과'를 재는 데 쓴다.
두 곳의 단어 목록을 바꿀 때는 같이 바꿀 것 (tests/test_prefilter.py 가 Guard.kt 와 같은지 확인).
"""
import re

RISK_WORDS = [
    "엄마", "아빠", "급해", "급하게", "폰 고장", "액정", "이 번호", "상품권", "송금", "이체", "입금", "계좌",
    "대출", "검찰", "경찰", "수사", "금감원", "금융감독원", "택배", "배송", "주소지", "지원금", "환급",
    "자동이체", "자동결제", "결제", "승인", "청구", "납부", "인증번호", "앱", "설치",
]
# 진짜 자녀 번호에서 온 문자에는 위험 단어로 치지 않는 말 (가족 일상 대화가 서버로 나가지 않게).
# 나머지 위험 단어·링크·모델 점수는 자녀 번호여도 그대로 (자녀 폰 해킹·번호 조작 대비)
PARENT_WORDS = ["엄마", "아빠"]
LINK = re.compile(r"https?://|www\.|(?<![\w.@])(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,13}\b")


def risk_word(text: str, from_child: bool = False) -> str | None:
    """걸린 위험 단어 (없으면 None). 자녀 번호에서 온 문자면 '엄마'·'아빠'는 빼고 본다."""
    return next((w for w in RISK_WORDS if w in text and not (from_child and w in PARENT_WORDS)), None)


def prefilter(text: str, sender_known: bool, model=None, sender_is_child: bool = False) -> tuple[bool, str]:
    """(서버로 보내는가, 이유).

    model 이 없으면 (예전 규칙) 저장 안 된 번호면 무조건 보낸다.
    model(가벼운 1차 모델)이 있으면: 위험 단어(안내 단어 포함) OR 링크 OR 모델 점수 ≥ 낮은 기준 → 보낸다.
      저장 안 된 번호라도 셋 다 아니면 폰에 남긴다 (평범한 문자를 폰 밖으로 안 내보내기)
    """
    if model is None and not sender_known:
        return True, "저장 안 된 번호"
    if LINK.search(text):
        return True, "링크 포함"
    hit = risk_word(text, sender_is_child)
    if hit:
        return True, f"위험 단어 '{hit}'"
    if model is not None:
        score = model.score(text)
        if score >= model.gate:
            return True, f"1차 모델 점수 {score:.2f}"
        return False, f"{'아는' if sender_known else '저장 안 된'} 번호 · 링크·위험 단어 없음 · 1차 모델 {score:.2f}"
    return False, "아는 번호 · 링크·위험 단어 없음"
