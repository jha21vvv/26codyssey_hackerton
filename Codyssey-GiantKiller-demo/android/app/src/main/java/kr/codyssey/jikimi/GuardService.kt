package kr.codyssey.jikimi

import android.app.Service
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.ServiceInfo
import android.database.ContentObserver
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.PowerManager
import android.provider.MediaStore
import android.util.Log
import java.io.File
import org.json.JSONObject

/**
 * 부모님 폰에서 뒤에서 계속 도는 서비스. 판단은 모두 백엔드(BE)가 하고, 이 서비스는 보고만 한다.
 *  1) 앱 설치 감지 → POST /api/v1/actions/app-install → 위험이면 경고창
 *  2) 통화 녹음 파일 감지 → POST /api/v1/calls/analyze → 주의 필요면 경고창
 *  (문자·메신저는 SmsReceiver·NotiListener → Inbox → POST /api/v1/alerts/check)
 */
class GuardService : Service() {
    companion object {
        private const val TAG = "jikimi"
        private const val CHECK_MS = 15_000L
        private const val MAX_AUDIO_BYTES = 10L * 1024 * 1024 // BE app/services/analysis.py MAX_AUDIO_BYTES
        fun start(ctx: Context) = ctx.startForegroundService(Intent(ctx, GuardService::class.java))
    }

    private val main = Handler(Looper.getMainLooper())
    private var running = false

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        Notifier.channels(this)
        startForeground(1, Notifier.service(this), ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
        registerReceiver(installReceiver, IntentFilter(Intent.ACTION_PACKAGE_ADDED).apply { addDataScheme("package") })
        // 파일 복사·녹음 앱 저장은 오디오 목록이 아니라 미디어 전체 경로로 알림이 오는 경우가 있어 넓게 듣는다
        contentResolver.registerContentObserver(android.net.Uri.parse("content://media/external"), true, audioObserver)
        running = true
        Api.io.execute { runCatching { baselineCallRecordings() } }
        main.post(tick)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int) = START_STICKY

    override fun onDestroy() {
        running = false
        unregisterReceiver(installReceiver)
        contentResolver.unregisterContentObserver(audioObserver)
        super.onDestroy()
    }

    // 미디어 변경 알림을 놓치는 기종이 있어서 15초마다 직접도 확인
    private val tick = object : Runnable {
        override fun run() {
            if (!running) return
            checkCallRecordings()
            main.postDelayed(this, CHECK_MS)
        }
    }

    // ── 1) 앱 설치 ──
    private val installReceiver = object : BroadcastReceiver() {
        override fun onReceive(ctx: Context, intent: Intent) {
            if (intent.getBooleanExtra(Intent.EXTRA_REPLACING, false)) return // 업데이트는 무시
            val pkg = intent.data?.schemeSpecificPart ?: return
            val label = runCatching {
                packageManager.getApplicationLabel(packageManager.getApplicationInfo(pkg, 0)).toString()
            }.getOrDefault(pkg)
            Log.i(TAG, "앱 설치 감지: $label")
            Api.io.execute {
                try {
                    val unknown = unknownSource(pkg)
                    val r = Api.reportInstall(ctx, pkg, label, unknown)
                    if (r.optBoolean("matched")) Reactions.install(ctx, label, pkg, unknown, r.optBoolean("related_call"), r.optString("event_id"))
                } catch (e: Exception) {
                    Log.w(TAG, "앱 설치 보고 실패: ${e.message}")
                }
            }
        }
    }

    /** 공식 스토어(플레이·갤럭시 스토어)가 아닌 곳에서 깔린 앱인가 — BE 가 위험 판정에 쓴다 */
    private fun unknownSource(pkg: String): Boolean {
        val installer = runCatching {
            if (Build.VERSION.SDK_INT >= 30) packageManager.getInstallSourceInfo(pkg).installingPackageName
            else @Suppress("DEPRECATION") packageManager.getInstallerPackageName(pkg)
        }.getOrNull()
        return installer !in setOf("com.android.vending", "com.sec.android.app.samsungapps")
    }

    // ── 2) 통화 녹음 ── (실기기 확인 필요: 기종마다 저장 폴더·파일 이름이 다르다)
    private val audioObserver = object : ContentObserver(main) {
        override fun onChange(selfChange: Boolean) = checkCallRecordings()
    }

