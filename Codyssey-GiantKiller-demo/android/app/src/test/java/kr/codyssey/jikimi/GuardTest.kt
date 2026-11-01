package kr.codyssey.jikimi

import org.junit.Assert.assertEquals
import org.junit.Test
import java.io.File
import java.util.Base64

/** 1차 필터 위험 단어 판정이 파이썬(ai/prefilter.py risk_word)과 같은지 — tests/data/prefilter_cases.tsv 공유 */
class GuardTest {
    private fun b64(s: String) = String(Base64.getDecoder().decode(s), Charsets.UTF_8)

    @Test
    fun sameRiskWordsAsPython() {
        val lines = File("../../tests/data/prefilter_cases.tsv").readLines().filter { it.isNotBlank() }
        for (line in lines) {
            val (hit, child, text) = line.split("\t")
            assertEquals("[${b64(text)}]", b64(hit), Guard.riskWord(b64(text), child == "1") ?: "")
        }
    }

    @Test
    fun digitsLikeServer() {
        assertEquals("01012345678", Guard.digits("+82 10-1234-5678"))
        assertEquals("01012345678", Guard.digits("010-1234-5678"))
    }
}
