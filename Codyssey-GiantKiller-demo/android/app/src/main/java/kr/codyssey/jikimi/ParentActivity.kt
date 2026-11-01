package kr.codyssey.jikimi

import android.Manifest
import android.app.Activity
import android.app.AlertDialog
import android.content.ComponentName
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.PowerManager
import android.provider.Settings
import android.widget.TextView
import android.widget.Toast
import kr.codyssey.jikimi.Ui.button
import kr.codyssey.jikimi.Ui.card
import kr.codyssey.jikimi.Ui.divider
import kr.codyssey.jikimi.Ui.gap
import kr.codyssey.jikimi.Ui.heading
import kr.codyssey.jikimi.Ui.listRow
import kr.codyssey.jikimi.Ui.page
import kr.codyssey.jikimi.Ui.split
import kr.codyssey.jikimi.Ui.text
import kr.codyssey.jikimi.Ui.topBar

/**
 * 부모님 폰 설정 (디자인 시안 02). 처음 한 번 자녀가 같이 해 주는 화면이고, 끝나면 부모님은 이 앱을 열 필요가 없다.
 *  1) 로그인(MainActivity) → 자녀가 보낸 초대 코드로 가족 참여 (BE: 가족은 대표 자녀가 만든다)
 *  2) 보호 설정: 알림 읽기 · 다른 앱 위에 표시 (+ 연락처·문자·녹음 파일, 배터리) → 지킴이 자동 시작
 */
class ParentActivity : Activity() {
    override fun onCreate(savedInstanceState: android.os.Bundle?) {
        super.onCreate(savedInstanceState)
        SystemBars.apply(this)
        // '뒤로' → 첫 화면("누가 사용하나요?"). 안드로이드 13+ 는 뒤로 가기 콜백, 그 전은 onBackPressed
        if (Build.VERSION.SDK_INT >= 33)
            onBackInvokedDispatcher.registerOnBackInvokedCallback(android.window.OnBackInvokedDispatcher.PRIORITY_DEFAULT) { back() }
    }

    @Deprecated("안드로이드 12 이하용")
    override fun onBackPressed() = back()

    companion object {
        private val COMMON_PERMS = arrayOf(Manifest.permission.READ_CONTACTS, Manifest.permission.RECEIVE_SMS)

        // (버튼 이름, (보낸 번호, 내용)) — 번호는 시험용 가짜 번호
        private val SAMPLES = listOf(
            "시험: 자녀 사칭 문자" to ("010-9876-5432" to "엄마 나 폰 액정 깨져서 수리 맡겼어. 이 번호로 문자줘"),
            "시험: 택배 사기 문자" to ("02-3456-7890" to "[국제택배] 주소지 불일치로 배송 보류. 확인: http://kr-post-check.xyz/a1"),
            "시험: 평범한 안내 문자 (아무것도 안 떠요)" to ("1588-1234" to "[행복아파트] 10월 관리비 245,300원이 자동이체될 예정입니다."),
        )
    }

    private val main = Handler(Looper.getMainLooper())
    private var linkText: TextView? = null
    private var resumed = false

    override fun onResume() {
        super.onResume()
        resumed = true
        if (Prefs.family(this).isEmpty()) join() else render()
    }

    override fun onPause() {
        resumed = false
        super.onPause()
    }

    // ── 1) 가족 연결: 자녀가 보낸 초대 코드로 참여 (BE: 가족은 대표 자녀가 만든다) ──
    private fun join() = Join.receive(this, "PARENT", onBack = { logout() }) { render() }

    /** 뒤로: 가족 연결 화면이면 바로, 보호 설정 화면이면 한 번 묻고 첫 화면("누가 사용하나요?")으로 */
    private fun back() {
        if (Prefs.family(this).isEmpty()) return logout()
        val on = listenerOn() && Overlay.canShow(this)
        AlertDialog.Builder(this)
            .setMessage(if (on) "첫 화면으로 돌아가면 로그아웃되고 지킴이가 멈춰요. 돌아갈까요?" else "첫 화면(누가 사용하나요?)으로 돌아갈까요? 다시 로그인해야 해요.")
            .setPositiveButton("돌아가기") { _, _ -> logout() }.setNegativeButton("취소", null).show()
    }

    private fun logout() {
        val act = this
        stopService(Intent(act, GuardService::class.java))
        Api.io.execute {
            Push.stop(act)
            Prefs.reset(act)
            runOnUiThread { startActivity(Intent(act, MainActivity::class.java)); finish() }
        }
    }

    // ── 2) 보호 설정 (시안 02) · 3) 연결 코드 (시안 03) ──
    private fun listenerOn() = Settings.Secure.getString(contentResolver, "enabled_notification_listeners")
        ?.contains(ComponentName(this, NotiListener::class.java).flattenToString()) == true

    private fun runtimePerms(): Array<String> =
        if (Build.VERSION.SDK_INT >= 33)
            arrayOf(Manifest.permission.POST_NOTIFICATIONS, Manifest.permission.READ_MEDIA_AUDIO, *COMMON_PERMS)
        else arrayOf(Manifest.permission.READ_EXTERNAL_STORAGE, *COMMON_PERMS)

