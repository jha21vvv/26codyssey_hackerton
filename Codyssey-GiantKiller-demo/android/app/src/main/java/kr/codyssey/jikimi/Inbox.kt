package kr.codyssey.jikimi

import android.content.Context
import android.os.Handler
import android.os.Looper
import android.util.Log
import org.json.JSONObject

/**
 * 받은 문자·메신저 메시지를 한곳에서 처리: 폰 1차 필터 → (통과하면) 가려서 BE `/alerts/check` 로.
 * 문자는 두 길로 들어온다 — ① 문자 직접 받기(SmsReceiver) ② 문자 앱 알림(NotiListener).
 * 같은 문자가 두 번 처리되지 않게 최근 내용과 비교해 거른다. 알림이 잘려 있거나('…') 갱신돼 여러 번 와도 한 번만.
 */
object Inbox {
    private const val TAG = "jikimi"
    private const val KEEP_MS = 3 * 60_000L
    private val recent = ArrayDeque<Pair<Long, String>>() // (받은 시각, 공백 뺀 내용)

    private fun squash(s: String) = s.filterNot { it.isWhitespace() }.removeSuffix("…").removeSuffix("...")

    @Synchronized
    private fun seen(text: String): Boolean {
        val now = System.currentTimeMillis()
        while (recent.isNotEmpty() && now - recent.first().first > KEEP_MS) recent.removeFirst()
        val t = squash(text)
        if (t.isEmpty()) return true
        val dup = recent.any { (_, r) -> r == t || (minOf(r.length, t.length) >= 10 && (r.startsWith(t) || t.startsWith(r))) }
        if (!dup) recent.addLast(now to t)
        return dup
    }

    /** sender: 번호(문자 직접 받기) 또는 알림 제목(연락처 이름일 수 있음) — 폰 1차 필터에만 쓰고 서버로는 안 보낸다. via: 로그용 */
    fun handle(ctx: Context, sender: String, text: String, via: String, skipSeen: Boolean = false) {
        if (Prefs.role(ctx) != "parent" || Prefs.family(ctx).isEmpty()) return // 부모님 폰으로 연결된 뒤에만
        if (!skipSeen && seen(text)) {
            Log.i(TAG, "$via 이미 처리한 메시지")
            return
        }
        val verdict = Guard.prefilter(ctx, sender, text)
        Log.i(TAG, "$via → ${verdict.why}")
        if (!verdict.pass) return // 평범한 메시지는 폰 밖으로 내보내지 않는다
        Api.io.execute {
            try {
                val r = Api.checkAlert(ctx, Guard.mask(text))
                val result = r.getJSONObject("result")
                Log.i(TAG, "판단 ${result.optString("classification")} 주의=${result.optBoolean("requires_attention")}")
                Reactions.message(ctx, result, r.optString("verification_id").takeIf { it.isNotEmpty() && it != "null" }, text,
                    eventId = r.optString("event_id"))
            } catch (e: Exception) {
                Log.w(TAG, "서버 전송 실패: ${e.message}")
            }
        }
    }
}

/**
 * BE 판단 결과를 받은 부모님 폰이 화면에 보여 주는 것.
 * BE 는 부모님께 사기 경고 푸시를 보내지 않으므로(자녀에게만 RISK_WARNING) 응답을 보고 폰이 직접 띄운다.
 * 가족 확인 중/결과 문구는 BE 푸시 문구(VERIFY_*)와 같게.
 */
object Reactions {
    private const val TAG = "jikimi"
    private val main = Handler(Looper.getMainLooper())

    private fun hasLink(s: String) = Regex("""https?://|www\.|\.[a-z]{2,}/""", RegexOption.IGNORE_CASE).containsMatchIn(s)

    /**
     * 같은 사건(BE event_id)의 경고는 한 번만. 통화 업로드 응답과 (나중에 BE 가 보낼) 부모님 푸시처럼 두 길로 와도 같은 규칙이 먹게
     * 경고창·안내 카드를 띄우는 곳은 모두 이걸 먼저 부른다. 띄운 id 는 최근 50개를 폰에 기억(앱을 껐다 켜도). id 가 없으면 그냥 띄운다
     */
    @Synchronized
    fun firstTime(ctx: Context, eventId: String?): Boolean {
        if (eventId.isNullOrEmpty() || eventId == "null") return true
        if (Prefs.testMode(ctx)) return true // 테스트 모드 예시 사건 id 는 겹친다 (앱을 다시 켜면 e1… 부터, 통화는 늘 e2) → 시험 버튼은 매번 뜨게
        val shown = Prefs.shownEvents(ctx)
        if (eventId in shown) {
            Log.i(TAG, "이미 경고를 띄운 사건이라 건너뜀")
            return false
        }
        Prefs.set(ctx, "shown_events" to (listOf(eventId) + shown).take(50).joinToString(","))
        return true
    }

