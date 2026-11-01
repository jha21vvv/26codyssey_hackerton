"""AI 서버 계약 테스트 (docs/AI_API.md). BE 레포 app/core/ai.py 가 이 모양을 그대로 쓸 수 있게.
BE 결과 모델: AlertAnalysisResult · CallAnalysisResult (extra 필드 금지, 사칭이면 requires_attention=true)

    .venv/bin/python -m unittest tests.test_ai_server -v
"""
import json
import os
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient  # noqa: E402

from ai import llm  # noqa: E402
from ai.server import app  # noqa: E402

CALLS = Path(__file__).resolve().parent.parent / "samples" / "calls"
CLASSIFICATIONS = {"SCAM", "CHILD_IMPERSONATION", "NEED_EXPLAIN", "SAFE"}
INSTR = {"INSTALL_APP", "INSTALL_REMOTE", "TRANSFER", "CASH", "SHARE_INFO"}
ALERT_KEYS = {"classification", "requires_attention", "risk_level", "summary"}

c = TestClient(app)


def alert(text):
    r = c.post("/v1/alerts/analyze", json={"text": text})
    assert r.status_code == 200, r.text
    return r.json()


def call_text(text, name="t.txt"):
    return c.post("/v1/calls/analyze", files={"file": (name, text.encode() if isinstance(text, str) else text)})


def check(t: unittest.TestCase, r: dict):
    t.assertIn(r["classification"], CLASSIFICATIONS)
    t.assertIsInstance(r["requires_attention"], bool)
    t.assertEqual(r["requires_attention"], r["classification"] in ("SCAM", "CHILD_IMPERSONATION"))
    t.assertIn(r["risk_level"], {"LOW", "MEDIUM", "HIGH"})


class Alert(unittest.TestCase):
    def test_scam(self):
        r = alert("[국제택배] 주소 불일치로 배송 보류. 확인 http://kr-post-check.xyz/a1")
        self.assertEqual(set(r), ALERT_KEYS)
        check(self, r)
        self.assertEqual(r["classification"], "SCAM")

    def test_child_impersonation(self):
        r = alert("엄마 나 폰 액정 깨져서 수리 맡겼어. 이 번호로 문자줘")
        check(self, r)
        self.assertEqual((r["classification"], r["risk_level"]), ("CHILD_IMPERSONATION", "HIGH"))  # BE: 가족 확인 요청

    def test_need_explain_summary_is_easy_text(self):
        r = alert("[행복아파트] 10월 관리비 245,300원이 자동이체될 예정입니다.")
        check(self, r)
        self.assertEqual((r["classification"], r["requires_attention"]), ("NEED_EXPLAIN", False))
        self.assertIn("관리비", r["summary"])

    def test_safe(self):
        r = alert("오늘 저녁에 같이 밥 먹을까?")
        check(self, r)
        self.assertEqual(r["classification"], "SAFE")

    def test_validation(self):
        self.assertEqual(c.post("/v1/alerts/analyze", json={"text": ""}).status_code, 422)
        self.assertEqual(c.post("/v1/alerts/analyze", json={}).status_code, 422)

    def test_llm_garbage_is_not_safe(self):
        with mock.patch.object(llm, "complete_json", return_value=({"category": "모름"}, "fake")):
            r = alert("[서울중앙지검] 귀하 명의가 금융범죄에 도용되었습니다 http://spo-check.xyz")
        self.assertEqual(r["classification"], "SCAM")


class Call(unittest.TestCase):
    def test_call_shape_and_instructions(self):
        with open(CALLS / "prosecutor_1.txt", "rb") as f:
            r = c.post("/v1/calls/analyze", files={"file": ("prosecutor_1.txt", f)})
        self.assertEqual(r.status_code, 200, r.text)
        r = r.json()
        self.assertEqual(set(r), ALERT_KEYS | {"instructions"})
        check(self, r)
        types = {i["instruction_type"] for i in r["instructions"]}
        self.assertTrue({"INSTALL_APP", "TRANSFER"} <= types <= INSTR)
        self.assertTrue(all(set(i) == {"instruction_type", "description"} for i in r["instructions"]))
        self.assertIn("검찰청 보안", next(i["description"] for i in r["instructions"] if i["instruction_type"] == "INSTALL_APP"))
        self.assertNotIn("김순자", json.dumps(r, ensure_ascii=False))  # 이름은 가린다

    def test_instructions_only_from_other_party(self):
        talk = ("상대: 서울중앙지검 수사관입니다. 보안 앱을 설치하세요.\n"
                "부모님: 이체요? 현금으로 찾아야 하나요? 팀뷰어가 뭔데요?\n"
                "상대: 아니요, 앱만 깔면 됩니다.")
        r = call_text(talk).json()
        self.assertEqual([i["instruction_type"] for i in r["instructions"]], ["INSTALL_APP"])  # 부모님이 되물은 건 지시 아님

    def test_normal_call(self):
        with open(CALLS / "normal.txt", "rb") as f:
            r = c.post("/v1/calls/analyze", files={"file": ("normal.txt", f)}).json()
        self.assertEqual((r["classification"], r["requires_attention"], r["instructions"]), ("SAFE", False, []))

    def test_file_checks(self):
        self.assertEqual(call_text(b"x", "a.exe").status_code, 415)
        self.assertEqual(call_text(b"", "a.m4a").status_code, 400)
        self.assertEqual(call_text(b"audio", "a.m4a").status_code, 503)  # 음성 엔진 없음 (테스트 환경)


class Key(unittest.TestCase):
    def test_server_key(self):
        with mock.patch.dict(os.environ, {"AI_SERVER_KEY": "secret"}):
            body = {"text": "안녕하세요"}
            self.assertEqual(c.post("/v1/alerts/analyze", json=body).status_code, 401)
            self.assertEqual(c.post("/v1/alerts/analyze", json=body, headers={"X-AI-Key": "secret"}).status_code, 200)
        self.assertTrue(c.get("/health").json()["ok"])

    def test_old_paths_are_gone(self):
        for path in ("/v1/analyze/message", "/v1/analyze/call", "/v1/transcribe"):
            self.assertEqual(c.post(path, json={}).status_code, 404, path)


if __name__ == "__main__":
    unittest.main()
