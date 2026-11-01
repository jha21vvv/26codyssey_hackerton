"""이름·전화번호·계좌번호 가리기. 폰(프론트)에서 먼저 가리고, 서버에서 한 번 더 가린다."""
import re

# http 링크, www, 그리고 han.gl/abc · kakao-safe.apk 같은 맨 도메인 (영문 도메인만)
URL_RE = re.compile(r"https?://\S+|www\.\S+|(?<![\w.@])(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,13}\b(?:/\S*)?")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?82[-\s]?)?0\d{1,2}[-\s.]?\d{3,4}[-\s.]?\d{4}(?!\d)")
RRN_RE = re.compile(r"(?<!\d)\d{6}[-\s]?[1-4]\d{6}(?!\d)")
# 하이픈으로 끊긴 숫자 묶음 또는 10~14자리 숫자 → 숫자 합계가 10자리 이상이면 계좌로 본다 (날짜 2026-10-30 은 제외)
ACCOUNT_RE = re.compile(r"(?<!\d)\d{2,6}(?:-\d{2,8}){1,3}(?!\d)|(?<!\d)\d{10,14}(?!\d)")
# '홍길동 씨', '김민수님' 같은 3글자 이름 + 호칭
# 앞에 한글이 붙어 있으면 이름이 아니다 ("서울중앙지검 수사관" 의 "앙지검" 은 이름이 아님)
NAME_HONORIFIC_RE = re.compile(r"(?<![가-힣])([가-힣]{3})(?=\s?(?:씨|님|고객|검사|수사관|팀장|과장|대리))")
NOT_NAMES = {"어머니", "아버지", "어머님", "아버님", "할머니", "할아버지", "선생님", "아드님", "고객님", "사모님", "담당자", "자녀분"}


def _account(m: re.Match) -> str:
    return "[계좌번호]" if sum(c.isdigit() for c in m.group(0)) >= 10 else m.group(0)


def mask_text(text: str, names: list[str] | tuple = ()) -> str:
    if not text:
        return text
    # URL 은 판단에 필요하므로 보존: 잠시 빼 두었다가 되돌린다
    urls: list[str] = []

    def keep(m):
        urls.append(m.group(0))
        return f"\x00{len(urls) - 1}\x00"

    t = URL_RE.sub(keep, text)
    t = RRN_RE.sub("[주민번호]", t)
    t = PHONE_RE.sub("[전화번호]", t)
    t = ACCOUNT_RE.sub(_account, t)
    for n in sorted({n for n in names if n and len(n) >= 2}, key=len, reverse=True):
        t = t.replace(n, "[이름]")
    t = NAME_HONORIFIC_RE.sub(lambda m: m.group(1) if m.group(1) in NOT_NAMES else "[이름]", t)
    return re.sub(r"\x00(\d+)\x00", lambda m: urls[int(m.group(1))], t)


def mask_phone(phone: str) -> str:
    """자녀 화면용: 010-9876-5432 → 010-****-5432"""
    parts = re.split(r"[-\s.]", phone or "")
    if len(parts) == 3:
        return f"{parts[0]}-{'*' * len(parts[1])}-{parts[2]}"
    d = re.sub(r"\D", "", phone or "")
    return f"{d[:3]}-****-{d[-4:]}" if len(d) >= 8 else (phone or "")


def sender_kind(sender: str) -> str:
    """번호를 가리기 전에 '종류'만 뽑는다. 판단에는 종류만 쓰고 번호 자체는 넘기지 않는다.

    personal      010 등 휴대폰        — 자녀 사칭·스미싱이 주로 쓰는 번호
    business      15xx·16xx·18xx 대표번호 — 국내 문자는 발신번호 변작이 막혀 있어 공식 기관·기업일 가능성이 높다
    landline      02·031 등 유선      internet  070 인터넷 전화
    international 국외발신·해외 번호    — 사칭에 자주 쓰인다
    short         짧은 번호(114 등)    name      카톡 이름 등 번호가 아님    unknown
    """
    s = (sender or "").strip()
    if not s:
        return "unknown"
    if "국외" in s or "국제" in s:
        return "international"
    if re.search(r"[가-힣A-Za-z]", s):  # 글자가 섞이면 연락처 이름 ('나다1', '민수 폰')
        return "name"
    d = re.sub(r"\D", "", s)
    if s.startswith("+") and not d.startswith("82"):
        return "international"
    if d.startswith("82") and len(d) >= 10:
        d = "0" + d[2:]
    if d.startswith("00"):
        return "international"
    if not d:
        return "name"
    if re.fullmatch(r"01[016789]\d{7,8}", d):
        return "personal"
    if re.fullmatch(r"1[5-9]\d{6}", d):
        return "business"
    if d.startswith("070"):
        return "internet"
    if re.fullmatch(r"0(?:2|[3-6]\d)\d{7,8}", d):
        return "landline"
    if len(d) <= 6:
        return "short"
    return "unknown"


def mask_name(name: str) -> str:
    """연락처 이름 가리기: '나다1' → '나○○' (첫 글자만)"""
    name = (name or "").strip()
    return name[:1] + "○" * max(len(name) - 1, 1) if name else ""
