"""평가 데이터 불러오기·나누기·비교표 (외부 데이터 형식이 달라도 같은 모양으로)."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ai import classifier  # noqa: E402
from ai.dataset import dedup, load, norm_label, text_key  # noqa: E402
from scripts.eval_ai import evaluate, metrics  # noqa: E402


class Load(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())

    def test_csv_korean_columns(self):
        (self.d / "a.csv").write_text("번호,문자,라벨\n1,[택배] 주소 확인 http://x.xyz,1\n2,내일 봐요,0\n", encoding="utf-8-sig")
        rows = load(str(self.d / "a.csv"))
        self.assertEqual([r["expect"] for r in rows], ["scam", "safe"])

    def test_txt_needs_label_and_known_flag(self):
        (self.d / "n.txt").write_text("김장 언제 해?\n\n반찬 잘 먹었어\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            load(str(self.d / "n.txt"))
        rows = load(f"{self.d / 'n.txt'}:safe:known")
        self.assertEqual(len(rows), 2)  # 빈 줄은 건너뜀
        self.assertTrue(all(r["known"] and r["expect"] == "safe" for r in rows))

    def test_jsonl_known_from_sender(self):
        (self.d / "t.jsonl").write_text(json.dumps({"content": "안녕", "expect": "safe", "sender": "010-1234-5678"}) + "\n")
        self.assertTrue(load(str(self.d / "t.jsonl"), {"01012345678"})[0]["known"])

    def test_labels_and_dedup(self):
        self.assertEqual(norm_label("스미싱"), "scam")
        self.assertEqual(norm_label("ham"), "safe")
        with self.assertRaises(ValueError):
            norm_label("?")
        self.assertEqual(text_key("택배 확인!"), text_key("택배확인"))
        self.assertEqual(len(dedup([{"text": "a b"}, {"text": "ab"}])), 1)


class Compare(unittest.TestCase):
    ROWS = [{"text": "[택배] 주소 불일치 확인 http://x.xyz", "expect": "scam", "known": False},
            {"text": "내일 노래교실 10시", "expect": "safe", "known": True}]

    def test_rule_engine(self):
        preds, _ = evaluate("rule", self.ROWS, 0)
        m = metrics(self.ROWS, preds, [1, 1], binary_only=True)
        self.assertEqual((m["recall"], m["false_alarm"], m["acc4"]), (1.0, 0.0, None))

    def test_model_engine_uses_classifier(self):
        with mock.patch.object(classifier, "danger_scores", return_value=[0.9, 0.2]):
            preds, _ = evaluate("model", self.ROWS, 0)
        self.assertEqual(preds, ["scam", "safe"])


if __name__ == "__main__":
    unittest.main()


class SenderKind(unittest.TestCase):
    """보낸 번호 '종류'만 판단에 쓴다 (번호 자체는 가림). 공식 대표번호의 링크 안내 ≠ 사기."""

    def test_kinds(self):
        from ai.privacy import sender_kind
        cases = {"010-1234-5678": "personal", "1588-0000": "business", "02-1588-0000": "landline",
                 "[국외발신]": "international", "+1 555 0100": "international", "070-1234-5678": "internet",
                 "114": "short", "민수": "name", "": "unknown", "+82 10-1234-5678": "personal"}
        for s, k in cases.items():
            self.assertEqual(sender_kind(s), k, s)

    def test_business_link_notice_is_explained_not_blocked(self):
        from ai import rules
        notice = "[계정안내] 새로운 기기에서 로그인이 시도되었습니다. 본인이 아닐 경우 즉시 확인해 주십시오. https://security.portal.example"
        biz = rules.analyze({"type": "message", "content": notice}, {"sender_kind": "business"})
        personal = rules.analyze({"type": "message", "content": notice}, {"sender_kind": "personal"})
        self.assertEqual((biz["category"], personal["category"]), ("need_explain", "scam"))
        self.assertIn("앱이나 대표번호", biz["explain"])

    def test_business_number_still_scam_for_strong_signals(self):
        from ai import rules
        for text in ("[서울중앙지검] 귀하 명의가 금융범죄에 도용되었습니다 http://spo.example",
                     "연 2.9% 햇살론 특별 승인 대상자입니다. 신청 kakao-loan.site/apply",
                     "보안 강화를 위해 원격 지원 앱 팀뷰어를 설치해 주세요 http://help.example"):
            self.assertEqual(rules.analyze({"type": "message", "content": text}, {"sender_kind": "business"})["category"], "scam", text)

    def test_long_tld_link(self):
        from ai.privacy import URL_RE
        self.assertTrue(URL_RE.search("반송 예정. k-gov.delivery-check.example"))
        self.assertFalse(URL_RE.search("최신 버전(v4.2.1)으로 업데이트"))
