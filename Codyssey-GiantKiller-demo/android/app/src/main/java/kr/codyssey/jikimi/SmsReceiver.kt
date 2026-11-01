package kr.codyssey.jikimi

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.provider.Telephony

/**
 * 문자 직접 받기. 알림보다 정확하다 — 보낸 번호가 연락처 이름이 아니라 진짜 번호로 오고,
 * 잠금화면에서 '내용 숨김'으로 설정해도 전체 내용을 읽는다. 알림으로도 같은 문자가 오면 Inbox 가 한 번만 처리.
 * (RCS 채팅 메시지는 이 길로 안 와서 알림으로 읽는다)
 */
class SmsReceiver : BroadcastReceiver() {
    override fun onReceive(ctx: Context, intent: Intent) {
        if (intent.action != Telephony.Sms.Intents.SMS_RECEIVED_ACTION) return
        val parts = Telephony.Sms.Intents.getMessagesFromIntent(intent) ?: return
        // 긴 문자는 여러 조각으로 온다 → 보낸 번호별로 이어 붙인다
        for ((from, ps) in parts.groupBy { it.originatingAddress.orEmpty() }) {
            val body = ps.joinToString("") { it.messageBody.orEmpty() }
            if (from.isNotEmpty() && body.isNotBlank()) Inbox.handle(ctx, from, body, "문자")
        }
    }
}