    /** text: 폰이 받은 문자 (제목을 '링크를 누르지 마세요'로 할지 정하는 데만 쓴다 — BE 응답엔 원문이 없다) */
    fun message(ctx: Context, result: JSONObject, verificationId: String?, text: String = "", eventId: String? = null) {
        val shows = result.optString("classification") == "CHILD_IMPERSONATION" || result.optBoolean("requires_attention")
        if (shows && !firstTime(ctx, eventId)) return
        val summary = result.optString("summary").takeIf { it.isNotEmpty() && it != "null" }
        when {
            result.optString("classification") == "CHILD_IMPERSONATION" -> {
                InfoCard.show(ctx, "가족에게 확인 중이에요", "송금·앱 설치·인증번호 전달을 잠시 멈춰주세요.", Ui.Stage.CAUTION, key = verificationId)
                verificationId?.let { watch(ctx, it) }
            }
            result.optBoolean("requires_attention") -> Overlay.show(ctx,
                if (hasLink(text) || (summary != null && hasLink(summary))) "이 링크를 누르지 마세요" else "답장하지 마세요",
                (summary ?: "사기로 의심되는 문자예요.") + "\n\n자녀에게 알려드렸어요.", "알겠어요")
            // NORMAL(평범한 문자·정상 안내)은 아무것도 띄우지 않는다. BE 분류는 CHILD_IMPERSONATION · FRAUD · NORMAL 셋뿐
        }
    }

    fun call(ctx: Context, result: JSONObject, eventId: String? = null) {
        if (!firstTime(ctx, eventId)) return
        Overlay.show(ctx, "전화로 시킨 일은 멈춰주세요",
            (result.optString("summary").takeIf { it.isNotEmpty() && it != "null" } ?: "사기로 의심되는 통화예요.") +
                "\n\n돈을 보내거나 앱을 설치하지 마세요.\n개인정보를 알려주지 마세요.\n\n자녀에게 알려드렸어요.", "알겠어요")
    }

    /** BE 원격 제어 앱 규칙 그대로 (BE app/services/app_install.py REMOTE_PACKAGE_PREFIXES) */
    private val REMOTE_PREFIXES = listOf("com.teamviewer.", "com.anydesk.", "com.rsupport.")

    /**
     * 설치 경고. BE 는 위험 여부·최근 24시간 의심 통화 여부만 주므로, 위험으로 본 이유(원격 제어 앱 / 스토어 밖 설치)는 폰이 안다.
     * 문구: 원격 제어 앱이 가장 위험해서 먼저 → 아니면 의심 통화 뒤 설치 → 아니면 스토어 밖 설치. 의심 통화는 원격 제어 앱 문구 앞에도 붙인다
     */
    fun install(ctx: Context, label: String, pkg: String, unknownSource: Boolean, relatedCall: Boolean, eventId: String? = null) {
        if (!firstTime(ctx, eventId)) return
        val remote = REMOTE_PREFIXES.any { pkg.startsWith(it) }
        val why = when {
            remote -> (if (relatedCall) "의심 통화 뒤에 " else "") + "'$label' 앱이 설치됐어요.\n원격 제어 앱이라 다른 사람이 이 폰을 마음대로 조작할 수 있어요."
            relatedCall -> "의심 통화 뒤에 '$label' 앱 설치가 감지됐어요."
            unknownSource -> "공식 앱 스토어가 아닌 곳에서 '$label' 앱이 설치됐어요."
            else -> "'$label' 앱 설치가 감지됐어요."
        }
        Overlay.show(ctx, "이 앱을 열지 마세요",
            "$why\n앱을 열지 말고 자녀의 연락을 기다려 주세요.\n\n자녀에게 긴급 알림을 보냈어요.", "알겠어요")
    }

    /** 가족 확인 결과를 기다린다 (BE GET /verify/{id}). 푸시가 없어도 부모님 폰에 결과가 뜨도록 몇 초마다 확인 */
    private fun watch(ctx: Context, id: String, tries: Int = 0) {
        if (tries > 140) return // 약 12분 (BE 응답 기한 10분)
        main.postDelayed({
            Api.io.execute {
                val status = runCatching { Api.verification(ctx, id).optString("status") }.getOrNull()
                Log.i(TAG, "가족 확인 $status")
                when (status) {
                    "CONFIRMED" -> InfoCard.show(ctx, "자녀가 발송을 확인했어요", "메시지나 링크의 안전을 보장하는 것은 아니에요.", key = id)
                    // 부인: 경고창은 카드와 다른 창이라, 떠 있던 같은 건의 "확인 중" 카드를 먼저 닫는다
                    // (확인됨·만료는 카드끼리라 새 카드가 자리를 바꿔 차지한다)
                    "DENIED" -> {
                        InfoCard.dismiss(ctx, id)
                        Overlay.show(ctx, "가족 전원이 발송을 부인했어요",
                            "위험 행동을 멈추고 기존에 알고 있던 연락처로 직접 확인해주세요.", "알겠어요")
                    }
                    "EXPIRED" -> InfoCard.show(ctx, "가족에게 확인하지 못했어요", "기존에 알고 있던 연락처나 다른 가족을 통해 확인해주세요.", Ui.Stage.CAUTION, key = id)
                    else -> watch(ctx, id, tries + 1)
                }
            }
        }, 5000)
    }
}
