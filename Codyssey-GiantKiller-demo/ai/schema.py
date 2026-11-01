"""AI 판단 결과 형식. LLM 출력은 항상 normalize() 를 거친다.

안에서는 소문자 값을 쓰고, AI 서버(ai/server.py)가 밖으로 낼 때 대문자로 바꾼다 (docs/AI_API.md).
"""

CATEGORIES = ("scam", "child_impersonation", "need_explain", "safe")
SCAM_TYPES = ("delivery", "prosecutor", "bank", "child", "subsidy", "none")
RISKS = ("low", "medium", "high")
# 상대가 시킨 행동
INSTRUCTIONS = (
    "app_install",     # 앱 설치 (링크 눌러 설치, '보안 앱' 등)
    "remote_control",  # 원격 제어 앱 설치 (팀뷰어·애니데스크·퀵서포트 등)
    "transfer",        # 계좌 이체·송금·상품권 구매
    "cash",            # 현금 인출·전달·보관
    "share_info",      # 개인정보·인증번호·카드번호·신분증 알려 달라
)
INSTALL_INSTRUCTIONS = ("app_install", "remote_control")

SCAM_LABEL = {
    "delivery": "택배",
    "prosecutor": "검찰·수사기관",
    "bank": "금융",
    "child": "자녀",
    "subsidy": "정부지원금",
    "none": "",
}
INSTR_LABEL = {
    "app_install": "앱 설치",
    "remote_control": "원격 제어 앱 설치",
    "transfer": "계좌 이체",
    "cash": "현금 인출",
    "share_info": "개인정보 알려주기",
}


class SchemaError(ValueError):
    """LLM 이 약속한 모양으로 답하지 않음. 절대 '안전'으로 바꿔 넣지 않는다 → 규칙 판단으로 대신한다."""


def normalize(raw: dict, event_id: str) -> dict:
    if not isinstance(raw, dict):
        raise SchemaError(f"JSON 객체가 아님: {type(raw).__name__}")
    category = str(raw.get("category") or "").strip().lower()
    if category not in CATEGORIES:
        raise SchemaError(f"category 값이 이상함: {raw.get('category')!r}")

    def pick(key, allowed, default):
        v = str(raw.get(key) or "").strip().lower()
        return v if v in allowed else default

    def str_list(key):
        v = raw.get(key) or []
        if isinstance(v, str):
            v = [v]
        return [str(x).strip() for x in v if str(x).strip()] if isinstance(v, list) else []

    instr = [i for i in dict.fromkeys(x.lower() for x in str_list("instructions")) if i in INSTRUCTIONS]
    danger = category in ("scam", "child_impersonation")
    out = {
        "event_id": event_id,
        "category": category,
        "scam_type": pick("scam_type", SCAM_TYPES, "none"),
        # 위험도가 빠지거나 이상하면 분류에 맞춰 채운다 (위험 분류를 낮은 위험으로 두지 않는다)
        "risk": pick("risk", RISKS, "high" if danger else "low"),
        "reason": str(raw.get("reason") or "").strip(),
        "explain": str(raw.get("explain") or "").strip(),
        "summary": str(raw.get("summary") or "").strip(),
        "instructions": instr,
        "mentioned_apps": list(dict.fromkeys(str_list("mentioned_apps")))[:5],
    }
    if category == "child_impersonation":
        out["scam_type"] = "child"
    if danger and out["risk"] == "low":
        out["risk"] = "medium"
    return out
