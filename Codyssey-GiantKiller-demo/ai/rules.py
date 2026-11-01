"""키워드 규칙 판단. LLM 키가 없거나 호출이 실패할 때 쓰고, LLM 결과의 안전망으로도 쓴다.

정답률 확인: python scripts/eval_ai.py --rule  (테스트 문자: ai/data/testset.jsonl)
"""
import re

from .privacy import URL_RE
from .schema import INSTR_LABEL, SCAM_LABEL

# 사기 유형별 신호 단어. 문자는 단어 + (링크·지시·전용 조건) 이 있어야 사기, 통화는 단어만으로 사기
SCAM_KW = {
    "prosecutor": ["검찰", "지검", "검사", "수사관", "금융감독원", "금감원", "경찰청", "사이버수사", "명의도용", "명의가 도용",
                   "대포통장", "범죄에 연루", "사건에 연루", "금융범죄", "구속", "영장", "피의자", "약식기소", "출석요구", "지급정지"],
    "bank": ["저금리", "대환", "대출", "햇살론", "캐피탈", "한도", "신용등급", "보안승급", "보안 등급", "계좌가 정지",
             "해외결제", "국외발신", "정상 승인", "결제 승인"],
    "delivery": ["택배", "운송장", "주소지", "주소 불일치", "배송 보류", "반송", "통관", "등기", "미수령"],
    "subsidy": ["지원금", "환급금", "장려금", "재난", "국민지원", "건강검진", "건강보험", "국세청", "과태료"],
}
# 이 단어가 있으면 링크가 없어도 사기 (어르신께 문자로 오는 대출 권유·결제 사칭은 거의 전부 사기)
NO_LINK_NEEDED = {
    "bank": [r"대출|대환|햇살론|캐피탈", r"상담|문의|신청|승인|대상|한도"],
    "bank_pay": [r"해외결제|국외발신|정상 승인|결제 승인|결제.{0,20}승인", r"본인.{0,4}아닐|본인.{0,4}아니|신고|고객센터|문의"],
}
LURE_KW = ["고수익", "재택 알바", "재택알바", "부업", "일당", "수익 보장", "투자 리딩", "코인 리딩", "부고", "별세", "청첩장", "결혼식에 초대",
           # 불법 도박 광고
           "카지노", "카지눠", "캬즤노", "슬롯", "토토", "바카라", "홀덤", "배팅", "베팅", "첫충", "매충", "꽁머니", "입플",
           "환전", "가입코드", "가입 코드", "추천코드", "추천 코드", "먹튀", "에볼루션"]
# ①ⓐⒶ㉑ 같은 동그라미 글자로 주소·단어를 비틀어 필터를 피하는 광고
OBFUSCATED = re.compile(r"[\u2460-\u24FF\u2776-\u2793\u3251-\u32BF\u2100-\u214F]")

# 공식 도메인: 이 주소(또는 그 하위 주소)로만 된 링크는 '모르는 링크'로 치지 않는다.
# 비슷하게 만든 가짜 주소(coupang-delivery.com, coupang.com.xyz 등)는 그대로 의심한다.
OFFICIAL_DOMAINS = (
    "go.kr", "gov.kr", "or.kr", "coupang.com", "cjlogistics.com", "hanjin.com", "hanjin.co.kr", "lotteglogis.com", "epost.go.kr",
    "naver.com", "kakao.com", "kakaobank.com", "toss.im", "kbstar.com", "shinhan.com", "wooribank.com", "hanabank.com",
    "nonghyup.com", "ibk.co.kr", "sktelecom.com", "tworld.co.kr", "kt.com", "uplus.co.kr",
)
HOST_RE = re.compile(r"(?:https?://)?(?:www\.)?([a-zA-Z0-9.-]+\.[a-zA-Z]{2,13})", re.I)


def official_link_only(text: str) -> bool:
    hosts = [m.group(1).lower() for m in (HOST_RE.match(u.group(0)) for u in URL_RE.finditer(text)) if m]
    return bool(hosts) and all(any(h == d or h.endswith("." + d) for d in OFFICIAL_DOMAINS) for h in hosts)

