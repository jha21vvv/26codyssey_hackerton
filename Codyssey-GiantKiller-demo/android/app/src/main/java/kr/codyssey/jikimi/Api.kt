package kr.codyssey.jikimi

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.time.OffsetDateTime
import java.util.UUID
import java.util.concurrent.Executors

/** 이 폰의 역할·로그인·가족 (서버 주소는 빌드 설정값) */
object Prefs {
    private fun sp(ctx: Context) = ctx.getSharedPreferences("jikimi", 0)
    private fun str(ctx: Context, k: String, def: String = "") = sp(ctx).getString(k, def)!!

    /** BE 서버 주소: 빌드 설정값 (android/gradle.properties 의 jikimi.serverUrl → 리소스 server_url). 바꾸려면 그 값을 고쳐 다시 빌드 */
    fun server(ctx: Context) = ctx.getString(R.string.server_url).trimEnd('/')
    fun role(ctx: Context) = str(ctx, "role")              // "" | parent | child
    fun token(ctx: Context) = str(ctx, "token")            // BE 로그인 JWT (Bearer)
    fun name(ctx: Context) = str(ctx, "name")              // 내 계정 이름
    fun userId(ctx: Context) = str(ctx, "user_id")         // 내 계정 ID (가족 대표인지 확인)
    fun testMode(ctx: Context) = str(ctx, "test_mode") == "1" // 로그인·서버 없이 둘러보기 (Demo.kt)
    fun family(ctx: Context) = str(ctx, "family")          // 참여한 가족 ID (BE UUID)
    fun parentTitle(ctx: Context) = str(ctx, "parent_title", "부모님") // 자녀 화면에 쓰는 부모님 이름 (가족 멤버 이름)
    fun fid(ctx: Context) = str(ctx, "fid")                // BE 에 등록한 FCM FID
    fun lastAudio(ctx: Context) = str(ctx, "last_audio", "-1").toLongOrNull() ?: -1L
    /** 자녀 폰: 푸시로 받은 가족 확인 요청 ID 들 (BE 에 목록 API 가 없어 폰이 기억한다) */
    fun verifications(ctx: Context): List<String> = str(ctx, "verifications").split(',').filter { it.isNotEmpty() }
    fun shownEvents(ctx: Context): List<String> = str(ctx, "shown_events").split(',').filter { it.isNotEmpty() } // 경고를 띄운 사건 (최근 50개)

    fun addVerification(ctx: Context, id: String) =
        set(ctx, "verifications" to (listOf(id) + verifications(ctx).filter { it != id }).take(20).joinToString(","))

    fun set(ctx: Context, vararg kv: Pair<String, Any?>) {
        sp(ctx).edit().apply {
            for ((k, v) in kv) when (v) {
                null -> remove(k)
                is Int -> putInt(k, v)
                else -> putString(k, v.toString().trim())
            }
        }.apply()
    }

    /** 로그아웃: 이 폰에 저장한 것을 모두 지운다 */
    fun reset(ctx: Context) {
        sp(ctx).edit().clear().apply()
    }
}

/**
 * 백엔드(BE 레포 ted1117/Codyssey-GiantKiller-BE) API. 네트워크는 메인 스레드에서 못 쓰므로 io 에서 부른다.
 * 로그인하면 받은 JWT 를 모든 요청에 `Authorization: Bearer` 로 보낸다. 만료되면(401) 다시 로그인한다.
 */
object Api {
    val io = Executors.newCachedThreadPool()

    class HttpError(val code: Int, val detail: String) : RuntimeException("HTTP $code $detail")

    /**
     * 통화 분석 응답 대기 95초: 서버(CPU 2개) Whisper 받아쓰기가 47초 녹음에도 60초를 넘겼다(10/31 22:20 갤럭시).
     * cloudflare 임시 주소가 한 요청을 100초까지만 잡아줘서 그 안으로
     */
    private const val CALL_READ_MS = 95_000

    /** readMs: 응답 기다리는 시간. 통화 분석만 길게 (CALL_READ_MS), 나머지는 60초 그대로 */
    private fun open(ctx: Context, path: String, method: String, readMs: Int = 60_000): HttpURLConnection =
        (URL(Prefs.server(ctx) + path).openConnection() as HttpURLConnection).apply {
            requestMethod = method
            connectTimeout = 5000
            readTimeout = readMs
            Prefs.token(ctx).takeIf { it.isNotEmpty() }?.let { setRequestProperty("Authorization", "Bearer $it") }
        }

