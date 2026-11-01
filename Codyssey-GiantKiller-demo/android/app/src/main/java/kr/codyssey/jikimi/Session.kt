package kr.codyssey.jikimi

import android.app.ActivityManager
import android.app.Notification
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Handler
import android.os.Looper
import android.widget.Toast

/**
 * 로그인 만료 (BE 401). 부모님·자녀·지킴이 어디서 받든 여기 한 곳에서 처리한다.
 *  - 저장된 토큰만 지운다 (역할·이름·가족은 남김 → 다시 로그인하면 그대로 이어서)
 *  - 앱 화면이 떠 있으면 로그인 화면으로, 지킴이만 뒤에서 돌고 있으면 "다시 로그인해 주세요" 알림 (누르면 로그인 화면)
 * 예전에는 토큰을 안 지워서, 앱을 다시 열어도 로그인된 줄 알고 같은 화면으로 돌아갔다.
 */
object Session {
    private const val NOTI_ID = 4011
    private val main = Handler(Looper.getMainLooper())

    fun expired(ctx: Context) {
        if (Prefs.testMode(ctx) || Prefs.token(ctx).isEmpty()) return // 이미 처리함 (여러 요청이 한꺼번에 401 이어도 한 번만)
        Prefs.set(ctx, "token" to null)
        val app = ctx.applicationContext
        main.post {
            if (onScreen()) {
                Toast.makeText(app, "로그인이 끝났어요. 다시 로그인해 주세요", Toast.LENGTH_LONG).show()
                app.startActivity(Intent(app, MainActivity::class.java)
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK))
            } else {
                notify(app)
            }
        }
    }

    /** 앱 화면이 사용자 앞에 있는지 (지킴이 서비스만 돌 때는 아님) */
    private fun onScreen(): Boolean = ActivityManager.RunningAppProcessInfo()
        .also { ActivityManager.getMyMemoryState(it) }
        .importance == ActivityManager.RunningAppProcessInfo.IMPORTANCE_FOREGROUND

    private fun notify(ctx: Context) {
        Notifier.channels(ctx)
        val open = PendingIntent.getActivity(ctx, NOTI_ID,
            Intent(ctx, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val n = Notification.Builder(ctx, Notifier.CH_WARNING)
            .setSmallIcon(android.R.drawable.ic_lock_lock)
            .setContentTitle("다시 로그인해 주세요")
            .setContentText("로그인이 끝나서 지킴이가 서버와 연결되지 않아요. 눌러서 로그인해 주세요.")
            .setStyle(Notification.BigTextStyle().bigText("로그인이 끝나서 지킴이가 서버와 연결되지 않아요. 눌러서 로그인해 주세요."))
            .setContentIntent(open)
            .setAutoCancel(true)
            .build()
        runCatching { ctx.getSystemService(NotificationManager::class.java).notify(NOTI_ID, n) }
    }
}
