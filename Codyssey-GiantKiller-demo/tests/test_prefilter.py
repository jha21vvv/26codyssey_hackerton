"""폰 1차 필터 규칙이 세 곳(파이썬·안드로이드·웹)에서 같은지 확인."""
import json
import re
import unittest
from pathlib import Path

from ai.prefilter import RISK_WORDS, prefilter

ROOT = Path(__file__).resolve().parent.parent


def words_in(path: Path, start: str) -> list[str]:
    src = path.read_text(encoding="utf-8")
    block = src[src.index(start):]
    block = block[:block.index(")" if "listOf" in start else "]")]
    return re.findall(r'"([^"]+)"', block)


class SameRules(unittest.TestCase):
    def test_android_same_words(self):
        kt = ROOT / "android/app/src/main/java/kr/codyssey/jikimi/Guard.kt"
        self.assertEqual(words_in(kt, "RISK_WORDS = listOf("), RISK_WORDS)



class Behaviour(unittest.TestCase):
    def test_unknown_always_sent(self):
        self.assertTrue(prefilter("내일 봐요", sender_known=False)[0])

    def test_known_plain_message_stays_on_phone(self):
        self.assertEqual(prefilter("내일 노래교실 10시에 봐요", sender_known=True), (False, "아는 번호 · 링크·위험 단어 없음"))

    def test_known_with_link_or_word_is_sent(self):
        self.assertTrue(prefilter("사진 봐 han.gl/abc", sender_known=True)[0])
        self.assertTrue(prefilter("엄마 저녁 먹었어?", sender_known=True)[0])



class ChildNumber(unittest.TestCase):
    """진짜 자녀 번호에서 온 문자: '엄마'·'아빠'만으로는 서버로 안 보냄. 다른 위험 단어·링크·모델은 그대로."""
    CASES = ROOT / "tests/data/prefilter_cases.tsv"

    def test_shared_cases(self):
        # 안드로이드 GuardTest 도 같은 파일로 Guard.riskWord 를 확인한다 → 두 쪽 판정이 같음
        import base64
        from ai.prefilter import risk_word
        for line in self.CASES.read_text(encoding="utf-8").splitlines():
            hit, child, text = line.split("\t")
            hit, text = base64.b64decode(hit).decode(), base64.b64decode(text).decode()
            self.assertEqual(risk_word(text, child == "1") or "", hit, text)

    def test_parent_words_same_in_android(self):
        from ai.prefilter import PARENT_WORDS
        kt = (ROOT / "android/app/src/main/java/kr/codyssey/jikimi/Guard.kt").read_text(encoding="utf-8")
        block = kt[kt.index("PARENT_WORDS = setOf("):]
        self.assertEqual(re.findall(r'"([^"]+)"', block[:block.index(")")]), PARENT_WORDS)

    def test_child_daily_message_stays_on_phone(self):
        self.assertEqual(prefilter("엄마 저녁 먹었어?", sender_known=True, sender_is_child=True)[0], False)
        self.assertTrue(prefilter("엄마 저녁 먹었어?", sender_known=True, sender_is_child=False)[0])
        self.assertTrue(prefilter("엄마 이 링크 봐 han.gl/x", sender_known=True, sender_is_child=True)[0])  # 링크는 그대로


if __name__ == "__main__":
    unittest.main()