    /** 통화 녹음 폴더(Recordings/Call, 통화 녹음 등)에서 가장 최근 파일 (id, 경로, 이름) */
    private fun newestCallRecording(): Triple<Long, String, String>? {
        val cols = arrayOf(MediaStore.Audio.Media._ID, MediaStore.Audio.Media.DATA, MediaStore.Audio.Media.DISPLAY_NAME)
        val where = "${MediaStore.Audio.Media.RELATIVE_PATH} LIKE ? OR ${MediaStore.Audio.Media.RELATIVE_PATH} LIKE ?"
        return contentResolver.query(MediaStore.Audio.Media.EXTERNAL_CONTENT_URI, cols, where, arrayOf("%Call%", "%통화%"),
            "${MediaStore.Audio.Media.DATE_ADDED} DESC, ${MediaStore.Audio.Media._ID} DESC")?.use { c ->
            if (c.moveToFirst()) Triple(c.getLong(0), c.getString(1) ?: "", c.getString(2) ?: "") else null
        }
    }

    /** 처음 켰을 때: 이미 있던 녹음은 올리지 않도록 기준점만 잡는다 */
    private fun baselineCallRecordings() {
        if (Prefs.lastAudio(this) < 0) Prefs.set(this, "last_audio" to (newestCallRecording()?.first ?: 0L))
    }

    private val audioLock = Any()

    /**
     * 이 녹음을 올릴 차례면 true. "이미 올렸나" 확인과 기록을 한 묶음으로 한다.
     * (녹음 파일이 써지는 동안 감지가 연달아 와서 병렬 작업들이 모두 확인을 통과해, 같은 녹음이 BE 에 세 번 올라간 적이 있다)
     */
    private fun claim(id: Long): Boolean = synchronized(audioLock) {
        if (id <= Prefs.lastAudio(this)) false else { Prefs.set(this, "last_audio" to id); true }
    }

    /** 파일 쓰기가 끝날 때까지 기다린다: 1초 간격으로 크기가 그대로면 끝 (최대 약 20초) */
    private fun waitWritten(file: File) {
        var last = -1L
        repeat(20) {
            val now = file.length()
            if (now > 0 && now == last) return
            last = now
            Thread.sleep(1000)
        }
    }

    /** 새 통화 녹음이 있으면 BE 로 보내 분석 → 주의 필요면 경고창 */
    private fun checkCallRecordings() = Api.io.execute {
        runCatching {
            val (id, path, name) = newestCallRecording() ?: return@runCatching
            if (path.isEmpty() || !claim(id)) return@runCatching // 같은 녹음은 한 번만 (감지가 연달아 와도)
            // 화면이 꺼지면 폰이 잠들어 기다림·업로드가 몇 분씩 늘어진다(10/31 22:26 갤럭시: 47초 녹음이 3분 20초 뒤 경고) → 처리하는 동안만 CPU 를 깨워 둔다 (화면은 꺼진 채)
            val wake = getSystemService(PowerManager::class.java).newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "jikimi:call").apply { acquire(3 * 60_000L) }
            try { uploadCall(id, path, name) } finally { if (wake.isHeld) wake.release() }
        }.onFailure { Log.w(TAG, "통화 녹음 확인 실패: ${it.message}") }
    }

    /** 쓰기가 끝나면 BE 로 올려 분석 → 주의 필요면 경고창. 진행을 로그로 남긴다 (예전엔 끝날 때만 남아서 업로드 중인지 알 수 없었다) */
    private fun uploadCall(id: Long, path: String, name: String) {
        Log.i(TAG, "통화 녹음 감지 (#$id) → 쓰기가 끝나길 기다림")
        val file = File(path)
        waitWritten(file)
        // BE 는 10MB 넘는 녹음을 받지 않는다 (413 AUDIO_TOO_LARGE) — 긴 통화는 보내지 않고 기록만
        if (file.length() > MAX_AUDIO_BYTES) {
            Log.w(TAG, "통화 녹음이 10MB 를 넘어 보내지 않음 (${file.length() / 1024 / 1024}MB)")
            return
        }
        Log.i(TAG, "통화 녹음 올리는 중 (${file.length() / 1024}KB) → 서버 분석 기다림 (최대 95초)")
        CallWarnings.begin() // 응답을 기다리는 동안 온 CALL_WARNING 푸시는 보류
        try {
            val r = try {
                Api.analyzeCall(this, file)
            } catch (e: Api.HttpError) {
                Log.w(TAG, "통화 녹음 분석 실패 ${e.code} ${e.detail}") // 413 AUDIO_TOO_LARGE · 422 EMPTY_AUDIO · 503 AI_NOT_CONFIGURED
                return
            }
            Log.i(TAG, "통화 녹음 분석 $name → ${r.optString("analysis_status")} ${r.optString("status")}")
            r.optJSONObject("result")?.takeIf { it.optBoolean("requires_attention") }?.let { Reactions.call(this, it, r.optString("event_id")) }
        } finally {
            // 성공이면 같은 사건은 위에서 떠서 firstTime 이 막고, 실패·시간 초과·예외면 보류한 푸시가 기본 문구로 뜬다
            CallWarnings.end().forEach { (id, title, body) -> Reactions.call(this, JSONObject(), id, title, body) }
        }
    }
}
