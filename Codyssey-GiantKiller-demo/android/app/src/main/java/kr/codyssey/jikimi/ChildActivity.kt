package kr.codyssey.jikimi

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.animation.AccelerateInterpolator
import android.view.animation.DecelerateInterpolator
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import kr.codyssey.jikimi.Ui.button
import kr.codyssey.jikimi.Ui.card
import kr.codyssey.jikimi.Ui.divider
import kr.codyssey.jikimi.Ui.dp
import kr.codyssey.jikimi.Ui.gap
import kr.codyssey.jikimi.Ui.heading
import kr.codyssey.jikimi.Ui.infoBox
import kr.codyssey.jikimi.Ui.kicker
import kr.codyssey.jikimi.Ui.link
import kr.codyssey.jikimi.Ui.listRow
import kr.codyssey.jikimi.Ui.page
import kr.codyssey.jikimi.Ui.split
import kr.codyssey.jikimi.Ui.text
import kr.codyssey.jikimi.Ui.topBar
import org.json.JSONArray
import org.json.JSONObject

/**
 * 자녀 폰 (디자인 시안 14~21, 데이터는 BE API).
 *  - 처음: 로그인(MainActivity) → 가족 만들기(대표가 됨) → 부모님 초대 코드 보내기 / 또는 받은 초대 코드로 참여
 *  - 이후: 아래 탭 3개 [오늘 · 알림 · 기록]. 오늘(통계)이 첫 화면이고 맨 위에 긴급·가족 확인을 짧게, 누르면 사건 상세
 *  - 이름 버튼(○○님 ˅)을 누르면 노랑 윗띠 바로 아래에서 반투명 검정 드로어가 내려온다:
 *    가족 구성원 · 초대 코드 만들기(대표만, BE 규칙) · 로그아웃
 *  - 가족 확인 요청(보냈어요/안 보냈어요)은 BE 푸시(VERIFY_REQUEST)로 받아 알림 버튼 또는 앱의 '가족 확인' 화면에서 답한다
 * BE 공개 범위 그대로: 사건 유형·분류·위험도·요약·분석 상태·대응 상태·발생 시각·지시 종류. 원문·번호는 없다.
 */
class ChildActivity : Activity() {
    companion object {
        const val EXTRA_EVENT = "event_id"
        const val EXTRA_VERIFICATION = "verification_id"
    }

