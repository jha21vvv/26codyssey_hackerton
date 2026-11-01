package kr.codyssey.jikimi

import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.graphics.Color
import android.graphics.PixelFormat
import android.util.TypedValue
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.view.Gravity
import android.view.WindowManager
import android.widget.Button
import android.widget.FrameLayout
import android.widget.ScrollView
import android.view.View
import android.view.WindowInsets
import android.widget.LinearLayout
import android.widget.TextView
import android.app.Notification

// ── 위험 경고창·안내 카드: 팀원 A안 코드 그대로 (사용자 결정 10/31: "수정하지 말고 그대로 적용") ──
/** 화면을 덮는 경고창 ("다른 앱 위에 표시" 권한). frontend/parent.html 의 빨간 경고창과 같은 모양. */
object Overlay {
    private val main = Handler(Looper.getMainLooper())
    private val queue = ArrayDeque<Pair<String, String>>()
    private var showing = false

    fun canShow(ctx: Context) = Settings.canDrawOverlays(ctx)

    fun show(ctx: Context, title: String, text: String, button: String = "확인했어요") {
        main.post { draw(ctx, title, text, button) }
    }

    private fun draw(ctx: Context, title: String, text: String, button: String) {
        if (!canShow(ctx)) return
        if (showing) { queue.add(title to text); return }
        showing = true
        val app = ctx.applicationContext
        val wm = app.getSystemService(Context.WINDOW_SERVICE) as WindowManager
        fun sp(v: Float) = TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_SP, v, app.resources.displayMetrics)

        val d = app.resources.displayMetrics.density
        // 머꼬 A안 · 위험(멈춤) 단계: 화면 전체 빨강·흰 굵은 사선 띠 + 흰 내용 카드
        // 자리: 상태바 아래 ~ 내비게이션 바 위 사이 정가운데 (StopRoot, 사용자 요청 10/31 "경고창이 화면 가운데에").
        // A안에서 바꾼 건 자리·크기뿐, 모양은 그대로
        val root = StopRoot(app, side = (22 * d).toInt()).apply {
            background = Ui.StripedBorderDrawable(app, Ui.Stage.DANGER)
        }
        val card = FitCard(app).apply {
            orientation = LinearLayout.VERTICAL
            val p = (22 * d).toInt()
            setPadding(p, p, p, p)
            background = android.graphics.drawable.GradientDrawable().apply {
                cornerRadius = Ui.RADIUS_DP * d
                setColor(Ui.PANEL)
            }
        }
        root.addView(card)
        // 빨간 "멈추세요" 띠 (손바닥 아이콘 + 글자)
        card.addView(LinearLayout(app).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            val p = (12 * d).toInt()
            setPadding(p, p, p, p)
            background = android.graphics.drawable.GradientDrawable().apply {
                cornerRadius = Ui.RADIUS_DP * d
                setColor(Ui.DANGER_RED)
            }
            addView(android.widget.ImageView(app).apply { setImageResource(R.drawable.ic_danger) },
                LinearLayout.LayoutParams((48 * d).toInt(), (48 * d).toInt()))
            addView(TextView(app).apply {
                this.text = "멈추세요"
                setTextColor(Color.WHITE)
                textSize = 26f
                typeface = android.graphics.Typeface.DEFAULT_BOLD
                setPadding((12 * d).toInt(), 0, 0, 0)
            })
        })
        fun label(s: String, size: Float, bold: Boolean = false) = TextView(app).apply {
            Ui.phrase(this) // 낱말 단위 줄바꿈 (사용자 요청 10/31 "자연스럽게")
            this.text = Ui.keep(s)
            setTextColor(Ui.TEXT)
            textSize = size
            setLineSpacing(0f, 1.2f)
            if (bold) typeface = android.graphics.Typeface.DEFAULT_BOLD
            setPadding(0, sp(16f).toInt(), 0, 0)
        }
        // 제목·설명은 스크롤 칸에: 화면이 작거나 글이 길면 이 칸만 줄고, 위 '멈추세요' 띠·아래 버튼은 항상 화면 안에
        val words = LinearLayout(app).apply { orientation = LinearLayout.VERTICAL }
        words.addView(label(title, 34f, bold = true).apply { setTextColor(Ui.TEXT) })
        words.addView(label(text, 21f).apply { setTextColor(Ui.TEXT_SUB) })
        card.scroll = ScrollView(app).apply { addView(words) }
        card.addView(card.scroll, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT))
        val params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.MATCH_PARENT,
            WindowManager.LayoutParams.MATCH_PARENT,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
            PixelFormat.TRANSLUCENT,
        )
        card.addView(Button(app).apply {
            this.text = button
            textSize = 22f
            isAllCaps = false
            typeface = android.graphics.Typeface.DEFAULT_BOLD
            minHeight = (72 * d).toInt()
            minimumHeight = minHeight
            stateListAnimator = null
            setTextColor(Color.WHITE)
            background = android.graphics.drawable.GradientDrawable().apply {
                cornerRadius = Ui.RADIUS_DP * d
                setColor(Ui.TEXT)
            }
            setOnClickListener {
                wm.removeView(root)
                showing = false
                queue.removeFirstOrNull()?.let { (t, x) -> show(ctx, t, x) }
            }
        }, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT)
            .apply { topMargin = (24 * d).toInt() })
        wm.addView(root, params)
    }
}

