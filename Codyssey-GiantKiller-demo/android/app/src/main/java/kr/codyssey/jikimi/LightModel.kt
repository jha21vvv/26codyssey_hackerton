package kr.codyssey.jikimi

import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.exp
import kotlin.math.sqrt

/**
 * 가벼운 1차 모델 (폰 안에서 판단). ai/light_model.py 와 **같은 문자에 똑같은 점수**를 내야 한다.
 * 바꾸면 파이썬도 같이 바꾸고 scripts/train_light.py 로 고정 예시를 다시 만든다 (LightModelTest 가 확인).
 *
 * 글자 다듬기: 숫자 → '0', A-Z → a-z, 공백류 연속 → 스페이스 하나(앞뒤 제거)
 * 조각: 코드포인트 기준 nmin~nmax 글자 → UTF-8 → FNV-1a 32비트 → % dim
 * 점수: sigmoid(bias + scale × Σ q[idx] / √(조각 종류 수))
 * 안드로이드 의존 없이 순수 Kotlin (JVM 단위 테스트로 확인)
 */
class LightModel private constructor(
    private val q: ByteArray,
    private val scale: Double,
    private val bias: Double,
    val gate: Double,
    val cls: Double,
    private val dim: Int,
    private val nmin: Int,
    private val nmax: Int,
) {
    companion object {
        private val MAGIC = "JKLM".toByteArray(Charsets.US_ASCII)
        private val SPACES = setOf(' '.code, '\t'.code, '\r'.code, '\n'.code, 0x00A0, 0x3000)

        fun parse(data: ByteArray): LightModel {
            require(data.size >= 28 && data.copyOfRange(0, 4).contentEquals(MAGIC)) { "가벼운 모델 파일이 아니에요" }
            val b = ByteBuffer.wrap(data, 4, 24).order(ByteOrder.LITTLE_ENDIAN)
            val ver = b.short.toInt()
            require(ver == 1) { "모델 버전 $ver (지원 1)" }
            val nmin = b.get().toInt()
            val nmax = b.get().toInt()
            val dim = b.int
            val scale = b.float.toDouble()
            val bias = b.float.toDouble()
            val gate = b.float.toDouble()
            val cls = b.float.toDouble()
            return LightModel(data.copyOfRange(28, 28 + dim), scale, bias, gate, cls, dim, nmin, nmax)
        }

        fun normalize(text: String): IntArray {
            val out = ArrayList<Int>(text.length)
            var space = false
            text.codePoints().forEach { c0 ->
                var c = c0
                if (c in '0'.code..'9'.code) c = '0'.code
                else if (c in 'A'.code..'Z'.code) c += 32
                if (c in SPACES) {
                    space = true
                    return@forEach
                }
                if (space && out.isNotEmpty()) out.add(' '.code)
                space = false
                out.add(c)
            }
            return out.toIntArray()
        }

        fun fnv1a(data: ByteArray): Long {
            var h = 0x811C9DC5L
            for (byte in data) {
                h = h xor (byte.toLong() and 0xFF)
                h = (h * 0x01000193L) and 0xFFFFFFFFL
            }
            return h
        }
    }

    fun features(text: String): IntArray {
        val cps = normalize(text)
        val idx = HashSet<Int>()
        for (n in nmin..nmax) {
            for (i in 0..cps.size - n) {
                val piece = String(cps, i, n).toByteArray(Charsets.UTF_8)
                idx.add((fnv1a(piece) % dim).toInt())
            }
        }
        return idx.sorted().toIntArray()
    }

    fun score(text: String): Double {
        val idx = features(text)
        if (idx.isEmpty()) return 1.0 / (1.0 + exp(-bias))
        var s = 0L
        for (i in idx) s += q[i].toLong()  // ByteArray 는 부호 있는 int8
        val z = bias + scale * s / sqrt(idx.size.toDouble())
        return 1.0 / (1.0 + exp(-z))
    }
}
