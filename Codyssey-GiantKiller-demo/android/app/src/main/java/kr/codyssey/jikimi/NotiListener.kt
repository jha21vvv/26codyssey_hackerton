package kr.codyssey.jikimi

import android.app.Notification
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification

/**
 * 알림 접근 권한으로 문자·카톡 알림을 읽는다. 부모님은 아무것도 안 해도 된다.
 * 설정 > 알림 > 기기 및 앱 알림 > 알림 읽기 허용 에서 '부모님 지킴이 알림 확인'을 켜야 동작.
 * 문자는 SmsReceiver 로도 받는다 — 같은 문자는 Inbox 가 한 번만 처리.
 */
class NotiListener : NotificationListenerService() {

    companion object {
        // 문자·메신저 앱만 본다. 다른 앱 알림까지 보려면 여기에 추가.
        val WATCH = setOf(
            "com.samsung.android.messaging",      // 삼성 메시지
            "com.google.android.apps.messaging",  // 구글 메시지
            "com.android.mms",
            "com.kakao.talk",
        )
    }

    override fun onNotificationPosted(sbn: StatusBarNotification) {
        if (sbn.packageName !in WATCH || sbn.isOngoing) return
        // "새 메시지 2개" 같은 묶음 요약 알림은 문자 하나가 아니므로 건너뛴다
        if (sbn.notification.flags and Notification.FLAG_GROUP_SUMMARY != 0) return
        // 지킴이가 재시작되면 알림창에 남아 있던 옛 알림이 다시 올라온다 → 2분 넘은 메시지는 무시
        val sentAt = sbn.notification.`when`
        if (sentAt > 0 && System.currentTimeMillis() - sentAt > 2 * 60_000) return
        val ex = sbn.notification.extras
        val title = ex.getCharSequence(Notification.EXTRA_TITLE)?.toString() ?: return
        val text = (ex.getCharSequence(Notification.EXTRA_BIG_TEXT) ?: ex.getCharSequence(Notification.EXTRA_TEXT))
            ?.toString() ?: return
        Inbox.handle(this, title, text, sbn.packageName.substringAfterLast('.'))
    }
}
