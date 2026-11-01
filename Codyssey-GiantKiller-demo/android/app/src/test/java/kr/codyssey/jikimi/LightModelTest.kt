package kr.codyssey.jikimi

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.util.Base64

/**
 * 파이썬(ai/light_model.py)과 안드로이드(LightModel.kt)가 같은 문자에 같은 점수를 내는지.
 * 고정 예시는 scripts/train_light.py 가 만든다 (tests/data/light_examples.tsv).
 *     cd android && ./gradlew :app:testDebugUnitTest
 */
class LightModelTest {
    private val model = LightModel.parse(File("src/main/assets/light_model.bin").readBytes())
    private val examples = File("../../tests/data/light_examples.tsv").readLines().filter { it.isNotBlank() }.map {
        val (score, b64) = it.split("\t")
        String(Base64.getDecoder().decode(b64), Charsets.UTF_8) to score.toDouble()
    }

    @Test
    fun sameScoresAsPython() {
        assertTrue(examples.size >= 10)
        for ((text, expected) in examples) {
            assertEquals("점수가 파이썬과 다름: [$text]", expected, model.score(text), 1e-9)
        }
    }

    @Test
    fun hashAndNormalizeBasics() {
        assertEquals(0x811C9DC5L, LightModel.fnv1a(ByteArray(0)))
        assertEquals(0xE40C292CL, LightModel.fnv1a("a".toByteArray()))  // FNV-1a 32비트 표준값
        val n = LightModel.normalize("  A1\t\tb ")
        assertEquals("a0 b", String(n, 0, n.size))
    }

    @Test
    fun gateIsLow() {
        assertTrue("1차 통과 기준은 낮아야 함 (애매하면 서버로)", model.gate <= 0.3 + 1e-6)
    }
}