    private val main = Handler(Looper.getMainLooper())
    private var family = JSONObject()
    private var tab = "today"
    private var historyFilter = "all"   // all | open | resolved
    private var inDetail = false
    private var shown = ""          // 지금 그려 둔 데이터 (같으면 다시 안 그려 스크롤이 튀지 않게)
    private var resumed = false
    private var shell: View? = null
    private lateinit var body: LinearLayout
    private lateinit var tabBar: LinearLayout
    private var backCallback: Any? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        SystemBars.apply(this)
        if (Build.VERSION.SDK_INT >= 33) requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 1)
        if (Prefs.family(this).isEmpty()) start() else openApp(intent)
    }

    override fun onResume() {
        super.onResume()
        resumed = true
        if (shell != null) {
            main.removeCallbacks(ticker)
            if (!inDetail) { shown = ""; refresh() }
            main.postDelayed(ticker, 5000)
        }
    }

    override fun onPause() {
        resumed = false
        super.onPause()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        if (Prefs.family(this).isNotEmpty()) openApp(intent)
    }

    // ── 처음: 가족 만들기 또는 초대 코드로 참여 ──
    private fun start() {
        val act = this
        shell = null
        page {
            topBar("가족 연결") { logout() }
            heading("부모님과\n연결해 볼까요?")
            text("가족을 만든 사람이 대표가 되고, 부모님께 초대 코드를 보내요.", 17f, Ui.MUTED)
            gap(16)
            button("가족 만들기 (내가 대표)") {
                Api.io.execute {
                    try {
                        Prefs.set(act, "family" to Api.createFamily(act).getString("id"))
                        runOnUiThread { Join.send(act, "PARENT") { openApp(null) } }
                    } catch (e: Exception) {
                        runOnUiThread { Toast.makeText(act, Join.message(e), Toast.LENGTH_LONG).show() }
                    }
                }
            }
            button("받은 초대 코드로 참여", primary = false) { Join.receive(act, "CHILD", onBack = { start() }) { openApp(null) } }
        }
    }

    private fun logout() {
        val act = this
        Api.io.execute {
            Push.stop(act)
            Prefs.reset(act)
            runOnUiThread { startActivity(Intent(act, MainActivity::class.java)); finish() }
        }
    }

    // ── 앱 틀: 위는 지금 탭 내용(스크롤), 아래는 탭 3개 ──
    private fun parentTitle() = Prefs.parentTitle(this)
    private fun expandIcon() = getDrawable(R.drawable.ic_expand)!!.mutate().apply { setTint(Ui.INK); setBounds(0, 0, dp(18), dp(18)) }
    private fun isRepresentative(): Boolean {
        val m = family.optJSONArray("members") ?: return false
        return (0 until m.length()).map { m.getJSONObject(it) }.any { it.optString("user_id") == Prefs.userId(this) && it.optBoolean("is_representative") }
    }

    private fun openApp(intent: Intent?) {
        if (shell == null) buildShell()
        Push.start(this)
        Api.io.execute {
            runCatching {
                family = Api.family(this)
                // 부모님 이름: 가족의 부모 멤버 이름 (BE 에는 '어머니/아버지' 구분이 없다)
                val members = family.getJSONArray("members")
                val parent = (0 until members.length()).map { members.getJSONObject(it) }.firstOrNull { it.optString("role") == "PARENT" }
                Prefs.set(this, "parent_title" to (parent?.optString("name")?.let { "${it}님" } ?: "부모님"))
                runOnUiThread { if (!inDetail) { shown = ""; refresh() } }
            }.onFailure { e -> if ((e as? Api.HttpError)?.code == 401) runOnUiThread { expired() } }
        }
        val verification = intent?.getStringExtra(EXTRA_VERIFICATION)
        val event = intent?.getStringExtra(EXTRA_EVENT)
        when {
            verification != null -> openVerification(verification)
            event != null -> openEvent(event)
            else -> showTab(tab)
        }
    }

    /** 로그인 만료 (BE JWT): 토큰 지우기·로그인 화면은 Session 이 한다 (Api 가 401 을 받으면 바로). 여기서는 이 화면만 닫는다 */
    private fun expired() {
        Session.expired(this)
        finish()
    }

    private fun buildShell() {
        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setBackgroundColor(Ui.BG) }
        // 노랑 윗띠: 머꼬 고양이 로고 + 오른쪽 "어머니 ˅" (누르면 가족·설정) — 참고 시안
        root.addView(LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setBackgroundColor(Ui.YELLOW)
            setPadding(dp(20), dp(11), dp(12), dp(11)) // 위아래 같게: 로고·이름이 띠 세로 가운데에
            // 로고: 앱 아이콘의 고양이 얼굴만 (노랑 위에 그라데이션 사각형까지 얹으면 노랑끼리 겹쳐 흐려서)
            addView(ImageView(context).apply {
                setImageResource(R.drawable.ic_logo_cat); adjustViewBounds = true; contentDescription = "머꼬"
            }, LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, dp(28)))
            addView(View(context), LinearLayout.LayoutParams(0, 1, 1f))
            parentPill = TextView(context).apply {
                text = parentTitle(); textSize = 16f; setTextColor(Ui.INK); typeface = Ui.regular(context)
                // 누르면 가족·설정이 펼쳐지니 아래 화살표. 24dp 오른쪽 화살표는 글자보다 커서 어색 → 글자 크기에 맞춘 18dp
                setCompoundDrawablesRelative(null, null, expandIcon(), null)
                compoundDrawablePadding = dp(2)
                gravity = Gravity.CENTER_VERTICAL
                setPadding(dp(10), dp(6), dp(4), dp(6))
                setOnClickListener { if (drawerOpen) closeDrawer() else openDrawer() }
            }
            addView(parentPill)
        })
        body = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(20), dp(20), dp(20), dp(32))
        }
        // 가운데 칸: 내용(스크롤) 위에 메뉴 드로어를 겹친다. 이 칸 밖은 잘려서 드로어가 윗띠 아래에서 나오는 것처럼 보인다
        val content = FrameLayout(this)
        content.addView(ScrollView(this).apply { addView(body) }, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
        scrim = View(this).apply { visibility = View.GONE; setOnClickListener { closeDrawer() } } // 드로어 밖을 누르면 닫힘
        content.addView(scrim, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
        drawer = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            visibility = View.GONE
            isClickable = true // 드로어 안을 누르면 닫히지 않게
            setPadding(dp(24), dp(10), dp(24), dp(14))
            setBackgroundColor(DRAWER_BG) // 모서리는 각지게 (둥글게 하지 말 것 — 사용자 요청)
        }
        content.addView(drawer, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, Gravity.TOP))
        root.addView(content, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))
        root.addView(View(this).apply { setBackgroundColor(Ui.LINE) }, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 1))
        tabBar = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setBackgroundColor(Ui.SURFACE)
            setPadding(0, 0, 0, dp(8))
        }
        root.addView(tabBar)
        shell = root
        setContentView(root)
        main.removeCallbacks(ticker)
        main.postDelayed(ticker, 5000)
    }

    private fun drawTabs() {
        tabBar.removeAllViews()
        // 고른 탭: 채운 아이콘 + 검정 굵은 글자 / 안 고른 탭: 선 아이콘 + 회색 글자 (흰 바탕 위 노랑 띠는 대비가 약해서 뺐다)
        // 첫 화면(오늘)이 맨 왼쪽
        for ((key, label, icons) in listOf(Triple("today", "오늘", R.drawable.ic_tab_today_on to R.drawable.ic_tab_today),
            Triple("alerts", "알림", R.drawable.ic_tab_alerts_on to R.drawable.ic_tab_alerts),
            Triple("history", "기록", R.drawable.ic_tab_history_on to R.drawable.ic_tab_history))) {
            val on = key == tab
            val color = if (on) Ui.INK else Color.parseColor("#A1A1A6")
            tabBar.addView(LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                gravity = Gravity.CENTER_HORIZONTAL
                setPadding(0, dp(9), 0, 0)
                setOnClickListener { showTab(key) }
                addView(ImageView(context).apply { setImageResource(if (on) icons.first else icons.second); setColorFilter(color) },
                    LinearLayout.LayoutParams(dp(26), dp(26)))
                addView(TextView(context).apply {
                    text = label; textSize = 13f; setTextColor(color); gravity = Gravity.CENTER
                    typeface = if (on) Ui.bold(context) else Ui.regular(context)
                })
            }, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        }
    }

    private fun showTab(name: String) {
        closeDrawer(now = true)
        if (inDetail) closeDetail()
        tab = name
        shown = ""
        drawTabs()
        refresh()
    }

    /** 지금 탭의 데이터를 받아 그린다. 화면이 보이는 동안 몇 초마다 다시 */
    private fun refresh() {
        val forTab = tab
        val filter = historyFilter
        Api.io.execute {
            val data: Pair<JSONArray, List<JSONObject>>? = try {
                val events = Api.events(this)
                // 알림·오늘 탭: 푸시로 받은 가족 확인 요청 중 아직 답하지 않은 것 (BE 에 목록 API 가 없어 폰이 ID 를 기억)
                val pending = if (forTab == "alerts" || forTab == "today") Prefs.verifications(this).mapNotNull { id ->
                    runCatching { Api.verification(this, id) }.getOrNull()
                        ?.takeIf { it.optString("status") == "PENDING" && it.isNull("my_response") }
                } else emptyList()
                events to pending
            } catch (e: Exception) {
                runOnUiThread {
                    if ((e as? Api.HttpError)?.code == 401) expired()
                    else if (!inDetail && tab == forTab && shown.isEmpty()) message(Join.message(e))
                }
                null
            }
            if (data != null) runOnUiThread {
                val key = data.first.toString() + data.second + filter + parentTitle() + family.optString("id")
                if (inDetail || tab != forTab || key == shown) return@runOnUiThread
                shown = key
                body.removeAllViews()
                val events = (0 until data.first.length()).map { data.first.getJSONObject(it) }
                when (forTab) {
                    "alerts" -> drawAlerts(events, data.second)
                    "today" -> drawToday(events, data.second)
                    else -> drawHistory(events)
                }
            }
        }
    }

    private val ticker = object : Runnable {
        override fun run() {
            if (!resumed) return
            if (!inDetail) refresh()
            main.postDelayed(this, 5000)
        }
    }

    private fun message(s: String) {
        body.removeAllViews()
        body.text(s, 17f, Ui.MUTED, center = true, top = 40)
    }

    private var parentPill: TextView? = null

    /** 제목 줄: 큰 제목 + 개수 (참고 시안 "알림 3") */
    private fun header(title: String, count: Int? = null) {
        parentPill?.text = parentTitle()
        if (Prefs.testMode(this)) body.text("테스트 모드 (예시 데이터)", 13f, Ui.MUTED, top = 0)
        body.addView(LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.BOTTOM
            setPadding(0, dp(10), 0, dp(4))
            addView(TextView(context).apply { text = title; textSize = 25f; setTextColor(Ui.INK); typeface = Ui.bold(context) })
            count?.let { n -> addView(TextView(context).apply {
                text = "$n"; textSize = 17f; setTextColor(Ui.MUTED); typeface = Ui.regular(context); setPadding(dp(10), 0, 0, dp(4))
            }) }
        })
    }

    // ── 메뉴 드로어: 노랑 윗띠 바로 아래에서 내려온다. 위는 가족 구성원(누를 수 없음), 구분선 아래는 할 일 ──
    private val DRAWER_BG = Color.parseColor("#E01C1C1E") // 약간 투명한 검정 (88%)
    private var drawer: LinearLayout? = null
    private var scrim: View? = null
    private var drawerOpen = false
    private var drawerBack: Any? = null

    private fun openDrawer() {
        val d = drawer ?: return
        val members = family.optJSONArray("members")?.let { m -> (0 until m.length()).map { m.getJSONObject(it) } } ?: emptyList()
        val items = mutableListOf<Pair<String, () -> Unit>>()
        if (isRepresentative()) {
            items += "부모님 초대 코드 만들기" to { Join.send(this, "PARENT") { closeToShell() } }
            items += "형제·자매 초대 코드 만들기" to { Join.send(this, "CHILD") { closeToShell() } }
        }
        items += "로그아웃" to { logout() }
        d.removeAllViews()
        d.addView(TextView(this).apply {
            text = "우리 가족"; textSize = 13f; setTextColor(Color.parseColor("#99FFFFFF")); typeface = Ui.regular(context)
            setPadding(0, dp(6), 0, dp(2))
        })
        for (m in members) d.addView(TextView(this).apply {
            text = "${m.optString("name")} · ${if (m.optString("role") == "PARENT") "부모님" else "자녀"}" +
                if (m.optBoolean("is_representative")) " (대표)" else ""
            textSize = 16f; setTextColor(Color.parseColor("#D9FFFFFF")); typeface = Ui.regular(context)
            setPadding(0, dp(5), 0, dp(5))
        })
        d.addView(View(this).apply { setBackgroundColor(Color.parseColor("#33FFFFFF")) },
            LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 1).apply { topMargin = dp(10); bottomMargin = dp(4) })
        for ((label, act) in items) d.addView(TextView(this).apply {
            text = label; textSize = 18f; setTextColor(Color.WHITE); typeface = Ui.bold(context)
            setPadding(0, dp(13), 0, dp(13))
            setOnClickListener { closeDrawer(now = true); act() }
        }, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))
        // 높이를 먼저 재서 윗띠 뒤(잘리는 곳)에 숨겨 두고 아래로 미끄러져 내려온다
        val w = (d.parent as View).width
        d.measure(View.MeasureSpec.makeMeasureSpec(w, View.MeasureSpec.EXACTLY), View.MeasureSpec.makeMeasureSpec(0, View.MeasureSpec.UNSPECIFIED))
        d.animate().cancel()
        d.translationY = -d.measuredHeight.toFloat()
        d.visibility = View.VISIBLE
        scrim?.visibility = View.VISIBLE
        drawerOpen = true
        setDrawerBack(true)
        d.animate().translationY(0f).setDuration(250).setInterpolator(DecelerateInterpolator(2f)).start()
        parentPill?.compoundDrawablesRelative?.get(2)?.let { rotate(it, 180f) }
    }

    private fun closeDrawer(now: Boolean = false) {
        if (!drawerOpen) return
        drawerOpen = false
        setDrawerBack(false)
        scrim?.visibility = View.GONE
        parentPill?.compoundDrawablesRelative?.get(2)?.let { rotate(it, 0f) }
        val d = drawer ?: return
        d.animate().cancel()
        if (now) { d.visibility = View.GONE; return }
        d.animate().translationY(-d.height.toFloat()).setDuration(200).setInterpolator(AccelerateInterpolator(1.5f))
            .withEndAction { if (!drawerOpen) d.visibility = View.GONE }.start()
    }

    /** 이름 옆 화살표: 열리면 위(▲), 닫히면 아래(▼) */
    private fun rotate(icon: android.graphics.drawable.Drawable, to: Float) {
        parentPill?.setCompoundDrawablesRelative(null, null,
            if (to == 0f) expandIcon() else android.graphics.drawable.RotateDrawable().apply {
                drawable = expandIcon(); fromDegrees = to; toDegrees = to; level = 10000; setBounds(icon.bounds)
            }, null)
    }

    // 드로어가 열려 있으면 '뒤로'는 드로어만 닫는다 (안드로이드 13+ 콜백, 그 전은 onBackPressed)
    private fun setDrawerBack(on: Boolean) {
        if (Build.VERSION.SDK_INT < 33) return
        val cb = drawerBack as? android.window.OnBackInvokedCallback
        if (on && cb == null) {
            val c = android.window.OnBackInvokedCallback { closeDrawer() }
            onBackInvokedDispatcher.registerOnBackInvokedCallback(android.window.OnBackInvokedDispatcher.PRIORITY_OVERLAY, c)
            drawerBack = c
        } else if (!on && cb != null) {
            onBackInvokedDispatcher.unregisterOnBackInvokedCallback(cb)
            drawerBack = null
        }
    }

    private fun closeToShell() {
        shell?.let { setContentView(it) }
        shown = ""
        refresh()
    }

    // ── 시안 14: 알림 목록. 가족 확인 요청 → 해결 안 된 긴급 1건 → 나머지 사건 ──
    private fun drawAlerts(events: List<JSONObject>, pending: List<JSONObject>) {
        val open = events.count { it.optString("status") in setOf("OPEN", "ACKNOWLEDGED") }
        header("알림", open + pending.size)
        if (events.isEmpty() && pending.isEmpty()) {
            body.card { text("아직 알림이 없어요.\n${parentTitle()} 폰에 위험한 연락이 오면 여기와 알림으로 알려드려요.", 17f, Ui.MUTED, top = 12) }
            if (!Push.available(this)) body.text("※ 이 앱은 아직 푸시 설정(Firebase)이 없어 새 알림이 오지 않아요. 앱을 열면 기록은 보여요.", 14f, Ui.MUTED, top = 12)
            return
        }
        val urgent = events.filter { isUrgent(it) }  // 긴급은 모두 맨 위 카드로 (오늘 화면의 "긴급 N건"이 여기로 온다)
        urgent.forEach { urgentCard(it) }
        val rest = events.filter { it !in urgent }
        if (rest.isEmpty() && pending.isEmpty()) return
        body.text(if (urgent.isNotEmpty()) "다른 알림" else "최근 알림", 15f, Ui.MUTED, top = 28)
        for (v in pending) {
            val e = events.firstOrNull { it.getString("id") == v.optString("event_id") }
            alertRow("이 문자, 직접 보내셨나요?", e?.optString("summary")?.takeIf { it.isNotEmpty() && it != "null" } ?: "가족 확인 요청",
                "답변 필요", Ui.INK, fmtTime(e?.optString("occurred_at").orEmpty())) { openVerification(v.getString("id")) }
        }
        for (e in rest) {
            val (state, color) = when (e.optString("status")) {
                "OPEN" -> "확인 전" to Ui.INK
                "ACKNOWLEDGED" -> "확인했어요" to Ui.MUTED
                "RESOLVED" -> "해결됨" to Ui.MUTED
                else -> "" to Ui.MUTED
            }
            alertRow(eventTitle(e), e.optString("summary").takeIf { it.isNotEmpty() && it != "null" } ?: riskLabel(e),
                state, color, fmtTime(e.optString("occurred_at"))) { openEvent(e.getString("id")) }
        }
    }

    /** 알림 한 줄 (참고 시안): 굵은 제목 / 회색 한 줄 설명 / 아래 왼쪽 상태 · 오른쪽 시간, 오른쪽 ›, 아래 구분선 */
    private fun alertRow(title: String, sub: String, state: String, stateColor: Int, time: String, onClick: () -> Unit) {
        body.addView(LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(0, dp(16), 0, dp(16))
            setOnClickListener { onClick() }
            addView(LinearLayout(context).apply {
                orientation = LinearLayout.VERTICAL
                addView(TextView(context).apply { text = title; textSize = 19f; setTextColor(Ui.INK); typeface = Ui.bold(context) })
                addView(TextView(context).apply {
                    text = sub; textSize = 15f; setTextColor(Ui.MUTED); typeface = Ui.regular(context); maxLines = 1
                    ellipsize = android.text.TextUtils.TruncateAt.END; setPadding(0, dp(6), 0, 0)
                })
                addView(LinearLayout(context).apply {
                    orientation = LinearLayout.HORIZONTAL
                    setPadding(0, dp(12), 0, 0)
                    addView(TextView(context).apply { text = state; textSize = 14f; setTextColor(stateColor); typeface = Ui.bold(context) },
                        LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
                    addView(TextView(context).apply { text = time; textSize = 14f; setTextColor(Ui.MUTED); typeface = Ui.regular(context) })
                })
            }, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
            addView(ImageView(context).apply { setImageResource(R.drawable.ic_chevron); setColorFilter(Color.parseColor("#A1A1A6")) },
                LinearLayout.LayoutParams(dp(28), dp(28)).apply { leftMargin = dp(12) })
        })
        body.addView(View(this).apply { setBackgroundColor(Ui.LINE) },
            LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(1)))
    }

    /** 긴급: 해결 안 된 앱 설치, 또는 위험도 높음 */
    private fun isUrgent(e: JSONObject) = e.optString("status") in setOf("OPEN", "ACKNOWLEDGED") &&
        (e.optString("event_type") == "APP_INSTALL" || e.optString("risk_level").equals("HIGH", true))

    private fun urgentCard(e: JSONObject) {
        // 참고 시안: 연분홍 칸, 빨강 "긴급 · 지금 확인" + 오른쪽 시간, 굵은 제목, 회색 설명, 검정 버튼
        // (시안의 "어머니께 전화하기"는 BE 에 전화번호가 없어 "사건 자세히 보기"로)
        // 긴급은 더 강하게: 빨간 테두리 + 조금 짙은 분홍 + 빨간 제목
        body.card(line = Ui.DANGER, fill = Color.parseColor("#FFE8E6"), pad = 22) {
            addView(LinearLayout(context).apply {
                orientation = LinearLayout.HORIZONTAL
                setPadding(0, dp(12), 0, 0)
                addView(TextView(context).apply {
                    text = "긴급 · " + if (e.optString("status") == "ACKNOWLEDGED") "확인함 · 미해결" else "지금 확인"
                    textSize = 15f; setTextColor(Ui.DANGER); typeface = Ui.bold(context)
                }, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
                addView(TextView(context).apply { text = fmtTime(e.optString("occurred_at")); textSize = 14f; setTextColor(Ui.MUTED); typeface = Ui.regular(context) })
            })
            text("${parentTitle()}께 연락해 주세요", 23f, Ui.DANGER, bold = true, top = 12)
            text(e.optString("summary").takeIf { it.isNotEmpty() && it != "null" } ?: eventTitle(e), 17f, Ui.MUTED, top = 8)
            button("사건 자세히 보기") { openEvent(e.getString("id")) }
        }
    }

    // ── 시안 15: 오늘 요약 (BE 사건 목록에서 오늘 것만 센다). 첫 화면이라 맨 위에 긴급·가족 확인을 짧게 ──
    private fun drawToday(events: List<JSONObject>, pending: List<JSONObject>) {
        header("오늘의 연락")
        urgentStrip(events.filter { isUrgent(it) })
        if (pending.isNotEmpty()) strip("가족 확인 · 답변 필요" + if (pending.size > 1) " ${pending.size}건" else "", Ui.INK,
            "이 문자, 직접 보내셨나요?", Ui.LINE, Ui.SURFACE) { pending.singleOrNull()?.let { openVerification(it.getString("id")) } ?: showTab("alerts") }
        val today = events.filter { it.optString("occurred_at").take(10) == java.time.LocalDate.now().toString() }
        body.text(if (today.isNotEmpty()) "주의가 필요한 연락 ${today.size}건을 알려드렸어요." else "오늘은 주의가 필요한 연락이 없었어요.",
            17f, Ui.INK, top = 8)
        body.infoBox(listOf(
            "문자" to "${today.count { it.optString("event_type") == "ALERT" }}건",
            "통화" to "${today.count { it.optString("event_type") == "CALL" }}건",
            "앱 설치" to "${today.count { it.optString("event_type") == "APP_INSTALL" }}건",
        ))
        if (today.isNotEmpty()) {
            body.text("오늘 있었던 일", 16f, Ui.MUTED, bold = true, top = 24)
            body.card(pad = 18) {
                today.forEachIndexed { i, e ->
                    if (i > 0) divider()
                    eventRow(e)
                }
            }
        }
        body.text("평범한 문자는 부모님 폰 안에서 처리하고 서버로 보내지 않아요", 14f, Ui.MUTED, top = 16)
    }

    /** 오늘 화면 맨 위 긴급 한 줄: 한 건이면 그 사건 제목 → 사건 상세, 여러 건이면 "긴급 N건" → 알림 탭(긴급 목록) */
    private fun urgentStrip(urgent: List<JSONObject>) {
        if (urgent.isEmpty()) return
        val one = urgent.singleOrNull()
        strip(if (one != null) "긴급 · ${parentTitle()}께 연락해 주세요" else "긴급 ${urgent.size}건 · ${parentTitle()}께 연락해 주세요", Ui.DANGER,
            if (one != null) eventTitle(one) else "알림에서 모두 보기", Ui.DANGER, Color.parseColor("#FFE8E6")) {
            one?.let { openEvent(it.getString("id")) } ?: showTab("alerts")
        }
    }

    /** 짧은 한 줄 칸: 위 작은 제목(색) / 굵은 한 줄 + 오른쪽 › */
    private fun strip(kick: String, kickColor: Int, title: String, line: Int, fill: Int, onClick: () -> Unit) {
        body.card(line = line, fill = fill, pad = 16, onClick = onClick) {
            text(kick, 14f, kickColor, bold = true, top = 10)
            addView(LinearLayout(context).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
                setPadding(0, dp(4), 0, 0)
                addView(TextView(context).apply {
                    text = title; textSize = 18f; setTextColor(Ui.INK); typeface = Ui.bold(context)
                    maxLines = 1; ellipsize = android.text.TextUtils.TruncateAt.END
                }, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
                addView(ImageView(context).apply { setImageResource(R.drawable.ic_chevron); setColorFilter(Ui.INK) },
                    LinearLayout.LayoutParams(dp(24), dp(24)))
            })
        }
    }


    // ── 시안 16: 사건 기록 (전체·미해결·해결됨, 날짜별) ──
    private fun drawHistory(all: List<JSONObject>) {
        header("사건 기록")
        body.addView(LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding(0, dp(16), 0, 0)
            for ((key, label) in listOf("all" to "전체", "open" to "미해결", "resolved" to "해결됨")) {
                val on = key == historyFilter
                addView(LinearLayout(context).apply {
                    orientation = LinearLayout.VERTICAL
                    setOnClickListener { historyFilter = key; shown = ""; refresh() }
                    addView(TextView(context).apply {
                        text = label; textSize = 17f; gravity = Gravity.CENTER
                        setTextColor(if (on) Ui.INK else Ui.MUTED); typeface = if (on) Ui.bold(context) else Ui.regular(context)
                        setPadding(0, dp(8), 0, dp(10))
                    })
                    addView(View(context).apply { setBackgroundColor(if (on) Ui.YELLOW else Ui.LINE) },
                        LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, if (on) dp(3) else 1))
                }, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
            }
        })
        val events = all.filter {
            when (historyFilter) {
                "open" -> it.optString("status") in setOf("OPEN", "ACKNOWLEDGED")
                "resolved" -> it.optString("status") == "RESOLVED"
                else -> true
            }
        }
        if (events.isEmpty()) body.text(if (historyFilter == "all") "기록이 없어요" else "해당하는 사건이 없어요", 16f, Ui.MUTED, center = true, top = 32)
        for ((date, group) in events.groupBy { it.optString("occurred_at").take(10) }) {
            body.text(fmtDate(date), 16f, Ui.MUTED, bold = true, top = 20)
            body.card(pad = 18) {
                group.forEachIndexed { i, e ->
                    if (i > 0) divider()
                    eventRow(e, clock = true)
                }
            }
        }
        body.text("문자 원문 없이 사건 요약만 보관해요", 14f, Ui.MUTED, top = 16)
    }

    private fun LinearLayout.eventRow(e: JSONObject, clock: Boolean = false) {
        val state = STATUS_LABEL[e.optString("status")] ?: ""
        val time = if (clock) localTime(e.optString("occurred_at")).let { it?.let { t -> "%02d:%02d".format(t.hour, t.minute) } ?: "" }
                   else fmtTime(e.optString("occurred_at"))
        listRow(eventTitle(e), listOf(time, state).filter { it.isNotEmpty() }.joinToString(" · "),
            if (isUrgent(e)) "긴급" else "", Ui.DANGER) { openEvent(e.getString("id")) }
    }

    /** 목록의 짧은 사건 이름 (BE 사건 유형·분류) */
    private fun eventTitle(e: JSONObject): String = when (e.optString("event_type")) {
        "APP_INSTALL" -> "위험할 수 있는 앱 설치"
        "CALL" -> "주의가 필요한 통화"
        else -> if (e.optString("classification") == "CHILD_IMPERSONATION") "자녀 사칭 의심 문자" else "주의가 필요한 문자"
    }

    private fun riskLabel(e: JSONObject) = RISK_LABEL[e.optString("risk_level").uppercase()] ?: ""

    // ── 상세 화면 공통 틀: 위 막대 + 스크롤 내용 + 아래 고정 버튼 ──
    private fun detailFrame(title: String, build: LinearLayout.() -> Unit, actions: LinearLayout.() -> Unit) {
        inDetail = true
        setBack(true)
        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setBackgroundColor(Ui.BG) }
        val content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(20), dp(16), dp(20), dp(24))
            topBar(title) { closeDetail() }
            build()
        }
        root.addView(ScrollView(this).apply { addView(content) }, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))
        root.addView(LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(20), 0, dp(20), dp(16))
            actions()
        })
        setContentView(root)
    }

    private fun closeDetail() {
        inDetail = false
        setBack(false)
        shell?.let { setContentView(it) } ?: buildShell()
        shown = ""
        drawTabs()
        refresh()
    }

    private fun openEvent(id: String) {
        Api.io.execute {
            val e = runCatching { Api.event(this, id) }
            runOnUiThread {
                e.onSuccess { eventDetail(it) }.onFailure { Toast.makeText(this, Join.message(it as Exception), Toast.LENGTH_LONG).show() }
            }
        }
    }

    // ── 시안 18: 가족 확인 요청 (BE /verify) ──
    private fun openVerification(id: String) {
        Prefs.addVerification(this, id)
        Api.io.execute {
            val r = runCatching {
                val v = Api.verification(this, id)
                v to runCatching { Api.event(this, v.getString("event_id")) }.getOrNull()
            }
            runOnUiThread {
                r.onSuccess { (v, e) ->
                    if (v.optString("status") != "PENDING" || !v.isNull("my_response")) e?.let { eventDetail(it) } ?: showTab("alerts")
                    else verify(v, e)
                }.onFailure { Toast.makeText(this, Join.message(it as Exception), Toast.LENGTH_LONG).show() }
            }
        }
    }

    private fun verify(v: JSONObject, e: JSONObject?) {
        val pt = parentTitle()
        detailFrame("가족 확인", {
            val who = pt.removeSuffix("님")
            val batchim = who.lastOrNull()?.let { it in '가'..'힣' && (it - '가') % 28 != 0 } ?: false
            text("$who${if (batchim) "이" else "가"} 받은 문자", 15f, Ui.MUTED, top = 20)
            heading("이 문자,\n직접 보내셨나요?", top = 8)
            text("보낸 사람이 가족인지 확인해 주세요.", 17f, Ui.MUTED, top = 12)
            card(fill = Ui.FILL, line = Ui.FILL, pad = 22) {
                text("문자 요약", 14f, Ui.MUTED, top = 14)
                text(e?.optString("summary")?.takeIf { it.isNotEmpty() && it != "null" } ?: "가족을 사칭한 것으로 의심되는 문자예요", 20f, Ui.INK, top = 10)
                gap(12)
            }
            gap(20); divider()
            text("가족 ${v.optInt("target_count")}명 중 ${v.optInt("responded_count")}명이 답했어요.", 15f, Ui.MUTED, top = 16)
        }) {
            text("답변은 ${pt}께 바로 알려드려요.", 14f, Ui.MUTED, top = 8)
            split {
                button("내가 보냈어요", outline = true) { answer(v, "SENT") }
                button("안 보냈어요", outline = true) { answer(v, "NOT_SENT") }
            }
        }
    }

    private fun answer(v: JSONObject, response: String) {
        Api.io.execute {
            val msg = try {
                Api.respond(this, v.getString("id"), response)
                if (response == "SENT") "보냈다고 ${parentTitle()}께 알려드렸어요" else "안 보냈다고 ${parentTitle()}께 알려드렸어요"
            } catch (e: Exception) {
                if ((e as? Api.HttpError)?.code == 409) "이미 답했거나 확인이 끝난 요청이에요" else Join.message(e)
            }
            runOnUiThread {
                Toast.makeText(this, msg, Toast.LENGTH_LONG).show()
                openEvent(v.getString("event_id")) // 같은 사건의 상세로
            }
        }
    }

    // ── 시안 17·19·20·21: 사건 상세 (BE 상세: 유형·분류·위험도·요약·상태·지시 종류) ──
    private fun eventDetail(e: JSONObject) {
        val pt = parentTitle()
        val type = e.optString("event_type")
        val status = e.optString("status")
        val urgent = isUrgent(e)
        val bar = when {
            urgent -> "긴급 알림"
            type == "CALL" -> "통화 알림"
            type == "ALERT" && e.optString("classification") != "CHILD_IMPERSONATION" -> "문자 알림"
            else -> "사건 상세"
        }
        detailFrame(bar, {
            if (urgent) kicker("긴급 · ${STATUS_LABEL[status] ?: "확인 전"}", top = 20)
            else kicker(color = Ui.MUTED, top = 20, s = when {
                type == "APP_INSTALL" -> "위험할 수 있는 앱 설치"
                type == "CALL" -> "주의가 필요한 통화"
                e.optString("classification") == "CHILD_IMPERSONATION" -> "자녀 사칭 의심"
                else -> "주의가 필요한 문자"
            })
            when {
                urgent -> {
                    heading("${pt}께 연락해 주세요", top = 8)
                }
                type == "CALL" -> heading("${pt}께 상황을 확인해 주세요", top = 8)
                e.optString("classification") == "CHILD_IMPERSONATION" -> heading("가족을 사칭한 문자예요", top = 8)
                else -> heading("${pt}께 의심 문자가 왔어요", top = 8)
            }
            e.optString("summary").takeIf { it.isNotEmpty() && it != "null" }?.let { text(it, 18f, Ui.MUTED, top = 10) }

            val rows = mutableListOf<Pair<String, String>>()
            riskLabel(e).takeIf { it.isNotEmpty() }?.let { rows += "위험도" to it }
            val instr = e.optJSONArray("instructions")?.let { a -> (0 until a.length()).map { a.getJSONObject(it).optString("instruction_type") } }
                ?: emptyList()
            if (instr.isNotEmpty()) rows += "요구한 것" to instr.joinToString(", ") { INSTR_LABEL[it] ?: it }
            if (type == "CALL" && e.optString("analysis_status") == "FAILED") rows += "분석" to "실패 (다시 확인 필요)"
            rows += "발생 시각" to fmtTime(e.optString("occurred_at"))
            infoBox(rows)
            if (type == "ALERT") text("문자 원문은 보관하지 않아요.", 14f, Ui.MUTED, top = 8)
            text("현재 상태 · ${STATUS_LABEL[status] ?: status}", 15f, Ui.MUTED,
                bold = status == "OPEN", top = 16)
        }) {
            when (status) {
                "OPEN" -> split {
                    button("확인했어요", primary = false) { setStatus(e.getString("id"), "ACKNOWLEDGED") }
                    button("해결됐어요") { setStatus(e.getString("id"), "RESOLVED") }
                }
                "ACKNOWLEDGED" -> button("해결됐어요") { setStatus(e.getString("id"), "RESOLVED") }
            }
        }
    }

    private fun setStatus(id: String, status: String) {
        Api.io.execute {
            val err = runCatching { Api.setStatus(this, id, status) }.exceptionOrNull()
            runOnUiThread {
                err?.let { Toast.makeText(this, if ((it as? Api.HttpError)?.code == 409) "이미 해결된 사건이에요" else Join.message(it as Exception),
                    Toast.LENGTH_LONG).show() }
                if (status == "RESOLVED" && err == null) closeDetail() else openEvent(id)
            }
        }
    }

    // 상세 화면에서 '뒤로' → 목록으로 (안드로이드 13+ 는 뒤로 가기 콜백, 그 전은 onBackPressed)
    private fun setBack(on: Boolean) {
        if (Build.VERSION.SDK_INT < 33) return
        val cb = backCallback as? android.window.OnBackInvokedCallback
        if (on && cb == null) {
            val c = android.window.OnBackInvokedCallback { closeDetail() }
            onBackInvokedDispatcher.registerOnBackInvokedCallback(android.window.OnBackInvokedDispatcher.PRIORITY_DEFAULT, c)
            backCallback = c
        } else if (!on && cb != null) {
            onBackInvokedDispatcher.unregisterOnBackInvokedCallback(cb)
            backCallback = null
        }
    }

    @Deprecated("안드로이드 12 이하용")
    override fun onBackPressed() {
        if (drawerOpen) closeDrawer() else if (inDetail) closeDetail() else @Suppress("DEPRECATION") super.onBackPressed()
    }

    /** BE 시각(UTC 등 시간대 포함) → 이 폰의 시각 */
    private fun localTime(iso: String): java.time.LocalDateTime? = runCatching {
        java.time.OffsetDateTime.parse(iso).atZoneSameInstant(java.time.ZoneId.systemDefault()).toLocalDateTime()
    }.getOrNull()

    private fun fmtTime(iso: String): String {
        val t = localTime(iso) ?: return ""
        val time = "${if (t.hour < 12) "오전" else "오후"} ${if (t.hour % 12 == 0) 12 else t.hour % 12}:${"%02d".format(t.minute)}"
        return if (t.toLocalDate() != java.time.LocalDate.now()) "${t.monthValue}/${t.dayOfMonth} $time" else time
    }

    private fun fmtDate(date: String): String =
        if (date.length < 10) date
        else if (date == java.time.LocalDate.now().toString()) "오늘"
        else "${date.substring(5, 7).toInt()}월 ${date.substring(8, 10).toInt()}일"
}

// BE 값 → 화면 이름표
private val STATUS_LABEL = mapOf("OPEN" to "확인 전", "ACKNOWLEDGED" to "확인했어요", "RESOLVED" to "해결됐어요", "NOT_REQUIRED" to "대응 필요 없음")
private val RISK_LABEL = mapOf("HIGH" to "위험 높음", "MEDIUM" to "주의", "LOW" to "낮음")
// 지시 종류 (AI 서버 docs/AI_API.md 값). 모르는 값은 그대로 보여 준다
private val INSTR_LABEL = mapOf("INSTALL_APP" to "앱 설치", "INSTALL_REMOTE" to "원격 제어 앱", "TRANSFER" to "계좌 이체",
    "CASH" to "현금 인출·전달", "SHARE_INFO" to "개인정보·인증번호")
