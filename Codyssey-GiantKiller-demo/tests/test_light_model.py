"""가벼운 1차 모델: 파일 읽기, 고정 예시 점수(안드로이드 LightModelTest 와 같은 값), 1차 필터 결합 규칙."""
import json
import unittest
from pathlib import Path

from ai.light_model import LightModel, features, fnv1a, normalize, quantize, train
from ai.prefilter import prefilter

ROOT = Path(__file__).resolve().parent.parent
ASSET = ROOT / "android/app/src/main/assets/light_model.bin"
EXAMPLES = ROOT / "tests/data/light_examples.json"


class Basics(unittest.TestCase):
    def test_hash_and_normalize(self):
        self.assertEqual(fnv1a(b""), 0x811C9DC5)
        self.assertEqual(fnv1a(b"a"), 0xE40C292C)  # FNV-1a 32비트 표준값 (Kotlin 테스트와 같음)
        self.assertEqual(normalize("  A1\t\tb "), "a0 b")
        self.assertEqual(normalize("택배 2026-10-30"), "택배 0000-00-00")
        self.assertEqual(features(""), [])

    def test_save_load_roundtrip(self):
        m = quantize([0.5, -1.0, 0.25, 0.0], 0.1, gate=0.2)
        p = Path(__file__).parent / "_tmp_light.bin"
        try:
            m.save(p)
            m2 = LightModel.load(p)
            self.assertEqual((m2.q, m2.scale, m2.bias, m2.gate, m2.dim), (m.q, m.scale, m.bias, m.gate, 4))
        finally:
            p.unlink(missing_ok=True)

    def test_tiny_training_separates(self):
        xs = ["카지노 첫충 보너스 가입코드"] * 20 + ["오늘 저녁 뭐 먹을까"] * 20
        ys = [1] * 20 + [0] * 20
        m = quantize(*train(xs, ys, epochs=3, dim=1 << 12))
        self.assertGreater(m.score("카지노 가입코드 이벤트"), 0.5)
        self.assertLess(m.score("저녁 뭐 먹을까요"), 0.5)


@unittest.skipUnless(ASSET.exists(), "학습한 모델 없음 (scripts/train_light.py)")
class Trained(unittest.TestCase):
    def setUp(self):
        self.m = LightModel.load(ASSET)

    def test_examples_match(self):
        # 안드로이드 LightModelTest 도 같은 예시·같은 점수를 확인한다 → 두 쪽 점수가 같음
        for ex in json.loads(EXAMPLES.read_text(encoding="utf-8")):
            self.assertAlmostEqual(self.m.score(ex["text"]), ex["score"], places=12, msg=ex["text"])

    def test_gate_is_low(self):
        self.assertLessEqual(self.m.gate, 0.3 + 1e-6)

    def test_combined_prefilter(self):
        m = self.m
        # 위험 단어·링크는 모델과 상관없이 보낸다
        self.assertTrue(prefilter("엄마 나 폰 고장났어", sender_known=True, model=m)[0])
        self.assertTrue(prefilter("사진 봐 han.gl/abc", sender_known=False, model=m)[0])
        # 모델이 있으면 저장 안 된 번호의 평범한 문자는 폰에 남을 수 있다
        sent, why = prefilter("오늘 날씨 좋네요 산책 가요", sender_known=False, model=m)
        self.assertFalse(sent, why)
        # 모델이 없으면 예전 규칙 (저장 안 된 번호 = 무조건 보냄)
        self.assertTrue(prefilter("오늘 날씨 좋네요 산책 가요", sender_known=False)[0])


if __name__ == "__main__":
    unittest.main()
