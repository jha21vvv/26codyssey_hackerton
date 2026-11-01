"""LLM 호출. SDK 없이 httpx 로 부른다.

기본은 코디세이 게이트웨이(https://copa.codyssey.kr) — 팀원 model/llm_classify.py 의 ask() 와 같은 방식:
claude* 모델은 Anthropic 규격 /v1/messages (x-api-key: CODY_CLAUDE_KEY), 그 밖은 OpenAI 호환 /v1/chat/completions
(Bearer CODY_GPT_KEY). OpenAI 호환(vLLM 등)은 OPENAI_BASE_URL 을 줄 때.
"""
import json
import os
import re
from datetime import date
from pathlib import Path

import httpx


class LLMError(Exception):
    pass


def provider() -> str:
    p = os.getenv("LLM_PROVIDER", "auto").strip().lower()
    if p != "auto":
        return p
    if os.getenv("CODY_CLAUDE_KEY") or os.getenv("CODY_GPT_KEY"):
        return "cody"
    if os.getenv("OPENAI_BASE_URL"):
        return "openai"
    return "rule"


def parse_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        raise LLMError(f"JSON 없음: {(text or '')[:200]}")
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError as e:
        raise LLMError(f"JSON 파싱 실패: {e}: {m.group(0)[:200]}") from e


# ── 하루 호출 상한 (게이트웨이 한도 보호) ──
# 서버·스크립트가 같은 기록 파일을 써서 합산한다. 넘으면 LLMError → 판단은 규칙으로 대신
USAGE_FILE = Path(os.getenv("LLM_USAGE_FILE") or Path(__file__).resolve().parent.parent / "data" / "llm_usage.json")


def daily_limit() -> int:
    return int(os.getenv("LLM_DAILY_LIMIT", "200"))  # 0 이면 상한 없음


def usage_today() -> int:
    try:
        d = json.loads(USAGE_FILE.read_text())
        return d.get("count", 0) if d.get("day") == date.today().isoformat() else 0
    except (OSError, ValueError):
        return 0


def _count_call():
    """호출 직전에 센다. 상한을 넘으면 LLMError"""
    limit = daily_limit()
    n = usage_today()
    if limit and n >= limit:
        raise LLMError(f"오늘 LLM 호출 상한 {limit}회에 도달 (LLM_DAILY_LIMIT)")
    try:
        USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
        USAGE_FILE.write_text(json.dumps({"day": date.today().isoformat(), "count": n + 1}))
    except OSError:
        pass


def llm_timeout() -> float:
    """판단 대기 시간. 넘으면 LLM 실패 → 규칙 판단 (부모님이 경고를 오래 기다리지 않게)"""
    return float(os.getenv("LLM_TIMEOUT", "20"))


def _post(url: str, **kw) -> httpx.Response:
    """네트워크 오류·시간 초과도 LLMError 로 → 부르는 쪽이 규칙 판단으로 대신한다"""
    try:
        return httpx.post(url, **kw)
    except httpx.HTTPError as e:
        raise LLMError(f"{type(e).__name__}: {e}") from e


def openai_chat(system: str, user: str, timeout: float | None = None) -> str:
    timeout = timeout or llm_timeout()
    base = (os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
    headers = {}
    if os.getenv("OPENAI_API_KEY"):
        headers["Authorization"] = f"Bearer {os.getenv('OPENAI_API_KEY')}"
    body = {
        "model": os.getenv("OPENAI_MODEL", ""),
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    r = _post(f"{base}/chat/completions", headers=headers, json=body, timeout=timeout)
    if r.status_code == 400:  # json 모드 미지원 서버
        body.pop("response_format")
        r = _post(f"{base}/chat/completions", headers=headers, json=body, timeout=timeout)
    if r.status_code != 200:
        raise LLMError(f"OpenAI 호환 {r.status_code}: {r.text[:300]}")
    return r.json()["choices"][0]["message"]["content"]


def cody_model() -> str:
    """팀원 llm_classify.py 기본값과 같은 claude-haiku-4. CODY_MODEL 로 바꾼다 (예: gpt-5.4)"""
    return os.getenv("CODY_MODEL") or "claude-haiku-4"


def cody(system: str, user: str, max_tokens: int = 800, timeout: float | None = None) -> str:
    """코디세이 게이트웨이 한 번 호출 → 답 글자. 키 값은 로그·오류에 남기지 않는다"""
    base = (os.getenv("CODY_BASE_URL") or "https://copa.codyssey.kr").rstrip("/")
    model = cody_model()
    timeout = timeout or llm_timeout()
    if model.startswith("claude"):
        key = os.getenv("CODY_CLAUDE_KEY")
        if not key:
            raise LLMError("CODY_CLAUDE_KEY 없음")
        _count_call()
        r = _post(f"{base}/v1/messages", timeout=timeout,
                  headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
                  json={"model": model, "max_tokens": max_tokens, "temperature": 0, "system": system,
                        "messages": [{"role": "user", "content": user}]})
        if r.status_code != 200:
            raise LLMError(f"코디세이 {model} {r.status_code}: {r.text[:200]}")
        return "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text")
    key = os.getenv("CODY_GPT_KEY")
    if not key:
        raise LLMError("CODY_GPT_KEY 없음")
    _count_call()
    r = _post(f"{base}/v1/chat/completions", timeout=timeout, headers={"Authorization": f"Bearer {key}"},
              json={"model": model, "max_tokens": max_tokens, "temperature": 0,
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
    if r.status_code != 200:
        raise LLMError(f"코디세이 {model} {r.status_code}: {r.text[:200]}")
    try:
        return r.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        raise LLMError(f"코디세이 응답 형식 이상: {r.text[:200]}") from e


def complete_json(system: str, user: str) -> tuple[dict, str]:
    """(결과 dict, 사용한 엔진 이름)"""
    p = provider()
    if p == "cody":
        return parse_json(cody(system, user)), f"cody:{cody_model()}"
    if p == "openai":
        return parse_json(openai_chat(system, user)), "openai"
    raise LLMError(f"LLM 미설정 (provider={p})")