PARENT_CALL = re.compile(r"(엄마|아빠|어머니|아버지|어머님|아버님)")
CHILD_TROPES = [
    (["액정", "고장", "깨졌", "깨져", "망가", "잃어버", "분실", "수리", "보험 처리"], "폰이 고장났다"),
    (["이 번호", "임시폰", "임시 번호", "새 번호", "번호 바꿨", "친구폰", "친구 폰", "컴퓨터로 문자", "통화 안 돼", "통화가 안"], "이 번호로 연락하라"),
    (["상품권", "기프트카드", "문화상품권"], "상품권을 사 달라"),
    (["송금", "이체", "돈 좀", "보내줘", "보내줄", "입금", "결제 좀", "만원만", "병원비", "합의금"], "돈을 보내 달라"),
    (["신분증", "카드 번호", "카드번호", "비밀번호", "인증번호"], "개인정보를 보내 달라"),
    (["앱", "어플", "설치", "링크", "깔아"], "앱을 설치하라"),
    (["사고", "다쳤", "응급실", "경찰서"], "사고가 났다"),
    (["급해", "급하게", "급한 일", "부탁"], "급한 부탁이 있다"),
]
# 자녀가 아닌 사람이 자녀 소식을 빙자 ("아드님 친구인데요")
CHILD_PROXY = re.compile(r"(아드님|따님|아들|딸|자녀분?).{0,6}(친구|동료|선배|후배|직장|회사)")

EXPLAIN_KW = [
    (["인증번호", "인증 번호"], "인증번호 문자예요. 누가 물어봐도 절대 알려주지 마세요."),
    (["자동이체", "자동 이체", "자동결제", "자동 결제", "정기결제", "자동납부", "자동 납부"],
     "{subj}자동으로 빠져나간다는 안내예요. 따로 하실 일은 없어요."),
    (["승인", "결제 완료", "결제완료", "결제되었", "일시불"],
     "카드로 결제됐다는 안내예요. 직접 쓰신 게 맞으면 하실 일은 없어요. 모르는 결제면 자녀분께 알려주세요."),
    (["결제예정", "결제 예정", "청구", "납부", "고지", "요금"], "{obj}낼 때가 됐다는 안내예요. 통장에 돈이 있는지만 확인하시면 돼요."),
    (["입금", "출금", "잔액"], "통장에 돈이 들어오거나 나갔다는 안내예요. 따로 하실 일은 없어요."),
    (["배송 완료", "배송완료", "배달 완료", "배달완료", "문 앞에"], "주문하신 물건이 도착했다는 안내예요. 따로 하실 일은 없어요."),
    (["예약이 확인", "예약 확인", "진료 예약", "예약되었"], "예약이 잡혔다는 안내예요. 날짜와 시간만 기억해 두세요."),
    (["조제", "처방약"], "약이 준비됐다는 안내예요. 약국에 가서 받으시면 돼요."),
]
WHAT_KW = ["관리비", "전기요금", "가스요금", "수도요금", "통신요금", "보험료", "카드대금", "구독료"]

INSTR_RE = {
    "app_install": re.compile(r"(앱|어플|애플리케이션|프로그램|보안).{0,12}(설치|깔|다운)|설치\s?하|깔아|\.apk", re.S),
    "remote_control": re.compile(r"원격|팀뷰어|teamviewer|애니데스크|anydesk|퀵서포트|quick ?support|알서포트|remote ?call|화면 ?공유", re.I),
    "transfer": re.compile(r"이체|송금|안전계좌|보호계좌|국가안전계좌|입금|계좌로|상품권|보내줘|보내줄|만원만"),
    "cash": re.compile(r"현금|인출|뽑아|찾아서|보관함|직접 전달|전달해"),
    "share_info": re.compile(r"인증 ?번호.{0,10}(알려|불러|보내|말해)|비밀번호|카드 ?번호|신분증|주민(등록)? ?번호|보안카드|OTP|계좌 ?번호.{0,6}(알려|불러)", re.I),
}

# 통화·문자에서 말한 앱 이름 → 백엔드가 실제 설치된 앱과 맞춰볼 때 쓴다
REMOTE_APPS = {"팀뷰어": "TeamViewer", "teamviewer": "TeamViewer", "애니데스크": "AnyDesk", "anydesk": "AnyDesk",
               "퀵서포트": "QuickSupport", "quicksupport": "QuickSupport", "알서포트": "RemoteCall", "remotecall": "RemoteCall"}
QUOTED_APP = re.compile(r"['\"‘“]([^'\"’”]{2,15})['\"’”]\s*(?:앱|어플|프로그램)")
NAMED_APP = re.compile(r"((?:[가-힣A-Za-z0-9]+\s)?[가-힣A-Za-z0-9]{2,})\s?(?:앱|어플)(?:을|를|이|가)?\s?.{0,4}(?:설치|깔|다운)")
NOT_APP_NAME = {"보안", "이", "그", "해당", "무료", "새", "다른", "그냥", "이거", "그거", "어떤", "무슨"}