    /** ctx 를 주면 401(로그인 만료) 때 토큰을 지우고 로그인 화면·알림으로 (Session) */
    private fun read(c: HttpURLConnection, ctx: Context? = null): String {
        val code = c.responseCode
        val body = (if (code < 400) c.inputStream else c.errorStream)?.bufferedReader()?.readText() ?: ""
        if (code == 401 && ctx != null) Session.expired(ctx)
        if (code >= 400) {
            val detail = runCatching { JSONObject(body).opt("detail")?.toString() ?: body }.getOrDefault(body)
            throw HttpError(code, detail)
        }
        return body
    }

    fun get(ctx: Context, path: String): String =
        if (Prefs.testMode(ctx)) Demo.handle(ctx, "GET", path, null) else read(open(ctx, path, "GET"), ctx)

    private fun send(ctx: Context, method: String, path: String, body: JSONObject?): String {
        if (Prefs.testMode(ctx)) return Demo.handle(ctx, method, path, body)
        val c = open(ctx, path, method)
        if (body != null) {
            c.doOutput = true
            c.setRequestProperty("Content-Type", "application/json; charset=utf-8")
            c.outputStream.use { it.write(body.toString().toByteArray()) }
        }
        return read(c, ctx)
    }

    fun post(ctx: Context, path: String, body: JSONObject? = null): JSONObject =
        send(ctx, "POST", path, body).let { if (it.isBlank()) JSONObject() else JSONObject(it) }

    private fun now() = OffsetDateTime.now().toString()

    // ── 계정 (FastAPI Users) ──
    fun register(ctx: Context, email: String, password: String, name: String) {
        post(ctx, "/api/v1/auth/register", JSONObject().put("email", email).put("password", password).put("name", name))
    }

    /** 로그인: form 으로 username=이메일 → JWT 저장 */
    fun login(ctx: Context, email: String, password: String) {
        val c = open(ctx, "/api/v1/auth/login", "POST").apply {
            doOutput = true
            setRequestProperty("Content-Type", "application/x-www-form-urlencoded")
        }
        val form = "username=${URLEncoder.encode(email, "UTF-8")}&password=${URLEncoder.encode(password, "UTF-8")}"
        c.outputStream.use { it.write(form.toByteArray()) }
        Prefs.set(ctx, "token" to JSONObject(read(c)).getString("access_token"))
        val me = me(ctx)
        Prefs.set(ctx, "name" to me.optString("name"), "user_id" to me.optString("id"))
    }

    fun me(ctx: Context): JSONObject = JSONObject(get(ctx, "/api/v1/users/me"))

    // ── 가족·초대 ──
    /** 가족 만들기: 만든 사람(자녀)이 대표가 된다 */
    fun createFamily(ctx: Context): JSONObject = post(ctx, "/api/v1/families")

    fun families(ctx: Context): JSONArray = JSONArray(get(ctx, "/api/v1/families"))

    fun family(ctx: Context, id: String = Prefs.family(ctx)): JSONObject = JSONObject(get(ctx, "/api/v1/families/$id"))

    /** 초대 만들기 (대표만): role = PARENT | CHILD → invite_url, expires_at */
    fun invite(ctx: Context, role: String): JSONObject =
        post(ctx, "/api/v1/families/${Prefs.family(ctx)}/invitations", JSONObject().put("role", role))

    /** 초대 취소 (대표만, 아직 안 쓴 초대): 만들 때 받은 id → 204. 이미 취소된 초대를 또 취소해도 204 */
    fun revokeInvite(ctx: Context, invitationId: String) {
        send(ctx, "DELETE", "/api/v1/families/${Prefs.family(ctx)}/invitations/$invitationId", null)
    }

    /**
     * 초대 코드 = BE 초대 토큰 (invite_url 끝부분, 영문·숫자·-·_ 43자). 화면에는 이 코드만 보여 주고 주고받는다.
     * 받은 쪽은 코드만, 공유 메시지 통째로, 예전 링크 어느 것을 붙여 넣어도 코드만 골라낸다
     */
    fun inviteToken(input: String): String {
        val s = input.trim()
        Regex("""[A-Za-z0-9_-]{20,}""").findAll(s).lastOrNull()?.let { return it.value }
        return s.trimEnd('/').substringAfterLast('/').substringBefore('?')
    }

