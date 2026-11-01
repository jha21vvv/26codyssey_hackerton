package kr.codyssey.jikimi

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.time.OffsetDateTime

/**
 * 테스트 모드: 로그인·서버 없이 화면을 둘러보는 용도 (첫 화면 로그인 아래 "테스트로 둘러보기").
 * Api 가 BE 대신 여기서 예시 응답을 받는다 — 모양은 BE 응답 그대로. 이 폰 메모리에만 있고 서버로는 아무것도 안 보낸다.
 * 로그아웃하면 끝난다.
 */
object Demo {
    private const val FAMILY = "test-family"
    private const val PARENT = "test-parent"
    private const val CHILD = "test-child"

    private fun ago(min: Long) = OffsetDateTime.now().minusMinutes(min).toString()

    /** 테스트 모드 시작: 로그인·가족 연결을 건너뛴다 */
    fun start(ctx: Context) {
        val child = Prefs.role(ctx) == "child"
        Prefs.set(ctx, "test_mode" to "1", "token" to "test", "name" to (if (child) "민수" else "김순자"),
            "user_id" to (if (child) CHILD else PARENT), "family" to FAMILY)
        if (child) Prefs.addVerification(ctx, "test-v1")
    }

    private val events = mutableListOf(
        event("e1", "APP_INSTALL", "RISKY_APP_INSTALL", "HIGH", "최근 의심 통화 뒤 '검찰청 보안' 앱 설치가 감지됐어요.", "OPEN", 5),
        event("e2", "CALL", "FRAUD", "HIGH", "검찰·수사기관 사칭 의심 통화예요. 앱 설치·계좌 이체를 요구했어요.", "OPEN", 30),
        event("e3", "ALERT", "CHILD_IMPERSONATION", "HIGH", "모르는 번호에서 자녀인 척 '폰이 고장났다, 상품권을 사 달라'는 문자가 왔어요.",
            "OPEN", 12),
        event("e4", "ALERT", "FRAUD", "MEDIUM", "택배 주소 오류를 핑계로 링크를 누르게 하는 문자예요.", "ACKNOWLEDGED", 90),
        event("e5", "ALERT", "FRAUD", "MEDIUM", "정부 지원금을 준다며 개인정보를 요구하는 문자예요.", "RESOLVED", 60 * 26),
    )
    private val verifications = mutableMapOf(
        "test-v1" to JSONObject().put("id", "test-v1").put("event_id", "e3").put("status", "PENDING")
            .put("expires_at", OffsetDateTime.now().plusMinutes(10).toString()).put("target_count", 1).put("responded_count", 0)
            .put("my_response", JSONObject.NULL),
    )
    private val createdAt = mutableMapOf<String, Long>()

    private fun event(id: String, type: String, cls: String, risk: String, summary: String, status: String, minAgo: Long,
                      instr: List<String> = emptyList()) = JSONObject()
        .put("id", id).put("event_type", type).put("classification", cls).put("risk_level", risk).put("summary", summary)
        .put("analysis_status", if (type == "CALL") "COMPLETED" else JSONObject.NULL).put("status", status)
        .put("occurred_at", ago(minAgo))
        .put("instructions", JSONArray(instr.map { JSONObject().put("instruction_type", it) }))

    private fun family() = JSONObject().put("id", FAMILY).put("created_at", ago(60 * 24)).put("members", JSONArray()
        .put(JSONObject().put("id", "m1").put("user_id", CHILD).put("name", "민수").put("role", "CHILD").put("is_representative", true)
            .put("joined_at", ago(60 * 24)))
        .put(JSONObject().put("id", "m2").put("user_id", PARENT).put("name", "김순자").put("role", "PARENT").put("is_representative", false)
            .put("joined_at", ago(60 * 23))))

    private fun listed(e: JSONObject) = JSONObject(e.toString()).apply { remove("instructions") }

    /** 문자 판단 흉내: BE 분류 셋 (CHILD_IMPERSONATION · FRAUD · NORMAL, BE app/core/ai.py) */
    private fun judge(text: String): JSONObject {
        val (cls, risk, summary) = when {
            Regex("엄마|아빠|폰 고장|액정|이 번호로").containsMatchIn(text) ->
                Triple("CHILD_IMPERSONATION", "HIGH", "자녀인 척 급한 부탁을 하는 문자예요.")
            Regex("https?://|www\\.|검찰|경찰|금감원|대출|지원금").containsMatchIn(text) ->
                Triple("FRAUD", "HIGH", "링크를 누르게 하는 사기 의심 문자예요.")
            else -> Triple("NORMAL", "LOW", "위험 신호가 없는 문자예요.")
        }
        return JSONObject().put("classification", cls).put("requires_attention", cls != "NORMAL")
            .put("risk_level", risk).put("summary", summary)
    }

