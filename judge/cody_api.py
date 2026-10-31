"""코디세이 API 게이트웨이(https://copa.codyssey.kr) 호출 헬퍼.

키는 이 폴더의 `.env` 에서 읽는다(`.env` 는 커밋하지 않는다).
모델 이름만 바꾸면 GPT 계열과 Claude 계열을 같은 함수로 호출할 수 있다.
규격이 서로 다른 부분(경로, 인증 헤더, 응답 구조)은 이 파일이 흡수한다.

    from cody_api import ask
    print(ask("한 줄로 자기소개해줘"))
    print(ask("같은 질문", model="claude-haiku-4"))

명령줄에서도 쓸 수 있다.

    python 0.opt/AI-api/cody_api.py --models
    python 0.opt/AI-api/cody_api.py "요약해줘" --model gpt-5.4
"""

import os
import sys
import argparse
import requests

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

def repo_root(start=__file__):
    """`.git` 을 만날 때까지 올라간다. 이 파일이 어느 폴더로 옮겨져도 `.env` 를 찾는다."""
    path = os.path.dirname(os.path.abspath(start))
    while True:
        if os.path.isdir(os.path.join(path, ".git")):
            return path
        parent = os.path.dirname(path)
        if parent == path:
            return os.path.dirname(os.path.abspath(start))
        path = parent


def _find_env():
    """이 파일 옆을 먼저 보고, 없으면 저장소 루트를 본다. 둘 다 없으면 옆 경로를 돌려준다."""
    here = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    for candidate in (here, os.path.join(repo_root(), ".env")):
        if os.path.exists(candidate):
            return candidate
    return here


ENV_PATH = _find_env()
DEFAULT_BASE_URL = "https://copa.codyssey.kr"
DEFAULT_MODEL = "gpt-5.4-mini"
TIMEOUT = 120

# 월 한도에 대한 차감 배수. API 콘솔 문서(CodysseyApiRule.pdf)의 표를 그대로 옮긴다.
TOKEN_WEIGHTS = {
    # CHAT
    "claude-opus-4-8": 1.5,      # Claude Opus 4.8
    "claude-opus-4-7": 1.5,      # Claude Opus 4.7
    "claude-sonnet-4": 1.0,      # Claude Sonnet 4.6
    "claude-haiku-4": 0.5,       # Claude Haiku 4.5
    "gpt-5.5": 2.0,
    "gpt-5.4": 1.0,
    "gpt-5.4-mini": 0.5,
    "gpt-5-mini": 0.5,
    "gemini-3.1-pro": 1.5,
    "gemini-3-flash": 0.5,
    "gemini-3.1-flash-lite": 0.5,
    # IMAGE / AUDIO / VIDEO 는 전부 1.0
    "gpt-image-2": 1.0, "gpt-image-1.5": 1.0, "gpt-image-1-mini": 1.0,
    "imagen-4": 1.0, "imagen-4-fast": 1.0, "imagen-4-ultra": 1.0,
    "gemini-2.5-flash-image": 1.0,
    "tts-1": 1.0, "tts-1-hd": 1.0, "gpt-4o-mini-tts": 1.0,
    "gemini-2.5-flash-tts": 1.0,
    "sora-2": 1.0, "veo-3.1": 1.0, "veo-3.1-fast": 1.0,
}


def load_env(path=ENV_PATH):
    """`.env` 를 읽어 os.environ 에 채운다. 이미 설정된 값은 덮어쓰지 않는다."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _base_url():
    load_env()
    return os.environ.get("CODY_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def _key_for(model):
    """모델 계열에 맞는 키를 고른다.

    Claude 계열은 codyclaude 키, 나머지는 codygpt 키를 쓴다.
    Gemini 계열이 어느 키에 속하는지는 안내에 없어 codygpt 키로 보낸다.
    """
    load_env()
    name = "CODY_CLAUDE_KEY" if model.startswith("claude") else "CODY_GPT_KEY"
    key = os.environ.get(name)
    if not key:
        raise RuntimeError(
            f"{name} 가 없다. `.env.example` 을 `.env` 로 복사하고 키를 채울 것 ({ENV_PATH})"
        )
    return key


def models():
    """게이트웨이가 실제로 열어둔 모델 ID 목록을 돌려준다."""
    r = requests.get(
        f"{_base_url()}/v1/models",
        headers={"Authorization": f"Bearer {_key_for('gpt')}"},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return [m["id"] for m in r.json()["data"]]


def ask(prompt, model=DEFAULT_MODEL, system=None, max_tokens=1024, temperature=None):
    """한 번 묻고 답 문자열만 돌려준다. 규격 차이는 모델 이름으로 자동 분기한다."""
    return chat([{"role": "user", "content": prompt}], model, system, max_tokens, temperature)


def chat(messages, model=DEFAULT_MODEL, system=None, max_tokens=1024, temperature=None):
    """대화 이력을 넘겨 이어서 묻는다. messages 는 OpenAI 형식으로 통일한다."""
    if model.startswith("claude"):
        return _anthropic(messages, model, system, max_tokens, temperature)
    return _openai(messages, model, system, max_tokens, temperature)


def _openai(messages, model, system, max_tokens, temperature):
    """OpenAI 호환 규격: /v1/chat/completions, Bearer 인증, choices 로 응답."""
    if system:
        messages = [{"role": "system", "content": system}] + list(messages)
    payload = {"model": model, "messages": messages, "max_tokens": max_tokens}
    if temperature is not None:
        payload["temperature"] = temperature
    r = requests.post(
        f"{_base_url()}/v1/chat/completions",
        headers={"Authorization": f"Bearer {_key_for(model)}"},
        json=payload,
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _anthropic(messages, model, system, max_tokens, temperature):
    """Anthropic 규격: /v1/messages, x-api-key 인증, max_tokens 필수, content 블록으로 응답."""
    payload = {"model": model, "messages": list(messages), "max_tokens": max_tokens}
    if system:
        payload["system"] = system          # 시스템 프롬프트가 messages 안이 아니다.
    if temperature is not None:
        payload["temperature"] = temperature
    r = requests.post(
        f"{_base_url()}/v1/messages",
        headers={
            "x-api-key": _key_for(model),
            "anthropic-version": "2023-06-01",
        },
        json=payload,
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    blocks = r.json()["content"]
    return "".join(b.get("text", "") for b in blocks if b.get("type") == "text")


def main():
    parser = argparse.ArgumentParser(description="코디세이 게이트웨이에 한 번 질문한다.")
    parser.add_argument("prompt", nargs="?", help="질문. 생략하면 표준입력에서 읽는다.")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--system", default=None)
    parser.add_argument("--max-tokens", type=int, default=1024)
    parser.add_argument("--models", action="store_true", help="사용 가능한 모델 목록만 출력한다.")
    args = parser.parse_args()

    if args.models:
        for name in models():
            weight = TOKEN_WEIGHTS.get(name)
            note = f"차감 {weight}배" if weight else "차감 비율 미공지"
            print(f"{name:24} {note}")
        return

    prompt = args.prompt if args.prompt is not None else sys.stdin.read()
    if not prompt.strip():
        parser.error("질문이 비어 있다.")
    print(ask(prompt, model=args.model, system=args.system, max_tokens=args.max_tokens))


if __name__ == "__main__":
    main()