/**
 * 급하지 않은 설명을 화면 위쪽에 크게 보여 주는 초록 안내 카드 (빨간 경고창과 구분).
 * 안드로이드 알림은 기본이 접힌 한 줄이라 어르신이 끝까지 읽기 어렵다 → 카드로 전부 보여 준다.
 * 화면 위쪽만 차지하고, 아래 화면은 그대로 쓸 수 있다. "알겠어요"를 누르거나 2분 뒤 사라진다.
 */
object InfoCard {
    private val main = Handler(Looper.getMainLooper())
    private var current: android.view.View? = null
    private var currentKey: String? = null // 지금 카드가 어느 가족 확인 건인지 (결과가 오면 같은 건만 닫는다)

    /** stage: 안심(초록, 기본) · 주의(노랑, 가족 확인 중처럼 잠시 멈춰야 할 때) — 팀원 A안의 단계 색 그대로 */
    /** key: 가족 확인 건 ID. 같은 건의 결과가 오면 dismiss(key) 로 이 카드를 닫는다 */
    fun show(ctx: Context, title: String, text: String, stage: Ui.Stage = Ui.Stage.SAFE, key: String? = null) {
        main.post {
            val before = current
            draw(ctx, title, text, stage)
            if (current != null && current !== before) currentKey = key // 새 카드가 실제로 떴을 때만
        }
    }

    /** 같은 가족 확인 건의 카드만 닫는다 (다른 사건 카드는 그대로) */
    fun dismiss(ctx: Context, key: String) {
        main.post {
            val card = current ?: return@post
            if (currentKey != key) return@post
            val wm = ctx.applicationContext.getSystemService(Context.WINDOW_SERVICE) as WindowManager
            runCatching { wm.removeView(card) }
            current = null
            currentKey = null
        }
    }

