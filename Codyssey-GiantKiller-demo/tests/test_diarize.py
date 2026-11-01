"""화자 구분: 단어 ↔ 화자 구간 맞추기, '상대'/'부모님' 정하기 (pyannote·whisper 없이)."""
import unittest
from types import SimpleNamespace
from unittest import mock

from ai import diarize
from ai.rules import other_party
from ai.transcribe import clean_repeats


def words(*items):
    return [(s, e, w) for s, e, w in items]


class Merge(unittest.TestCase):
    TURNS = [(0.0, 1.0, "S0"), (1.2, 9.0, "S1"), (9.2, 10.0, "S0")]

    def test_merge_by_speaker(self):
        ws = words((0.1, 0.5, " 여보세요"), (1.3, 1.8, " 서울중앙지검"), (1.9, 2.5, " 수사관입니다."),
                   (3.0, 8.5, " 보안 앱을 설치하세요."), (9.3, 9.8, " 앱을요?"))
        segs = diarize.merge(ws, self.TURNS)
        self.assertEqual([s[2] for s in segs], ["S0", "S1", "S0"])
        self.assertEqual(segs[1][3], " 서울중앙지검 수사관입니다. 보안 앱을 설치하세요.")
        text = diarize.to_text(segs)
        self.assertEqual(text.splitlines()[0], "부모님: 여보세요")  # 적게 말한 쪽 = 부모님
        self.assertTrue(text.splitlines()[1].startswith("상대: 서울중앙지검"))
        # 규칙 판단은 '상대:' 줄만 본다 → 부모님의 "앱을요?" 는 지시가 아님
        self.assertNotIn("앱을요", other_party(text))

    def test_word_between_turns_goes_to_nearest(self):
        self.assertEqual(diarize.speaker_at(self.TURNS, 1.15, 1.18), "S1")

    def test_roles_similar_talk_first_is_parent(self):
        segs = [[0, 5, "A", "x"], [5, 10, "B", "y"]]
        self.assertEqual(diarize.roles(segs), {"A": "부모님", "B": "상대"})

    def test_roles_not_two_speakers(self):
        self.assertEqual(diarize.roles([[0, 1, "A", "x"]]), {"A": "화자1"})


class Repeats(unittest.TestCase):
    def test_clean_repeats(self):
        self.assertEqual(clean_repeats("검찰 사이트 보세요.\n네.\n네.\n네.\n중앙지검입니다."), "검찰 사이트 보세요.\n네.\n중앙지검입니다.")
        self.assertEqual(clean_repeats("부모님: 네. 네. 네. 네. 네."), "부모님: 네.")
        self.assertEqual(clean_repeats("상대: 앱 깔고 이체하세요."), "상대: 앱 깔고 이체하세요.")  # 반복 없으면 그대로


class Fallback(unittest.TestCase):
    def test_diarize_failure_returns_plain_text(self):
        seg = SimpleNamespace(text=" 안녕하세요 ", words=[SimpleNamespace(start=0, end=1, word=" 안녕하세요")])
        model = mock.Mock()
        model.transcribe.return_value = (iter([seg]), SimpleNamespace(duration=1.0))
        with mock.patch.object(diarize, "turns", side_effect=RuntimeError("HF_TOKEN 없음")):
            self.assertEqual(diarize.transcribe_with_speakers(model, "a.m4a"), ("안녕하세요", 1.0))
        with mock.patch.object(diarize, "turns", return_value=[(0, 1, "S0")]):
            model.transcribe.return_value = (iter([seg]), SimpleNamespace(duration=1.0))
            self.assertEqual(diarize.transcribe_with_speakers(model, "a.m4a")[0], "화자1: 안녕하세요")

    def test_enabled_flag(self):
        with mock.patch.dict("os.environ", {"WHISPER_DIARIZE": "1"}):
            self.assertTrue(diarize.enabled())
        with mock.patch.dict("os.environ", {"WHISPER_DIARIZE": "0"}):
            self.assertFalse(diarize.enabled())


if __name__ == "__main__":
    unittest.main()