    /** Api 의 BE 요청을 대신 받는다 → BE 응답과 같은 모양의 JSON 글자 */
    @Synchronized
    fun handle(ctx: Context, method: String, path: String, body: JSONObject?): String {
        val p = path.substringBefore('?')
        return when {
            p == "/api/v1/users/me" -> JSONObject().put("id", Prefs.userId(ctx)).put("name", Prefs.name(ctx)).put("email", "test@jikimi.test").toString()
            p == "/api/v1/families" && method == "GET" -> JSONArray().put(family()).toString()
            p.startsWith("/api/v1/families") && p.endsWith("/invitations") -> JSONObject().put("id", "inv1").put("family_id", FAMILY)
                .put("role", body?.optString("role")).put("invite_url", "https://jikimi.test/invite/test-token")
                .put("expires_at", OffsetDateTime.now().plusHours(24).toString()).toString()
            p.startsWith("/api/v1/families") && p.contains("/invitations/") && method == "DELETE" -> "" // 초대 취소: 204
            p.startsWith("/api/v1/families") -> family().toString()
            p.startsWith("/api/v1/invitations/") && p.endsWith("/accept") -> JSONObject().put("id", "m3").put("role", "CHILD").toString()
            p.startsWith("/api/v1/invitations/") -> JSONObject().put("family_id", FAMILY).put("representative_name", "민수")
                .put("role", if (Prefs.role(ctx) == "parent") "PARENT" else "CHILD").put("expires_at", ago(-60)).toString()
            p.startsWith("/api/v1/users/me/push-registrations") -> ""
            p == "/api/v1/alerts/check" -> {
                val result = judge(body?.optString("text").orEmpty())
                var eventId: Any = JSONObject.NULL
                var vId: Any = JSONObject.NULL
                if (result.getBoolean("requires_attention")) {
                    val id = "e" + (events.size + 1)
                    events.add(0, event(id, "ALERT", result.getString("classification"), result.getString("risk_level"),
                        result.getString("summary"), "OPEN", 0))
                    eventId = id
                    if (result.getString("classification") == "CHILD_IMPERSONATION") {
                        vId = "test-v" + (verifications.size + 1)
                        verifications[vId] = JSONObject().put("id", vId).put("event_id", id).put("status", "PENDING")
                            .put("expires_at", OffsetDateTime.now().plusMinutes(10).toString()).put("target_count", 1)
                            .put("responded_count", 0).put("my_response", JSONObject.NULL)
                        createdAt[vId] = System.currentTimeMillis()
                    }
                }
                JSONObject().put("result", result).put("event_id", eventId).put("verification_id", vId).toString()
            }
            p == "/api/v1/actions/app-install" -> JSONObject().put("matched", body?.optBoolean("is_unknown_source") == true)
                .put("event_id", JSONObject.NULL).put("related_call", true).toString()
            p == "/api/v1/verify/respond" -> {
                val v = verifications.getValue(body!!.getString("verification_id"))
                v.put("my_response", body.getString("response")).put("responded_count", 1)
                    .put("status", if (body.getString("response") == "SENT") "CONFIRMED" else "DENIED")
                v.toString()
            }
            p.startsWith("/api/v1/verify/") -> {
                val id = p.substringAfterLast('/')
                val v = verifications[id] ?: throw Api.HttpError(404, "VERIFICATION_NOT_FOUND")
                // 부모님 폰 시험: 8초 뒤 자녀가 '안 보냈어요'라고 답한 것처럼
                createdAt[id]?.let { if (v.getString("status") == "PENDING" && System.currentTimeMillis() - it > 8000)
                    v.put("status", "DENIED").put("responded_count", 1) }
                v.toString()
            }
            p == "/api/v1/events" -> JSONArray(events.map { listed(it) }).toString()
            p.startsWith("/api/v1/events/") && p.endsWith("/status") -> {
                val e = events.first { it.getString("id") == p.split('/')[4] }
                e.put("status", body!!.getString("status"))
                listed(e).toString()
            }
            p.startsWith("/api/v1/events/") -> (events.firstOrNull { it.getString("id") == p.substringAfterLast('/') }
                ?: throw Api.HttpError(404, "EVENT_NOT_FOUND")).toString()
            else -> throw Api.HttpError(404, "테스트 모드에 없는 요청: $method $p")
        }
    }

    /** 통화 녹음 분석 흉내 */
    fun call(): JSONObject = JSONObject().put("event_id", "e2").put("analysis_status", "COMPLETED").put("status", "OPEN")
        .put("result", JSONObject().put("classification", "FRAUD").put("requires_attention", true).put("risk_level", "HIGH")
            .put("summary", "검찰·수사기관 사칭 의심 통화예요. 앱 설치·계좌 이체를 요구했어요.")
            .put("instructions", JSONArray())) // BE 는 통화 지시를 아직 뽑지 않는다 (항상 빈 목록)
        .put("error_code", JSONObject.NULL)
}