    private fun draw(ctx: Context, title: String, text: String, stage: Ui.Stage) {
        if (!Overlay.canShow(ctx)) return
        val app = ctx.applicationContext
        val wm = app.getSystemService(Context.WINDOW_SERVICE) as WindowManager
        current?.let { runCatching { wm.removeView(it) } }  // 새 안내가 오면 바꿔 보여 준다
        val d = app.resources.displayMetrics.density
        // 머꼬 A안 · 안심(초록)/주의(노랑) 단계: 사선 줄무늬 테두리 + 흰 내용 카드
        val card = Ui.stripedFrame(app, stage).apply { elevation = 12 * d }
        val body = LinearLayout(app).apply {
            orientation = LinearLayout.VERTICAL
            setPadding((18 * d).toInt(), (6 * d).toInt(), (18 * d).toInt(), (14 * d).toInt())
            background = android.graphics.drawable.GradientDrawable().apply {
                cornerRadius = 2 * d
                setColor(Ui.PANEL)
            }
        }
        card.addView(body, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT))
        body.addView(Ui.stageHeader(app, stage, (if (stage == Ui.Stage.CAUTION) "주의" else "안심") + " · 부모님 지킴이"))
        body.addView(TextView(app).apply {
            Ui.phrase(this)
            this.text = Ui.keep(title)
            textSize = 24f
            setTextColor(Ui.TEXT)
            typeface = android.graphics.Typeface.DEFAULT_BOLD
        })
        body.addView(TextView(app).apply {
            Ui.phrase(this)
            this.text = Ui.keep(text)
            textSize = 20f
            setTextColor(Ui.TEXT_SUB)
            setLineSpacing(0f, 1.25f)
            setPadding(0, (8 * d).toInt(), 0, (12 * d).toInt())
        })
        val params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.MATCH_PARENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
            PixelFormat.TRANSLUCENT,
        ).apply {
            gravity = Gravity.TOP
            x = 0
            // 푸시 알림(헤드업, 답장 버튼까지 약 170dp)이 뜨는 위쪽을 피해 아래에 (사용자 요청 10/31, A안은 36dp)
            y = (200 * d).toInt()
            horizontalMargin = 0.03f
        }
        fun close() {
            if (current === card) {
                runCatching { wm.removeView(card) }
                current = null
            }
        }
        body.addView(Button(app).apply {
            this.text = "알겠어요"
            textSize = 20f
            isAllCaps = false
            typeface = android.graphics.Typeface.DEFAULT_BOLD
            minHeight = (64 * d).toInt()
            minimumHeight = minHeight
            stateListAnimator = null
            setTextColor(Color.WHITE)
            background = android.graphics.drawable.GradientDrawable().apply {
                cornerRadius = Ui.RADIUS_DP * d
                setColor(if (stage == Ui.Stage.CAUTION) Ui.TEXT else Ui.SAFE) // 주의 카드에 초록 버튼은 '안심'으로 읽혀서 진한 색
            }
            setOnClickListener { close() }
        }, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT))
        wm.addView(card, params)
        current = card
        main.postDelayed({ close() }, 120_000)
    }
}

/** 급하지 않은 설명은 일반 알림 하나로 */
object Notifier {
    const val CH_EXPLAIN = "explain"
    const val CH_SERVICE = "service"
    // 자녀 폰
    const val CH_CONFIRM = "confirm"
    const val CH_WARNING = "warning"
    const val CH_URGENT = "urgent"

    fun channels(ctx: Context) {
        val nm = ctx.getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel(CH_EXPLAIN, "쉬운 설명", NotificationManager.IMPORTANCE_HIGH))
        nm.createNotificationChannel(NotificationChannel(CH_SERVICE, "지킴이 실행 중", NotificationManager.IMPORTANCE_MIN))
        nm.createNotificationChannel(NotificationChannel(CH_CONFIRM, "자녀 확인 요청", NotificationManager.IMPORTANCE_HIGH))
        nm.createNotificationChannel(NotificationChannel(CH_WARNING, "사기 의심 알림", NotificationManager.IMPORTANCE_HIGH))
        nm.createNotificationChannel(NotificationChannel(CH_URGENT, "긴급 알림", NotificationManager.IMPORTANCE_HIGH).apply {
            enableVibration(true)
            vibrationPattern = longArrayOf(0, 500, 200, 500, 200, 500)
        })
    }

    /** 답한 뒤 확인 요청 알림의 버튼을 없애고 결과 문구로 바꾼다 */
    fun replaceText(ctx: Context, id: Int, title: String, text: String) {
        val n = Notification.Builder(ctx, CH_CONFIRM)
            .setSmallIcon(android.R.drawable.ic_lock_lock)
            .setContentTitle(title)
            .setContentText(text)
            .setOnlyAlertOnce(true)
            .setAutoCancel(true)
            .build()
        ctx.getSystemService(NotificationManager::class.java).notify(id, n)
    }

    fun explain(ctx: Context, id: Int, title: String, text: String) {
        val n = Notification.Builder(ctx, CH_EXPLAIN)
            .setSmallIcon(android.R.drawable.ic_lock_lock)
            .setContentTitle(title)
            .setContentText(text)
            .setStyle(Notification.BigTextStyle().bigText(text))
            .setAutoCancel(true)
            .build()
        ctx.getSystemService(NotificationManager::class.java).notify(id, n)
    }

    fun service(ctx: Context): Notification =
        Notification.Builder(ctx, CH_SERVICE)
            .setSmallIcon(android.R.drawable.ic_lock_lock)
            .setContentTitle("지킴이가 켜져 있어요")
            .setContentText("위험한 연락이 오면 알려드려요.")
            .setOngoing(true)
            .build()
}