SPEAKER_LINE = re.compile(r"^\s*(상대|부모님)\s*:\s*(.*)$")


def other_party(text: str) -> str:
    """받아쓰기에 '상대:/부모님:' 줄 이름이 있으면 상대방 말만, 없으면 전체.
    부모님이 되묻는 말("앱을요?", "이체요?")을 지시로 잡지 않으려고."""
    lines = [SPEAKER_LINE.match(line) for line in text.splitlines()]
    if not any(lines):
        return text
    return "\n".join(m.group(2) for m in lines if m and m.group(1) == "상대")


def mentioned_apps(text: str) -> list[str]:
    found = [m.group(1).strip() for m in QUOTED_APP.finditer(text)]
    for m in NAMED_APP.finditer(text):
        name = m.group(1).strip()
        last = name.split()[-1]
        if name not in NOT_APP_NAME and not re.search(r"(서|고|면|해|요|게)$", last) and not any(name in f for f in found):
            found.append(name)
    low = text.lower()
    found += [canon for word, canon in REMOTE_APPS.items() if word in low]
    return list(dict.fromkeys(found))[:5]


def josa(word: str, with_batchim: str, without: str) -> str:
    c = word[-1] if word else ""
    return with_batchim if "가" <= c <= "힣" and (ord(c) - 0xAC00) % 28 else without


def extract_instructions(text: str) -> list[str]:
    return [k for k, rx in INSTR_RE.items() if rx.search(text)]


def _hits(text: str, words: list[str]) -> list[str]:
    return [w for w in words if w in text]


def _all(text: str, patterns: list[str]) -> bool:
    return all(re.search(p, text) for p in patterns)


def _child_impersonation(text: str, ctx: dict) -> dict | None:
    # 진짜 자녀 번호면 사칭이 아니다. 저장된 번호라도 자녀가 아닌데 자녀처럼 굴면 자녀에게 확인한다
    if ctx.get("sender_is_child"):
        return None
    where = "저장된 번호" if ctx.get("sender_known") else "모르는 번호"
    proxy = bool(CHILD_PROXY.search(text))
    if not (PARENT_CALL.search(text) or proxy):
        return None
    tropes = [label for words, label in CHILD_TROPES if _hits(text, words)]
    if proxy and not tropes:
        tropes = ["자녀 지인이라며 연락했다"]
    if not tropes:
        return None
    t = ", ".join(tropes[:3])
    return {
        "category": "child_impersonation",
        "scam_type": "child",
        "risk": "high",
        "reason": f"등록된 자녀 번호가 아닌 곳에서 자녀{'의 지인' if proxy else ''}처럼 '{t}'는 내용을 보냈어요.",
        "explain": "자녀분이 보낸 문자인지 확인하고 있어요. 확인될 때까지 답장하지 마세요.",
        "summary": f"{where}에서 자녀{' 지인' if proxy else ''}인 척 '{t}'는 문자가 왔어요.",
        "instructions": extract_instructions(text),
        "mentioned_apps": mentioned_apps(text),
    }


