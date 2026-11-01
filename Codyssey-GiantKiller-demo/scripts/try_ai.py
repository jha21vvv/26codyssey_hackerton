"""판단 AI 단독 테스트.

    python scripts/try_ai.py "엄마 나 폰 고장났어 이 번호로 연락해" --sender 010-9876-5432
    python scripts/try_ai.py --demo          # 시연용 문자 전부
    python scripts/try_ai.py --call samples/calls/prosecutor_1.m4a
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai import analyze, mask_text, transcribe  # noqa: E402
from ai.llm import provider  # noqa: E402

CTX = {"child_name": "민수", "child_relation": "아드님", "sender_is_child": False, "sender_known": False, "previous_calls": []}

DEMO = [
    ("1588-1234", "[행복아파트] 10월 관리비 245,300원이 11월 5일 등록하신 계좌에서 자동이체될 예정입니다."),
    ("010-9876-5432", "엄마 나 폰 액정 깨져서 수리 맡겼어. 이 번호로 문자줘 급하게 부탁할 게 있어"),
    ("02-3456-7890", "[국제택배] 주소지 불일치로 배송 보류되었습니다. 확인: http://kr-post-check.xyz/a1"),
    ("010-2222-3333", "내일 경로당에서 10시에 봐요"),
]


def show(item):
    item["content"] = mask_text(item["content"], names=["민수"])
    print("▶", json.dumps(item, ensure_ascii=False))
    print(json.dumps(analyze(item, CTX), ensure_ascii=False, indent=1), "\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("text", nargs="?")
    ap.add_argument("--sender", default="010-9876-5432")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--call")
    a = ap.parse_args()
    print(f"[LLM provider: {provider()}]\n")
    if a.call:
        text, engine = transcribe(a.call)
        print(f"[음성 변환: {engine}]\n{text}\n")
        show({"event_id": "test", "type": "call", "sender": a.sender, "content": text})
    elif a.demo or not a.text:
        for i, (s, t) in enumerate(DEMO):
            show({"event_id": f"test{i}", "type": "message", "sender": s, "content": t})
    else:
        show({"event_id": "test", "type": "message", "sender": a.sender, "content": a.text})