/**
 * 경고창 바탕 (화면 전체 줄무늬). 카드를 상태바 아래 ~ 내비게이션 바(3버튼 바 포함) 위 사이 정가운데에 둔다
 * → 버튼이 화면 밖으로 잘리지 않는다. (예전엔 위 200dp 헤드업 자리를 피하느라 아래로 치우쳤다)
 * 카드가 남는 높이보다 길면 FitCard 가 글 칸만 줄인다.
 */
private class StopRoot(ctx: Context, private val side: Int) : FrameLayout(ctx) {
    // 시스템이 창 바 높이를 알려 주기 전까지의 기본값
    private var barTop = dimen(ctx, "status_bar_height")
    private var barBottom = dimen(ctx, "navigation_bar_height")

    init {
        // 실제 시스템 바 높이: 이 창 기준이라, 창이 내비게이션 바 위에서 끝나면(갤럭시 3버튼) 0 이 온다 → 그대로 쓴다
        // (0 을 '값 없음'으로 보고 기본값을 남기면 바 높이를 두 번 빼서 카드가 위아래로 치우친다)
        setOnApplyWindowInsetsListener { _, insets ->
            if (android.os.Build.VERSION.SDK_INT >= 30) {
                val i = insets.getInsets(WindowInsets.Type.systemBars() or WindowInsets.Type.displayCutout())
                barTop = i.top
                barBottom = i.bottom
            } else {
                @Suppress("DEPRECATION") run {
                    barTop = insets.systemWindowInsetTop
                    barBottom = insets.systemWindowInsetBottom
                }
            }
            requestLayout()
            insets
        }
    }

    override fun onMeasure(widthSpec: Int, heightSpec: Int) {
        val w = MeasureSpec.getSize(widthSpec)
        val h = MeasureSpec.getSize(heightSpec)
        val card = getChildAt(0)
        val room = (h - barTop - barBottom - 2 * side).coerceAtLeast(0)
        card?.measure(MeasureSpec.makeMeasureSpec(w - 2 * side, MeasureSpec.EXACTLY), MeasureSpec.makeMeasureSpec(room, MeasureSpec.AT_MOST))
        setMeasuredDimension(w, h)
    }

    override fun onLayout(changed: Boolean, l: Int, t: Int, r: Int, b: Int) {
        val card = getChildAt(0) ?: return
        val h = b - t
        val ch = card.measuredHeight
        val minTop = barTop + side
        val maxTop = maxOf(minTop, h - barBottom - side - ch)
        val top = (minTop + maxTop) / 2 // 남는 자리의 정가운데 (카드가 꽉 차면 minTop)
        card.layout(side, top, side + card.measuredWidth, top + ch)
    }

    companion object {
        fun dimen(ctx: Context, name: String): Int {
            val id = ctx.resources.getIdentifier(name, "dimen", "android")
            return if (id > 0) ctx.resources.getDimensionPixelSize(id) else 0
        }
    }
}

/** 경고창 카드: 주어진 높이보다 길면 글 칸(scroll)만 그만큼 줄인다 */
private class FitCard(ctx: Context) : LinearLayout(ctx) {
    var scroll: ScrollView? = null

    override fun onMeasure(widthSpec: Int, heightSpec: Int) {
        val s = scroll
        s?.layoutParams?.height = LayoutParams.WRAP_CONTENT
        // 먼저 제한 없이 재서 원래 높이를 안다 (AT_MOST 로 재면 이미 잘린 높이가 나온다)
        super.onMeasure(widthSpec, MeasureSpec.makeMeasureSpec(0, MeasureSpec.UNSPECIFIED))
        val natural = measuredHeight
        val limit = MeasureSpec.getSize(heightSpec)
        if (s != null && MeasureSpec.getMode(heightSpec) != MeasureSpec.UNSPECIFIED && natural > limit) {
            s.layoutParams.height = (s.measuredHeight - (natural - limit)).coerceAtLeast(0)
        }
        super.onMeasure(widthSpec, heightSpec)
    }
}
