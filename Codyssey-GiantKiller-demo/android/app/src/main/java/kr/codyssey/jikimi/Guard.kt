package kr.codyssey.jikimi

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.net.Uri
import android.provider.ContactsContract

/**
 * 폰 안 필터 + 가리기. ai/prefilter.py 와 같은 규칙.
 * 여기서 걸러진 메시지는 서버로 보내지 않는다.
 */
object Guard {
    private val RISK_WORDS = listOf(
        "엄마", "아빠", "급해", "급하게", "폰 고장", "액정", "이 번호", "상품권", "송금", "이체", "입금", "계좌",
        "대출", "검찰", "경찰", "수사", "금감원", "금융감독원", "택배", "배송", "주소지", "지원금", "환급",
        "자동이체", "자동결제", "결제", "승인", "청구", "납부", "인증번호", "앱", "설치",
    )
    private val LINK = Regex("""https?://|www\.|(?<![\w.@])(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,13}\b""")
    private val PHONE_LIKE = Regex("""^[\d\s+()\-.]{3,}$""")

    // 진짜 자녀 번호에서 온 문자에는 위험 단어로 치지 않는 말 (ai/prefilter.py PARENT_WORDS 와 같음)
    val PARENT_WORDS = setOf("엄마", "아빠")

    data class Verdict(val pass: Boolean, val why: String)

    /** 숫자만, +82 → 0 (서버 db.sender_key 와 같게) */
    fun digits(s: String): String {
        val d = s.filter { it.isDigit() }
        return if (d.startsWith("82") && d.length >= 10) "0" + d.substring(2) else d
    }

    /** 걸린 위험 단어 (없으면 null). 자녀 번호에서 온 문자면 '엄마'·'아빠'는 빼고 본다 — ai/prefilter.py risk_word 와 같음 */
    fun riskWord(text: String, fromChild: Boolean): String? =
        RISK_WORDS.firstOrNull { text.contains(it) && !(fromChild && it in PARENT_WORDS) }

    /**
     * 아는 번호인가. 문자 앱 알림 제목은 저장된 연락처면 이름, 아니면 번호로 뜬다.
     * 그래서 제목이 번호 모양이 아니면 '아는 사람'으로 본다.
     */
    fun isKnown(ctx: Context, title: String): Boolean {
        if (!PHONE_LIKE.matches(title)) return true
        if (ctx.checkSelfPermission(Manifest.permission.READ_CONTACTS) != PackageManager.PERMISSION_GRANTED) return false
        val uri = Uri.withAppendedPath(ContactsContract.PhoneLookup.CONTENT_FILTER_URI, Uri.encode(title))
        return ctx.contentResolver.query(uri, arrayOf(ContactsContract.PhoneLookup._ID), null, null, null)
            ?.use { it.count > 0 } ?: false
    }

    @Volatile private var light: LightModel? = null

    /** 가벼운 1차 모델 (assets/light_model.bin). 없거나 읽기 실패면 null → 예전 규칙 */
    fun lightModel(ctx: Context): LightModel? = light ?: runCatching {
        ctx.assets.open("light_model.bin").use { LightModel.parse(it.readBytes()) }
    }.getOrNull()?.also { light = it }

    /**
     * 서버로 보낼지 정한다 (ai/prefilter.py 와 같은 규칙).
     * 모델이 있으면: 위험 단어(안내 단어 포함) OR 링크 OR 모델 점수 ≥ 낮은 기준 → 보냄.
     *   저장 안 된 번호라도 셋 다 아니면 폰에 남긴다 (평범한 문자를 폰 밖으로 안 내보내기)
     * 모델이 없으면: 저장 안 된 번호는 무조건 보냄.
     */
    fun prefilter(ctx: Context, title: String, text: String): Verdict {
        val known = isKnown(ctx, title)
        val model = lightModel(ctx)
        if (model == null && !known) return Verdict(true, "저장 안 된 번호")
        if (LINK.containsMatchIn(text)) return Verdict(true, "링크 포함")
        // BE 는 가족 전화번호를 갖고 있지 않아 '진짜 자녀 번호' 구분은 하지 않는다 (fromChild = false)
        val fromChild = false
        riskWord(text, fromChild)?.let { return Verdict(true, "위험 단어 '$it'") }
        if (model != null) {
            val score = model.score(text)
            if (score >= model.gate) return Verdict(true, "1차 모델 점수 ${"%.2f".format(score)}")
            return Verdict(false, "${if (fromChild) "자녀" else if (known) "아는" else "저장 안 된"} 번호 · 링크·위험 단어 없음 · 1차 모델 ${"%.2f".format(score)}")
        }
        return Verdict(false, "${if (fromChild) "자녀" else "아는"} 번호 · 링크·위험 단어 없음")
    }

    fun mask(text: String): String {
        val urls = mutableListOf<String>()
        var t = Regex("""https?://\S+|www\.\S+""").replace(text) { urls += it.value; "\u0000${urls.size - 1}\u0000" }
        t = Regex("""(?<!\d)\d{6}[-\s]?[1-4]\d{6}(?!\d)""").replace(t, "[주민번호]")
        t = Regex("""(?<!\d)(?:\+?82[-\s]?)?0\d{1,2}[-\s.]?\d{3,4}[-\s.]?\d{4}(?!\d)""").replace(t, "[전화번호]")
        t = Regex("""(?<!\d)\d{2,6}(?:-\d{2,8}){1,3}(?!\d)|(?<!\d)\d{10,14}(?!\d)""").replace(t) {
            if (it.value.count { c -> c.isDigit() } >= 10) "[계좌번호]" else it.value
        }
        return Regex("\u0000(\\d+)\u0000").replace(t) { urls[it.groupValues[1].toInt()] }
    }
}
