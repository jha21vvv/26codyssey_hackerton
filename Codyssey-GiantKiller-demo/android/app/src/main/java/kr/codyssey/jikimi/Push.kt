package kr.codyssey.jikimi

import android.app.Notification
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log
import com.google.firebase.FirebaseApp
import com.google.firebase.messaging.FirebaseMessaging
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import org.json.JSONObject

/**
 * FCM 푸시 (BE PRD-004: 등록 토큰이 아니라 FID 를 `PUT /api/v1/users/me/push-registrations` 로 올린다).
 * Firebase 설정 파일(android/app/google-services.json)이 없으면 푸시 없이 동작한다 — 자녀 폰은 알림을 못 받는다.
 */
object Push {
    private const val TAG = "jikimi"

    fun available(ctx: Context) = FirebaseApp.getApps(ctx).isNotEmpty()

    /** 로그인 뒤: FCM 에 등록 → onRegistered(FID) 에서 BE 로 올린다. 이미 받은 FID 가 있으면 바로 올림 */
    fun start(ctx: Context) {
        if (Prefs.testMode(ctx)) return // 테스트 모드는 서버에 아무것도 안 올린다
        if (!available(ctx)) {
            Log.w(TAG, "Firebase 설정 없음 → 푸시 없이 동작")
            return
        }
        Prefs.fid(ctx).takeIf { it.isNotEmpty() }?.let { fid ->
            Api.io.execute { runCatching { Api.registerFid(ctx, fid, null) }.onFailure { Log.w(TAG, "FID 등록 실패: ${it.message}") } }
        }
        runCatching { FirebaseMessaging.getInstance().register() }.onFailure { Log.w(TAG, "FCM 등록 실패: ${it.message}") }
    }

    /** 로그아웃 전: 이 폰의 FID 연결 해제 (실패해도 로그아웃은 진행) */
    fun stop(ctx: Context) {
        if (Prefs.testMode(ctx)) return
        val fid = Prefs.fid(ctx).takeIf { it.isNotEmpty() } ?: return
        runCatching { Api.unregisterFid(ctx, fid) }.onFailure { Log.w(TAG, "FID 해제 실패: ${it.message}") }
    }
}

class JikimiMessagingService : FirebaseMessagingService() {
    override fun onRegistered(installationId: String) {
        val previous = Prefs.fid(this)
        Prefs.set(this, "fid" to installationId)
        if (Prefs.token(this).isEmpty()) return // 로그인 뒤 Push.start 에서 올린다
        Api.io.execute {
            runCatching { Api.registerFid(this, installationId, previous) }.onFailure { Log.w("jikimi", "FID 등록 실패: ${it.message}") }
        }
    }

    /** 앱이 화면에 있을 때 온 푸시 (뒤에 있을 때는 안드로이드가 BE 문구 그대로 알림을 띄운다) */
    override fun onMessageReceived(message: RemoteMessage) {
        val data = message.data
        if (Prefs.role(this) == "parent") {
            // 부모님 폰: 가족 확인 결과는 직접 확인해 띄운다(Reactions.watch). 통화 분석 경고(CALL_WARNING)만 받아 경고창
            // (같은 통화를 업로드 응답으로 이미 띄웠으면 Reactions 가 event_id 로 한 번만 띄운다)
            // 통화 업로드 응답을 기다리는 중이면 보류 → 응답(요약 포함)이 먼저 뜨게 (CallWarnings)
            // 경고창 권한이 없으면 data 의 title·body 로 상단바 알림 (BE PR #15: CALL_WARNING 은 data 만, high)
            if (data["push_type"] == "CALL_WARNING" && !CallWarnings.hold(data["event_id"], data["title"], data["body"]))
                Reactions.call(this, JSONObject(), data["event_id"], data["title"], data["body"])
            return
        }
        Notifier.child(this, message.notification?.title ?: "부모님 지킴이", message.notification?.body ?: "",
            // 알림 종류 키는 push_type (BE PR #12). message_type 은 FCM 예약 키라 발송 자체가 거부됐다
            data["push_type"].orEmpty(), data["event_id"], data["verification_id"])
    }
}

/** 알림의 "내가 보냈어요 / 안 보냈어요" 버튼 → POST /api/v1/verify/respond */
class VerifyReceiver : BroadcastReceiver() {
    override fun onReceive(ctx: Context, intent: Intent) {
        val id = intent.getStringExtra("verification_id") ?: return
        val answer = intent.getStringExtra("answer") ?: return
        val notifyId = intent.getIntExtra("notify_id", 0)
        val pending = goAsync()
        Api.io.execute {
            val text = try {
                Api.respond(ctx, id, answer)
                if (answer == "SENT") "✅ 내가 보냈다고 답했어요" else "🚫 안 보냈다고 답했어요"
            } catch (e: Api.HttpError) {
                if (e.code == 409) "이미 답했거나 확인이 끝난 요청이에요" else "전송 실패: ${e.detail}"
            } catch (e: Exception) {
                "전송 실패: 인터넷 연결을 확인해 주세요"
            }
            Notifier.replaceText(ctx, notifyId, "메시지 발송 확인 요청", text)
            pending.finish()
        }
    }
}

/** 폰을 다시 켜거나 앱이 업데이트되면 부모님 폰 지킴이를 다시 시작 */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(ctx: Context, intent: Intent) {
        if (Prefs.role(ctx) == "parent" && Prefs.family(ctx).isNotEmpty()) GuardService.start(ctx)
    }
}

/** 자녀 폰 알림: BE 푸시 문구 그대로 + 가족 확인 요청엔 답 버튼, 누르면 앱의 해당 화면 */
internal fun Notifier.child(ctx: Context, title: String, body: String, type: String, eventId: String?, verificationId: String?) {
    channels(ctx)
    verificationId?.let { if (type == "VERIFY_REQUEST") Prefs.addVerification(ctx, it) }
    val id = (verificationId ?: eventId ?: title).hashCode()
    val open = PendingIntent.getActivity(ctx, id,
        Intent(ctx, ChildActivity::class.java).putExtra(ChildActivity.EXTRA_EVENT, eventId)
            .putExtra(ChildActivity.EXTRA_VERIFICATION, verificationId)
            .addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP),
        PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
    val channel = when (type) { "INSTALL_WARNING" -> CH_URGENT; "VERIFY_REQUEST" -> CH_CONFIRM; else -> CH_WARNING }
    val b = Notification.Builder(ctx, channel)
        .setSmallIcon(android.R.drawable.ic_lock_lock)
        .setContentTitle(title)
        .setContentText(body)
        .setStyle(Notification.BigTextStyle().bigText(body))
        .setContentIntent(open)
        .setAutoCancel(type != "VERIFY_REQUEST")
    if (type == "VERIFY_REQUEST" && verificationId != null) {
        for ((label, answer) in listOf("내가 보냈어요" to "SENT", "안 보냈어요" to "NOT_SENT")) {
            val pi = PendingIntent.getBroadcast(ctx, id + answer.hashCode(),
                Intent(ctx, VerifyReceiver::class.java).putExtra("verification_id", verificationId).putExtra("answer", answer)
                    .putExtra("notify_id", id),
                PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
            b.addAction(Notification.Action.Builder(null, label, pi).build())
        }
    }
    ctx.getSystemService(NotificationManager::class.java).notify(id, b.build())
}
