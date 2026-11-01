"""LLM·음성 변환 호출 코드 테스트. 실제 API 대신 가짜 응답으로 요청 모양과 응답 처리를 확인한다.
(키가 생기면 scripts/try_ai.py --demo 로 실제 호출도 확인할 것)
"""
import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import httpx

from ai import analyze, llm
from ai.transcribe import transcribe

SCAM = {"event_id": "t", "type": "message", "sender": "[전화번호]",
        "content": "[국제택배] 주소 불일치로 배송 보류. 확인 http://kr-post-check.xyz/a1"}
EXPLAIN = {"event_id": "t", "type": "message", "sender": "1588-1234",
           "content": "[행복아파트] 10월 관리비 245,300원 자동이체 예정"}
LLM_JSON = {"category": "need_explain", "scam_type": "none", "risk": "low", "reason": "관리비 안내",
            "explain": "관리비가 빠져나간다는 안내예요.", "summary": "관리비 안내", "instructions": []}


class FakeHTTP:
    """httpx.post 대신 들어가서 요청을 기록하고 정해 둔 응답을 차례로 돌려준다."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url, **kw):
        # json 은 보낸 그 순간의 모양을 남긴다 (코드가 이후에 같은 dict 를 고쳐 다시 보내므로)
        self.calls.append({"url": url, **kw, "json": copy.deepcopy(kw.get("json"))})
        status, body = self.responses.pop(0)
        content = body if isinstance(body, (bytes, str)) else json.dumps(body)
        return httpx.Response(status, content=content, request=httpx.Request("POST", url))


def cody_reply(obj_or_text):
    """코디세이 게이트웨이(claude*) 응답 모양"""
    text = obj_or_text if isinstance(obj_or_text, str) else json.dumps(obj_or_text, ensure_ascii=False)
    return 200, {"content": [{"type": "text", "text": text}]}


def openai_reply(text):
    return 200, {"choices": [{"message": {"content": text}}]}


NO_CODY = {"CODY_CLAUDE_KEY": "", "CODY_GPT_KEY": "", "CODY_MODEL": "", "CODY_BASE_URL": ""}
ENV_CODY = NO_CODY | {"LLM_PROVIDER": "auto", "CODY_CLAUDE_KEY": "test-key", "OPENAI_BASE_URL": "",
                      "TRANSCRIBE_PROVIDER": "auto", "WHISPER_API_URL": ""}
ENGINE = "cody:claude-haiku-4"
ENV_OPENAI = NO_CODY | {"LLM_PROVIDER": "auto", "OPENAI_BASE_URL": "http://llm.local/v1",
              "OPENAI_API_KEY": "k", "OPENAI_MODEL": "exaone"}


class Provider(unittest.TestCase):
    def test_auto_selection(self):
        # 코디세이 게이트웨이 키가 있으면 그것 (팀원 방식)
        with mock.patch.dict(os.environ, NO_CODY | {"LLM_PROVIDER": "auto", "CODY_CLAUDE_KEY": "k"}):
            self.assertEqual(llm.provider(), "cody")
        with mock.patch.dict(os.environ, ENV_OPENAI):
            self.assertEqual(llm.provider(), "openai")
        with mock.patch.dict(os.environ, NO_CODY | {"LLM_PROVIDER": "auto", "OPENAI_BASE_URL": ""}):
            self.assertEqual(llm.provider(), "rule")

    def test_parse_json_in_code_fence(self):
        self.assertEqual(llm.parse_json('여기요\n```json\n{"category": "safe"}\n```'), {"category": "safe"})
        with self.assertRaises(llm.LLMError):
            llm.parse_json("모르겠어요")


class Fallback(unittest.TestCase):
    """LLM 이 실패하거나 위험을 놓쳐도 '안전'으로 넘기지 않는다"""

    def test_api_error_falls_back_to_rule(self):
        fake = FakeHTTP((429, {"error": {"message": "quota"}}))
        with mock.patch.dict(os.environ, ENV_CODY), mock.patch("httpx.post", fake):
            r = analyze(SCAM, {})
        self.assertEqual((r["category"], r["engine"]), ("scam", "rule"))

    def test_timeout_falls_back_to_rule(self):
        # 실제로 겪은 일 (10/30): LLM 이 60초 넘게 응답 없음 → 프로그램이 멈추면 안 되고 규칙 판단으로
        with mock.patch.dict(os.environ, ENV_CODY), mock.patch("httpx.post", side_effect=httpx.ReadTimeout("slow")):
            r = analyze(SCAM, {})
        self.assertEqual((r["category"], r["engine"]), ("scam", "rule"))

    def test_llm_misses_scam_rule_wins(self):
        fake = FakeHTTP(cody_reply({"category": "safe", "reason": "평범"}))
        with mock.patch.dict(os.environ, ENV_CODY), mock.patch("httpx.post", fake):
            r = analyze(SCAM, {})
        self.assertEqual((r["category"], r["engine"]), ("scam", ENGINE + "+rule"))


class DailyLimit(unittest.TestCase):
    def test_limit_falls_back_to_rule_without_calling(self):
        llm.USAGE_FILE.unlink(missing_ok=True)
        fake = FakeHTTP(cody_reply(LLM_JSON), cody_reply(LLM_JSON))
        with mock.patch.dict(os.environ, ENV_CODY | {"LLM_DAILY_LIMIT": "1"}), mock.patch("httpx.post", fake):
            first = analyze(EXPLAIN, {})
            second = analyze(SCAM, {})
        self.assertEqual(first["engine"], ENGINE)
        self.assertEqual((second["engine"], second["category"]), ("rule", "scam"))  # 상한 → 규칙
        self.assertEqual(len(fake.calls), 1)  # 두 번째는 LLM 을 아예 안 부름
        self.assertEqual(llm.usage_today(), 1)
        llm.USAGE_FILE.unlink(missing_ok=True)


class LinkIsNotInstall(unittest.TestCase):
    """실기기 시험(10/30)에서 본 것: 링크만 있는 택배 문자에 LLM 이 '앱 설치'를 붙임 → 빼야 한다"""

    def test_link_only_message_drops_app_install(self):
        llm_out = {"category": "scam", "scam_type": "delivery", "risk": "high", "instructions": ["app_install"]}
        with mock.patch.dict(os.environ, ENV_CODY), mock.patch("httpx.post", FakeHTTP(cody_reply(llm_out))):
            r = analyze(SCAM, {})
        self.assertEqual((r["category"], r["instructions"]), ("scam", []))

    def test_real_install_request_kept(self):
        item = SCAM | {"content": "[카카오] 보안 강화를 위해 아래 앱을 설치하세요 http://kakao-safe.xyz/app.apk"}
        llm_out = {"category": "scam", "scam_type": "none", "risk": "high", "instructions": ["app_install"]}
        with mock.patch.dict(os.environ, ENV_CODY), mock.patch("httpx.post", FakeHTTP(cody_reply(llm_out))):
            r = analyze(item, {})
        self.assertEqual(r["instructions"], ["app_install"])


class OpenAICompatible(unittest.TestCase):
    def test_json_mode_unsupported_retries_without_it(self):
        fake = FakeHTTP((400, {"error": "response_format not supported"}),
                        openai_reply("```json\n" + json.dumps(LLM_JSON) + "\n```"))
        with mock.patch.dict(os.environ, ENV_OPENAI), mock.patch("httpx.post", fake):
            r = analyze(EXPLAIN, {})
        self.assertEqual(len(fake.calls), 2)
        self.assertIn("response_format", fake.calls[0]["json"])
        self.assertNotIn("response_format", fake.calls[1]["json"])
        self.assertEqual(fake.calls[0]["url"], "http://llm.local/v1/chat/completions")
        self.assertEqual(fake.calls[0]["headers"]["Authorization"], "Bearer k")
        self.assertEqual(fake.calls[0]["json"]["model"], "exaone")
        self.assertEqual((r["category"], r["engine"]), ("need_explain", "openai"))

    def test_call_instructions_merged_with_rule(self):
        call = {"event_id": "t", "type": "call", "sender": "[전화번호]",
                "content": "서울중앙지검 수사관입니다. 보안 앱 설치하시고 안전계좌로 이체하세요."}
        fake = FakeHTTP(openai_reply(json.dumps({"category": "scam", "scam_type": "prosecutor", "risk": "high",
                                                 "instructions": ["app_install"]})))
        with mock.patch.dict(os.environ, ENV_OPENAI), mock.patch("httpx.post", fake):
            r = analyze(call, {})
        self.assertEqual(sorted(r["instructions"]), ["app_install", "transfer"])  # LLM 이 놓친 이체 지시를 규칙이 보탬


class Transcribe(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()) / "call.m4a"
        self.tmp.write_bytes(b"fake-audio")

    def test_whisper_api(self):
        fake = FakeHTTP((200, {"text": "검찰입니다"}))
        env = {"TRANSCRIBE_PROVIDER": "whisper_api", "WHISPER_API_URL": "http://gpu:8100/"}
        with mock.patch.dict(os.environ, env), mock.patch("httpx.post", fake):
            text, engine = transcribe(self.tmp)
        self.assertEqual(fake.calls[0]["url"], "http://gpu:8100/v1/audio/transcriptions")
        self.assertEqual(fake.calls[0]["data"]["language"], "ko")
        self.assertEqual((text, engine), ("검찰입니다", "whisper_api"))

    def test_whisper_failure_is_not_sent_elsewhere(self):
        # 통화 원본은 Whisper 로만: 실패하면 다른 곳으로 보내지 않고 오류 (백엔드가 실패로 기록)
        fake = FakeHTTP((500, "down"))
        env = ENV_CODY | {"WHISPER_API_URL": "http://gpu:8100"}
        with mock.patch.dict(os.environ, env), mock.patch("httpx.post", fake):
            with self.assertRaises(httpx.HTTPStatusError):
                transcribe(self.tmp)
        self.assertEqual(len(fake.calls), 1)

    def test_no_engine_raises_clear_error(self):
        with mock.patch.dict(os.environ, {"TRANSCRIBE_PROVIDER": "none"}):
            with self.assertRaises(RuntimeError):
                transcribe(self.tmp)


class Cody(unittest.TestCase):
    """코디세이 게이트웨이: 팀원 model/llm_classify.py ask() 와 같은 요청 모양"""
    MSG = "엄마 나 폰 고장났어 이 번호로 문자줘"
    ANSWER = {"category": "child_impersonation", "scam_type": "child", "risk": "high", "reason": "자녀 사칭",
              "explain": "확인될 때까지 답장하지 마세요.", "summary": "자녀 사칭 의심 문자", "instructions": []}

    def test_claude_request_shape(self):
        fake = FakeHTTP((200, {"content": [{"type": "text", "text": json.dumps(self.ANSWER, ensure_ascii=False)}]}))
        env = NO_CODY | {"LLM_PROVIDER": "auto", "CODY_CLAUDE_KEY": "claude-key"}
        with mock.patch.dict(os.environ, env), mock.patch("httpx.post", fake):
            r = analyze({"type": "message", "content": self.MSG}, {})
        call = fake.calls[0]
        self.assertEqual(call["url"], "https://copa.codyssey.kr/v1/messages")
        self.assertEqual(call["headers"]["x-api-key"], "claude-key")
        self.assertEqual(call["headers"]["anthropic-version"], "2023-06-01")
        self.assertEqual(call["json"]["model"], "claude-haiku-4")  # 팀원 기본값
        self.assertEqual((r["category"], r["engine"]), ("child_impersonation", "cody:claude-haiku-4"))

    def test_gpt_request_shape(self):
        fake = FakeHTTP(openai_reply(json.dumps(self.ANSWER, ensure_ascii=False)))
        env = NO_CODY | {"LLM_PROVIDER": "auto", "CODY_GPT_KEY": "gpt-key", "CODY_MODEL": "gpt-5.4",
                         "CODY_BASE_URL": "https://gw.local/"}
        with mock.patch.dict(os.environ, env), mock.patch("httpx.post", fake):
            r = analyze({"type": "message", "content": self.MSG}, {})
        call = fake.calls[0]
        self.assertEqual(call["url"], "https://gw.local/v1/chat/completions")
        self.assertEqual(call["headers"]["Authorization"], "Bearer gpt-key")
        self.assertEqual(call["json"]["messages"][0]["role"], "system")
        self.assertEqual(r["engine"], "cody:gpt-5.4")

    def test_gateway_error_falls_back_to_rule(self):
        fake = FakeHTTP((500, {"error": "down"}))
        with mock.patch.dict(os.environ, NO_CODY | {"LLM_PROVIDER": "auto", "CODY_CLAUDE_KEY": "k"}), mock.patch("httpx.post", fake):
            r = analyze({"type": "message", "content": self.MSG}, {})
        self.assertEqual((r["category"], r["engine"]), ("child_impersonation", "rule"))



class Bert(unittest.TestCase):
    """팀원 BERT 를 판단에 넣은 것 (CLASSIFIER_DIR 이 있을 때). 모델 대신 점수를 가짜로"""
    SAFE_TEXT = {"event_id": "t", "type": "message", "sender": "", "content": "오늘 저녁 뭐 먹을까"}

    def run_with(self, score, item, env):
        with mock.patch.dict(os.environ, env | {"CLASSIFIER_DIR": "/x"}), \
                mock.patch("ai.classifier.danger_scores", return_value=[score]):
            return analyze(item, {})

    def test_no_llm_rule_safe_bert_high_is_scam(self):
        r = self.run_with(0.7, self.SAFE_TEXT, NO_CODY | {"LLM_PROVIDER": "rule"})
        self.assertEqual((r["category"], r["risk"], r["engine"]), ("scam", "medium", "rule+bert"))
        self.assertIn("BERT", r["reason"])

    def test_no_llm_bert_low_stays_safe(self):
        r = self.run_with(0.2, self.SAFE_TEXT, NO_CODY | {"LLM_PROVIDER": "rule"})
        self.assertEqual((r["category"], r["engine"]), ("safe", "rule+bert"))

    def test_notice_needs_strong_bert(self):
        # 공식 안내(관리비)는 0.9 미만이면 그대로 안내 — base 모델이 공식 안내를 스미싱으로 보는 경향 때문
        self.assertEqual(self.run_with(0.8, EXPLAIN, NO_CODY | {"LLM_PROVIDER": "rule"})["category"], "need_explain")
        self.assertEqual(self.run_with(0.95, EXPLAIN, NO_CODY | {"LLM_PROVIDER": "rule"})["category"], "scam")

    def test_llm_safe_but_bert_strong(self):
        fake = FakeHTTP(cody_reply({"category": "safe", "reason": "평범"}), cody_reply({"category": "safe", "reason": "평범"}))
        with mock.patch("httpx.post", fake):
            r = self.run_with(0.95, self.SAFE_TEXT, ENV_CODY)
            self.assertEqual((r["category"], r["engine"]), ("scam", ENGINE + "+bert"))
            r = self.run_with(0.6, self.SAFE_TEXT, ENV_CODY)  # 0.9 미만이면 LLM 판단 그대로
            self.assertEqual((r["category"], r["engine"]), ("safe", ENGINE))

    def test_bert_failure_is_ignored(self):
        with mock.patch.dict(os.environ, NO_CODY | {"LLM_PROVIDER": "rule", "CLASSIFIER_DIR": "/x"}), \
                mock.patch("ai.classifier.danger_scores", side_effect=OSError("no model")):
            r = analyze(SCAM, {})
        self.assertEqual((r["category"], r["engine"]), ("scam", "rule"))


if __name__ == "__main__":
    unittest.main()