    fun previewInvite(ctx: Context, token: String): JSONObject = JSONObject(get(ctx, "/api/v1/invitations/$token"))

    fun acceptInvite(ctx: Context, token: String): JSONObject = post(ctx, "/api/v1/invitations/$token/accept")

    // ── 푸시 (FCM FID) ──
    fun registerFid(ctx: Context, fid: String, previous: String?) {
        send(ctx, "PUT", "/api/v1/users/me/push-registrations",
            JSONObject().put("fid", fid).apply { previous?.takeIf { it.isNotEmpty() && it != fid }?.let { put("previous_fid", it) } })
    }

    fun unregisterFid(ctx: Context, fid: String) {
        send(ctx, "DELETE", "/api/v1/users/me/push-registrations", JSONObject().put("fid", fid))
    }

    // ── 부모님 폰 → 분석 ──
    /** 폰에서 이미 가린 문자 → {result: {classification, requires_attention, risk_level, summary}, event_id, verification_id} */
    fun checkAlert(ctx: Context, text: String): JSONObject =
        post(ctx, "/api/v1/alerts/check", JSONObject().put("family_id", Prefs.family(ctx)).put("occurred_at", now()).put("text", text))

    /** 통화 녹음 (multipart) → {event_id, analysis_status, status, result, error_code}. 분석 실패는 502 지만 본문은 같은 모양 */
    fun analyzeCall(ctx: Context, file: File): JSONObject {
        if (Prefs.testMode(ctx)) return Demo.call()
        val boundary = "----jikimi" + UUID.randomUUID()
        val c = open(ctx, "/api/v1/calls/analyze", "POST", readMs = CALL_READ_MS).apply {
            doOutput = true
            setRequestProperty("Content-Type", "multipart/form-data; boundary=$boundary")
        }
        c.outputStream.buffered().use { out ->
            fun field(name: String, value: String) {
                out.write("--$boundary\r\nContent-Disposition: form-data; name=\"$name\"\r\n\r\n$value\r\n".toByteArray())
            }
            field("family_id", Prefs.family(ctx))
            field("occurred_at", now())
            out.write(("--$boundary\r\nContent-Disposition: form-data; name=\"file\"; filename=\"${file.name}\"\r\n" +
                "Content-Type: application/octet-stream\r\n\r\n").toByteArray())
            file.inputStream().use { it.copyTo(out) }
            out.write("\r\n--$boundary--\r\n".toByteArray())
        }
        if (c.responseCode == 502) return JSONObject(c.errorStream.bufferedReader().readText())
        return JSONObject(read(c, ctx))
    }

    /** 앱 설치 보고 → {matched, event_id, related_call} */
    fun reportInstall(ctx: Context, pkg: String, label: String, unknownSource: Boolean): JSONObject =
        post(ctx, "/api/v1/actions/app-install", JSONObject().put("family_id", Prefs.family(ctx)).put("package_name", pkg)
            .put("app_label", label).put("is_unknown_source", unknownSource).put("occurred_at", now()))

    // ── 가족 확인 ──
    /** {id, event_id, status: PENDING|CONFIRMED|DENIED|EXPIRED, expires_at, target_count, responded_count, my_response} */
    fun verification(ctx: Context, id: String): JSONObject = JSONObject(get(ctx, "/api/v1/verify/$id"))

    /** 자녀의 답: SENT | NOT_SENT */
    fun respond(ctx: Context, id: String, response: String): JSONObject =
        post(ctx, "/api/v1/verify/respond", JSONObject().put("verification_id", id).put("response", response))

    // ── 자녀 폰: 사건 ──
    /** [{id, event_type, classification, risk_level, summary, analysis_status, status, occurred_at}] 최신순 */
    fun events(ctx: Context, limit: Int = 100): JSONArray =
        JSONArray(get(ctx, "/api/v1/events?family_id=${Prefs.family(ctx)}&limit=$limit&offset=0"))

    /** 상세: 위 + instructions [{instruction_type}] */
    fun event(ctx: Context, id: String): JSONObject = JSONObject(get(ctx, "/api/v1/events/$id"))

    /** 대응 상태: ACKNOWLEDGED | RESOLVED */
    fun setStatus(ctx: Context, id: String, status: String): JSONObject =
        JSONObject(send(ctx, "PATCH", "/api/v1/events/$id/status", JSONObject().put("status", status)))

}
