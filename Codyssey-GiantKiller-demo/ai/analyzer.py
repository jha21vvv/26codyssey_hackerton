import logging
import os
import re

from . import classifier, llm, rules
from .prompts import SYSTEM, user_prompt
from .schema import SchemaError, normalize

log = logging.getLogger("ai")

DANGER = ("scam", "child_impersonation")
INSTALL_WORDS = re.compile(r"설치|깔|다운|apk|앱|어플|프로그램", re.I)


def strong() -> float:
    """BERT 가 이 점수 이상이면 LLM·규칙이 '안전'이라 해도 사기로 올린다 (팀원 base 모델은 외부 시험에서
    정상 안내도 스미싱으로 보는 경향이 있어 높게. large 로 바꾼 뒤 결과를 보고 CLASSIFIER_STRONG 으로 조정)"""
    return float(os.getenv("CLASSIFIER_STRONG", "0.9"))


def _bert(item: dict) -> float | None:
    """팀원 BERT 스미싱 점수 (CLASSIFIER_DIR 이 있을 때만). 실패하면 None — 판단을 멈추지 않는다"""
    if not classifier.available():
        return None
    try:
        return classifier.danger_scores([item.get("content", "")])[0]
    except Exception as e:  # 모델 파일·torch 문제
        log.warning("BERT 실패 → 빼고 판단: %s", e)
        return None


def _bert_upgrade(r: dict, score: float, engine: str) -> dict:
    """안전·안내로 본 것을 BERT 가 스미싱이라 확신하면 사기(주의)로 올린다"""
    return r | {
        "category": "scam", "risk": "medium",
        "reason": f"학습 모델(BERT)이 스미싱일 확률을 {score:.2f}로 봤어요." + (f" {r['reason']}" if r.get("reason") else ""),
        "explain": "사기일 수 있는 문자예요. 링크를 누르지 마시고 답장하지 마세요.",
        "summary": r.get("summary") or "학습 모델이 스미싱으로 판단한 문자예요.",
        "engine": engine + "+bert",
    }


def analyze(item: dict, context: dict | None = None) -> dict:
    """item: {"event_id","type":"message|call","sender","content"} (content 는 가려진 상태)
    context: {"child_name","child_relation","sender_is_child","sender_known","previous_calls":[...]}
    반환: 데이터 형식 초안 4번 + "engine"

    판단 순서: ① 키워드 규칙 ② 팀원 BERT 점수(CLASSIFIER_DIR) ③ LLM(코디세이 게이트웨이) ④ 안전망
      - LLM 이 있으면 LLM 판단이 기본. 규칙이 위험이라 했는데 LLM 이 놓치면 규칙, LLM 이 '안전'인데 BERT ≥ 0.9 면 사기(주의)
      - LLM 이 없거나 실패하면 규칙. 규칙이 '안전'인데 BERT ≥ 0.5(CLASSIFIER_THRESHOLD) 면 사기(주의),
        규칙이 '안내'인데 BERT ≥ 0.9 면 사기(주의)
    """
    ctx = context or {}
    rule = normalize(rules.analyze(item, ctx), item.get("event_id", ""))
    score = _bert(item)
    try:
        raw, engine = llm.complete_json(SYSTEM, user_prompt(item, ctx))
        result = normalize(raw, item.get("event_id", ""))
    except (llm.LLMError, SchemaError) as e:  # 응답이 이상하면 '안전'으로 넘기지 않고 규칙 판단으로
        if llm.provider() != "rule":
            log.warning("LLM 실패 → 규칙으로 대체: %s", e)
        if score is not None and ((rule["category"] == "safe" and score >= classifier.threshold())
                                  or (rule["category"] == "need_explain" and score >= strong())):
            return _bert_upgrade(rule, score, "rule")
        return rule | {"engine": "rule" if score is None else "rule+bert"}

    # 안전망: 규칙이 위험이라 했는데 LLM 이 놓치면 규칙 판단을 따른다
    if rule["category"] in DANGER and result["category"] not in DANGER:
        log.info("LLM=%s, 규칙=%s → 규칙 채택", result["category"], rule["category"])
        return rule | {"engine": f"{engine}+rule"}
    # LLM 이 '안전'이라 했는데 BERT 가 스미싱이라 확신하면 사기(주의)로
    if result["category"] == "safe" and score is not None and score >= strong():
        log.info("LLM=safe, BERT=%.2f → 사기(주의)", score)
        return _bert_upgrade(result, score, engine)
    # 문자에 설치를 시키는 말이 전혀 없는데 LLM 이 '앱 설치'라고 하면 뺀다 (링크 클릭 유도를 설치로 오해하는 경우)
    if item.get("type") != "call" and "app_install" in result["instructions"] and not INSTALL_WORDS.search(item.get("content", "")):
        result["instructions"] = [i for i in result["instructions"] if i != "app_install"]
        # 통화 지시는 둘 중 하나라도 잡으면 남긴다
    if item.get("type") == "call":
        result["instructions"] = list(dict.fromkeys(result["instructions"] + rule["instructions"]))
    result["mentioned_apps"] = list(dict.fromkeys(result["mentioned_apps"] + rule["mentioned_apps"]))[:5]
    return result | {"engine": engine}