def analyze(item: dict, context: dict | None = None) -> dict:
    ctx = context or {}
    text = item.get("content", "") or ""
    is_call = item.get("type") == "call"
    prev = ctx.get("previous_calls") or []
    joined = "\n".join([p.get("summary", "") for p in prev] + [text])
    unknown = not ctx.get("sender_known") and not ctx.get("sender_is_child")

    base = {"category": "safe", "scam_type": "none", "risk": "low", "reason": "", "explain": "", "summary": "", "instructions": []}

    # 1) 자녀 사칭 (문자만)
    if not is_call and (imp := _child_impersonation(text, ctx)):
        return base | imp

    # 2) 사기
    scope = joined if is_call else text
    found = {t: _hits(scope, kw) for t, kw in SCAM_KW.items()}
    has_url = bool(URL_RE.search(text))
    official = has_url and official_link_only(text)
    obfuscated = len(OBFUSCATED.findall(text)) >= 2
    lure = _hits(text, LURE_KW)
    instr = extract_instructions(other_party(text) if is_call else text)
    if is_call:  # 같은 번호의 이전 통화에서 나온 지시도 합친다
        for p in prev:
            instr += [i for i in p.get("instructions", []) if i not in instr]

    scam_type, hits = "none", []
    for t in ("prosecutor", "bank", "subsidy", "delivery"):
        if found[t]:
            scam_type, hits = t, found[t]
            break
    no_link = any(_all(text, pats) for pats in NO_LINK_NEEDED.values())
    loan = _all(text, NO_LINK_NEEDED["bank"])
    kind = ctx.get("sender_kind", "unknown")
    if no_link and scam_type in ("none", "delivery", "subsidy"):
        scam_type = "bank"

    signals = []
    if is_call:
        if scam_type != "none":
            signals.append("수상한 기관·금융 이야기")
        if len(instr) >= 2:
            signals.append("여러 행동 지시")
    else:
        if scam_type == "prosecutor":
            signals.append("수사기관 사칭")
        if no_link:
            signals.append("대출·결제 사칭")
        if scam_type != "none" and (has_url or instr):
            signals.append("링크·지시")
        if obfuscated and (has_url or ".com" in text.lower() or "코드" in text):
            signals.append("비튼 글자 광고")
        if has_url and unknown and not official:
            signals.append("모르는 번호의 링크")
        if lure and (has_url or unknown):
            signals.append("미끼 문구")
        if "app_install" in instr and unknown:
            signals.append("앱 설치 유도")
        if kind == "international" and (has_url or scam_type != "none"):
            signals.append("해외 발신")

    # 공식 대표번호(15xx 등)에서 온 링크 안내는 사기로 단정하지 않는다 → 경고창 대신 "링크 말고 공식 앱으로 확인" 설명.
    # 단, 수사기관 사칭·대출 권유·미끼 문구·앱 설치/원격 제어/개인정보 요구는 대표번호여도 사기로 본다.
    strong = (scam_type == "prosecutor" or loan or lure
              or any(i in instr for i in ("app_install", "remote_control", "share_info")))
    if signals and not is_call and kind == "business" and not strong:
        label = SCAM_LABEL[scam_type]
        return base | {
            "category": "need_explain",
            "scam_type": scam_type,
            "risk": "low",
            "reason": f"대표번호에서 온 {label + ' ' if label else ''}안내라 사기로 단정하지 않았어요. 링크 대신 공식 앱 확인을 권했어요.",
            "explain": "공식 대표번호에서 온 안내로 보여요. 그래도 문자 속 링크는 누르지 마시고, 쓰시던 앱이나 대표번호로 직접 확인하세요.",
            "summary": f"대표번호의 {label + ' ' if label else ''}안내 문자 (링크는 누르지 않도록 안내)",
        }
    if signals:
        label = SCAM_LABEL[scam_type]
        what = f"{label} 사칭 " if label else ""
        instr_txt = "·".join(INSTR_LABEL[i] for i in instr)
        clues = (hits[:3] or lure[:2]) + (["링크"] if has_url else [])
        if is_call:
            summary = f"{what}의심 통화예요." + (f" 통화에서 {instr_txt}{josa(instr_txt, '을', '를')} 요구했어요." if instr else "")
        else:
            summary = f"{what or ('·'.join(lure[:1]) + ' ' if lure else '')}의심 문자예요." + (" 링크를 누르게 하려고 해요." if has_url else "")
        reason = (f"'{', '.join(clues)}' 같은 사기 신호가 있어요." if clues else f"{', '.join(signals)} 신호가 있어요.")
        return base | {
            "category": "scam",
            "scam_type": scam_type,
            "risk": "high" if (scam_type == "prosecutor" or instr or no_link) else "medium",
            "reason": reason + (f" {instr_txt}{josa(instr_txt, '을', '를')} 시켰어요." if instr else ""),
            "explain": f"{what}사기로 보여요. 링크를 누르거나 전화하지 마세요." if not is_call else f"{what}사기로 보여요. 시키는 대로 하지 마세요.",
            "summary": summary,
            "instructions": instr,
            "mentioned_apps": mentioned_apps(other_party(scope) if is_call else scope),
        }

    # 3) 헷갈릴 만한 안내
    for words, tmpl in EXPLAIN_KW:
        if _hits(text, words):
            what = next((w for w in WHAT_KW if w in text), "")
            subj = f"{what}{josa(what, '이', '가')} " if what else "돈이 "
            obj = f"{what}{josa(what, '을', '를')} " if what else "요금을 "
            return base | {
                "category": "need_explain",
                "risk": "low",
                "reason": f"'{_hits(text, words)[0]}' 안내 문자예요.",
                "explain": tmpl.format(subj=subj, obj=obj),
                "summary": f"{what or '생활'} 안내 문자예요. 할 일 없음.",
            }

    return base | {"reason": "사기 신호가 없는 평범한 메시지예요.", "summary": "평범한 메시지예요."}