    private fun permsOn() = runtimePerms().all { checkSelfPermission(it) == PackageManager.PERMISSION_GRANTED }

    private fun openListener() = startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS))
    private fun openOverlay() = startActivity(Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:$packageName")))
    private fun openBattery() = startActivity(Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:$packageName")))

    private fun render() {
        val act = this
        val listener = listenerOn()
        val overlay = Overlay.canShow(this)
        val perms = permsOn()
        val battery = getSystemService(PowerManager::class.java).isIgnoringBatteryOptimizations(packageName)
        val ready = listener && overlay
        if (ready) GuardService.start(this)

        page {
            if (!ready) {
                topBar("보호 설정") { back() }
                if (Prefs.testMode(act)) text("테스트 모드 (예시 판단)", 13f, Ui.MUTED, top = 0)
                heading("위험한 연락을\n알려드릴 수 있게")
                text("아래 설정을 차례로 켜 주세요.", 17f, Ui.MUTED)
            } else {
                topBar("부모님 지킴이", null)
                if (Prefs.testMode(act)) text("테스트 모드 (예시 판단)", 13f, Ui.MUTED, top = 0)
                heading("지킴이가\n켜져 있어요")
                text("위험한 문자·전화·앱 설치가 있으면 화면에 크게 알려드려요.", 17f, Ui.MUTED)
                linkText = text("가족 확인 중…", 17f, Ui.MUTED, top = 16)
                text("이제 앱을 닫으셔도 돼요.", 15f, Ui.INK, bold = true, top = 8)
                text("보호 설정", 16f, Ui.MUTED, bold = true, top = 28)
            }

            // 설정 목록: 안 된 것은 "설정 ›", 된 것은 "완료"
            card(pad = 18) {
                fun row(title: String, sub: String, on: Boolean, open: () -> Unit) =
                    listRow(title, sub, if (on) "완료" else "설정", if (on) Ui.MUTED else Ui.DANGER) { open() }
                row("알림 읽기", "문자의 위험 신호를 확인해요", listener) { openListener() }
                divider()
                row("다른 앱 위에 표시", "위험할 때 크게 알려드려요", overlay) { openOverlay() }
                divider()
                row("연락처·문자·녹음 파일", "아는 번호 확인·문자 읽기·통화 녹음 확인", perms) { requestPermissions(runtimePerms(), 1) }
                divider()
                row("배터리 제한 해제", "앱을 닫아도 계속 알려드려요", battery) { openBattery() }
            }

            if (!ready) {
                gap(20)
                when {
                    !listener -> button("알림 읽기 설정하기") { openListener() }
                    else -> button("다른 앱 위에 표시 설정하기") { openOverlay() }
                }
                // 권한을 켜기 전에도 첫 화면("누가 사용하나요?")으로 돌아갈 수 있게
                gap(16)
                button("로그아웃", outline = true) { logout() }
            } else {
                // 현장 시험용: 다른 폰 없이 실제 흐름(폰 1차 필터 → 서버 AI → 경고창·자녀 알림)을 돌려 본다
                text("시험해 보기 (자녀 폰에도 알림이 가요)", 16f, Ui.MUTED, bold = true, top = 28)
                button("경고창 시험해 보기", primary = false) {
                    Overlay.show(act, "시험 경고창", "위험한 일이 생기면\n이렇게 화면을 덮어 알려드려요.")
                }
                for ((label, sample) in SAMPLES) button(label, primary = false) {
                    Inbox.handle(act, sample.first, sample.second, "시험", skipSeen = true)
                    Toast.makeText(act, "보냈어요. 몇 초 뒤 화면을 보세요 (같은 시험은 2분 뒤에 다시)", Toast.LENGTH_LONG).show()
                }
                gap(16)
                button("로그아웃", outline = true) {
                    AlertDialog.Builder(act).setMessage("로그아웃하면 지킴이가 멈춰요. 로그아웃할까요?")
                        .setPositiveButton("로그아웃") { _, _ -> logout() }.setNegativeButton("취소", null).show()
                }
            }
        }
        if (ready) pollLink()
    }

    /** 연결된 가족 (BE 가족 멤버) */
    private fun pollLink() {
        Api.io.execute {
            val text = try {
                val members = Api.family(this).getJSONArray("members")
                val kids = (0 until members.length()).map { members.getJSONObject(it) }.filter { it.optString("role") == "CHILD" }
                    .joinToString(", ") { it.optString("name") + "님" }
                if (kids.isNotEmpty()) "${kids}과 연결돼 있어요" else "연결된 자녀가 아직 없어요"
            } catch (e: Exception) {
                Join.message(e)
            }
            runOnUiThread {
                linkText?.text = text
                linkText?.setTextColor(if (text.endsWith("있어요")) Ui.INK else Ui.MUTED)
            }
        }
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        render()
    }
}
