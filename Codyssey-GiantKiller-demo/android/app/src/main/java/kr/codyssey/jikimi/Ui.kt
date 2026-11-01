package kr.codyssey.jikimi

import android.app.Activity
import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.ColorFilter
import android.graphics.Paint
import android.graphics.Path
import android.graphics.PixelFormat
import android.graphics.RectF
import android.graphics.Typeface
import android.graphics.drawable.Drawable
import android.graphics.drawable.GradientDrawable
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView

/**
 * XML 없이 코드로 그리는 화면 부품. 어르신도 쓰는 화면이라 글자·버튼을 크게.
 * [yellow] 참고 시안 "머꼬 핵심 화면 컨셉": 노랑 윗띠(머꼬 로고·제목) + 흰 바탕, 주요 버튼은 검정, 긴급은 연분홍 칸 + 빨강 글씨,
 * 정보 칸은 따뜻한 회색, 글꼴 Pretendard (로고는 고양이 그림). 부모님 경고창·안내 카드는 팀원 A안 그대로.
 * 부모님 위험 경고창만 팀원 A안(빨강·흰 사선 줄무늬 + "멈추세요") — 아래 Stage·StripedBorderDrawable.
 */
object Ui {
    val YELLOW = Color.parseColor("#FFD400")      // 윗띠 (머꼬)
    val BRAND = Color.parseColor("#1C1C1E")       // 주요 버튼: 검정
    val BRAND_SOFT = Color.parseColor("#F3F2EE")  // 보조 버튼 바탕
    val INK = Color.parseColor("#1C1C1E")
    val MUTED = Color.parseColor("#6E6E73")
    val BG = Color.WHITE                           // 바탕: 흰색
    val SURFACE = Color.WHITE
    val FILL = Color.parseColor("#F5F4F0")        // 정보 칸: 따뜻한 회색
    val LINE = Color.parseColor("#E8E8E8")
    val DANGER = Color.parseColor("#D92D20")      // 긴급 글씨 (빨강)
    val DANGER_SOFT = Color.parseColor("#FFF2F1") // 긴급 칸 (연분홍)
    val WARN = Color.parseColor("#B45309")
    val WARN_SOFT = Color.parseColor("#FDF1DF")
    val INFO = BRAND
    val INFO_SOFT = Color.parseColor("#EAF2FE")

    fun Activity.dp(v: Int) = (v * resources.displayMetrics.density).toInt()

    // ── 글꼴 (res/font): 본문·강조 Pretendard (로고는 고양이 그림 drawable/ic_logo_cat) ──
    private var fonts: Map<Int, Typeface> = emptyMap()
    private fun font(ctx: Context, id: Int): Typeface = fonts[id] ?: runCatching { ctx.resources.getFont(id) }
        .getOrDefault(Typeface.DEFAULT).also { fonts = fonts + (id to it) }
    fun bold(ctx: Context) = font(ctx, R.font.pretendard_extrabold)
    fun regular(ctx: Context) = font(ctx, R.font.pretendard_regular)

    /** 한국어 줄바꿈을 낱말 단위로 ("안내예/요" 대신 "안내예요" 통째로). 안드로이드 13 이상에서만 된다 */
    fun phrase(tv: TextView): TextView {
        if (android.os.Build.VERSION.SDK_INT >= 33) tv.lineBreakWordStyle = android.graphics.text.LineBreakConfig.LINE_BREAK_WORD_STYLE_PHRASE
        return tv
    }

    /** 한국어는 위 PHRASE 가 듣지 않아("부/인했어요") 한글 글자 사이에 줄바꿈 금지(U+2060)를 넣어 띄어쓰기에서만 줄을 바꾼다.
     *  경고창·안내 카드의 제목·본문에만 쓴다 (링크·영문은 그대로) */
    fun keep(s: String): String = buildString {
        s.forEachIndexed { i, c ->
            if (i > 0 && c in '\uAC00'..'\uD7A3' && s[i - 1] in '\uAC00'..'\uD7A3') append('\u2060')
            append(c)
        }
    }
    private fun Context.px(v: Float) = v * resources.displayMetrics.density
    private fun View.px(v: Int) = (v * resources.displayMetrics.density).toInt()

    /** 화면 전체: 스크롤 + 세로 줄. 설정 화면은 흰 바탕, 목록은 연회색 */
    fun Activity.page(bg: Int = SURFACE, build: LinearLayout.() -> Unit): LinearLayout {
        val col = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(20), dp(28), dp(20), dp(32))
            build()
        }
        setContentView(ScrollView(this).apply {
            setBackgroundColor(bg)
            addView(col, ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))
        })
        return col
    }

    fun LinearLayout.text(s: String, size: Float = 18f, color: Int = INK, bold: Boolean = false,
                          center: Boolean = false, top: Int = 8): TextView =
        TextView(context).apply {
            text = s
            textSize = size
            setTextColor(color)
            setLineSpacing(0f, 1.3f)
            typeface = if (bold) bold(context) else regular(context)
            if (center) gravity = Gravity.CENTER_HORIZONTAL
            setPadding(0, px(top), 0, 0)
            phrase(this)
        }.also { addView(it) }

    /** 큰 제목 (시안 28~30sp) */
    fun LinearLayout.heading(s: String, color: Int = INK, top: Int = 20): TextView = text(s, 25f, color, bold = true, top = top)
        .apply { setLineSpacing(0f, 1.15f) }

    /** 제목 위 작은 색 글자 ("사기 의심 문자", "긴급 · 지금 확인") */
    fun LinearLayout.kicker(s: String, color: Int = DANGER, top: Int = 16): TextView = text(s, 15f, color, bold = true, top = top)

    /**
     * 버튼. primary: 파랑 면 / 보조: 연회색 면 / outline: 흰 면 + 테두리 / danger: 빨강 면 (긴급 전화).
     * 높이 56dp 이상, 모서리 12dp.
     */
    fun LinearLayout.button(s: String, primary: Boolean = true, danger: Boolean = false, outline: Boolean = false,
                            onClick: () -> Unit): Button =
        Button(context).apply {
            text = s
            textSize = 18f
            isAllCaps = false
            typeface = bold(context)
            stateListAnimator = null
            minHeight = px(56)
            minimumHeight = minHeight
            val fill = when { danger -> DANGER; outline -> SURFACE; primary -> BRAND; else -> BRAND_SOFT }
            setTextColor(if (danger || (primary && !outline)) Color.WHITE else INK)
            background = GradientDrawable().apply {
                cornerRadius = px(10).toFloat()
                setColor(fill)
                if (outline) setStroke(px(1).coerceAtLeast(2), Color.parseColor("#C7C7CC"))
            }
            setPadding(px(16), px(14), px(16), px(14))
            setOnClickListener { onClick() }
        }.also {
            addView(it, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
                .apply { topMargin = px(12) })
        }

    /** 글자만 있는 작은 링크 버튼 ("사건 자세히 보기 ›") */
    fun LinearLayout.link(s: String, color: Int = MUTED, onClick: () -> Unit): TextView =
        text(s, 15f, color, bold = true, center = true, top = 14).apply {
            setPadding(0, px(14), 0, px(6))
            setOnClickListener { onClick() }
        }

    fun LinearLayout.input(hint: String, value: String = "", number: Boolean = false): EditText =
        EditText(context).apply {
            this.hint = hint
            setText(value)
            textSize = 19f
            setTextColor(INK)
            setHintTextColor(Color.parseColor("#9AA3AE"))
            minHeight = px(56)
            background = GradientDrawable().apply {
                cornerRadius = px(10).toFloat()
                setColor(FILL)
            }
            setPadding(px(16), px(14), px(16), px(14))
            if (number) inputType = InputType.TYPE_CLASS_PHONE
        }.also {
            addView(it, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
                .apply { topMargin = px(12) })
        }

    fun LinearLayout.gap(h: Int = 16) = addView(View(context), LinearLayout.LayoutParams(1, px(h)))

    /** 가는 구분선 */
    fun LinearLayout.divider(inset: Int = 0) = addView(View(context).apply { setBackgroundColor(LINE) },
        LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, px(1).coerceAtLeast(1)).apply { leftMargin = px(inset); rightMargin = px(inset) })

    /** 카드 (둥근 모서리). 흰 바탕 위라 옅은 테두리. line: 테두리 색 */
    fun LinearLayout.card(line: Int = LINE, fill: Int = SURFACE, pad: Int = 16, onClick: (() -> Unit)? = null,
                          build: LinearLayout.() -> Unit): LinearLayout =
        LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(px(pad), px(pad - 6).coerceAtLeast(0), px(pad), px(pad))
            background = GradientDrawable().apply {
                cornerRadius = px(10).toFloat()
                setColor(fill)
                if (line != fill) setStroke(px(if (line == DANGER) 2 else 1).coerceAtLeast(1), line)
            }
            onClick?.let { f -> setOnClickListener { f() } }
            build()
        }.also {
            addView(it, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
                .apply { topMargin = px(12) })
        }

    /** 상세 화면의 회색 정보 칸: (이름, 값) 줄들을 구분선으로 나눠 보여 준다 */
    fun LinearLayout.infoBox(rows: List<Pair<String, String>>, onClick: (() -> Unit)? = null): LinearLayout =
        card(fill = FILL, line = FILL, pad = 16, onClick = onClick) {
            rows.forEachIndexed { i, (k, v) ->
                if (i > 0) divider()
                addView(LinearLayout(context).apply {
                    orientation = LinearLayout.HORIZONTAL
                    gravity = Gravity.CENTER_VERTICAL
                    setPadding(0, px(12), 0, px(12))
                    addView(TextView(context).apply { text = k; textSize = 16f; setTextColor(MUTED); typeface = regular(context) },
                        LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
                    addView(TextView(context).apply {
                        text = v; textSize = 17f; setTextColor(INK); typeface = bold(context); gravity = Gravity.END
                    }, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1.4f))
                })
            }
        }

    /** 목록 한 줄: 제목 / 작은 설명 / 오른쪽 상태 글자 / › (누르면 상세) */
    fun LinearLayout.listRow(title: String, sub: String, right: String = "", rightColor: Int = INK,
                             onClick: () -> Unit): LinearLayout =
        LinearLayout(context).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(0, px(14), 0, px(14))
            setOnClickListener { onClick() }
            addView(LinearLayout(context).apply {
                orientation = LinearLayout.VERTICAL
                addView(TextView(context).apply { text = title; textSize = 18f; setTextColor(INK); typeface = bold(context) })
                if (sub.isNotEmpty()) addView(TextView(context).apply {
                    text = sub; textSize = 15f; setTextColor(MUTED); typeface = regular(context); setPadding(0, px(4), 0, 0)
                })
            }, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
            if (right.isNotEmpty()) addView(TextView(context).apply {
                text = right; textSize = 15f; setTextColor(rightColor); typeface = bold(context)
                setPadding(px(8), 0, px(4), 0)
            })
            addView(ImageView(context).apply {
                setImageResource(R.drawable.ic_chevron)
                setColorFilter(Color.parseColor("#9AA3AE"))
            }, LinearLayout.LayoutParams(px(22), px(22)))
        }.also { addView(it) }

    /** 가로 줄. 안에 넣은 것들이 같은 너비로 나눠 갖는다 (버튼 두 개 나란히 등) */
    fun LinearLayout.split(build: LinearLayout.() -> Unit): LinearLayout =
        LinearLayout(context).apply {
            orientation = LinearLayout.HORIZONTAL
            build()
            for (i in 0 until childCount) getChildAt(i).layoutParams =
                LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply {
                    topMargin = px(12)
                    if (i > 0) leftMargin = px(8)
                }
        }.also { addView(it) }

    /** 작은 둥근 꼬리표 여러 개 한 줄. (글자, 글자색, 바탕색) */
    fun LinearLayout.chips(vararg items: Triple<String, Int, Int>, after: String = ""): LinearLayout =
        LinearLayout(context).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(0, px(8), 0, 0)
            for ((s, fg, bg) in items.filter { it.first.isNotEmpty() }) addView(TextView(context).apply {
                text = s
                textSize = 14f
                setTextColor(fg)
                typeface = bold(context)
                setPadding(px(10), px(4), px(10), px(4))
                background = GradientDrawable().apply { cornerRadius = px(8).toFloat(); setColor(bg) }
            }, LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT)
                .apply { rightMargin = px(6) })
            if (after.isNotEmpty()) addView(TextView(context).apply { text = after; textSize = 15f; setTextColor(MUTED) })
        }.also { addView(it) }

    /** 노랑 윗띠: ‹ 뒤로 + 가운데 제목 (참고 시안). 부모 칸의 여백을 넘어 화면 끝까지 칠한다 */
    fun LinearLayout.topBar(title: String, onBack: (() -> Unit)?): LinearLayout =
        LinearLayout(context).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setBackgroundColor(YELLOW)
            setPadding(px(8), px(8), px(12), px(8))
            addView(TextView(context).apply {
                text = if (onBack != null) "‹" else ""
                textSize = 30f
                setTextColor(INK)
                setPadding(0, 0, px(12), 0)
                onBack?.let { b -> setOnClickListener { b() } }
            }, LinearLayout.LayoutParams(px(44), ViewGroup.LayoutParams.WRAP_CONTENT))
            addView(TextView(context).apply {
                text = title; textSize = 18f; setTextColor(INK); typeface = bold(context); gravity = Gravity.CENTER
            }, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
            addView(View(context), LinearLayout.LayoutParams(px(44), 1))
        }.also {
            clipToPadding = false // 부모 여백 밖까지 칠하려면 (안 하면 띠가 여백 안쪽만 보이고 ‹ 가 잘린다)
            addView(it, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply {
                leftMargin = -paddingLeft; rightMargin = -paddingRight; topMargin = -paddingTop; bottomMargin = px(8)
            })
        }

    // ── 부모님 위험 경고창: 팀원 A안 (안전 사인: ISO 3864 안전색 + 45° 사선 줄무늬) ──
    val SIGN_SAFE = Color.parseColor("#00613F")
    val SIGN_CAUTION = Color.parseColor("#FFD200")
    val SIGN_CAUTION_DARK = Color.parseColor("#2A2A2A")
    val SIGN_DANGER = Color.parseColor("#E63312")
    val SIGN_DANGER_TEXT = Color.parseColor("#A3150E")
    val SIGN_TEXT = Color.parseColor("#111111")
    val SIGN_TEXT_SUB = Color.parseColor("#3A3A3A")
    const val SIGN_RADIUS_DP = 3f

    // A안 코드(Overlay.kt 경고창·안내 카드)가 그대로 쓰는 이름
    val SAFE = SIGN_SAFE
    val DANGER_RED = SIGN_DANGER
    val TEXT = SIGN_TEXT
    val TEXT_SUB = SIGN_TEXT_SUB
    val PANEL = Color.WHITE
    const val RADIUS_DP = SIGN_RADIUS_DP

    /** 줄무늬 테두리 틀 (Overlay 처럼 Activity 밖에서도 쓰려고 Context 로 받는다) — A안 */
    fun stripedFrame(ctx: Context, stage: Stage): LinearLayout = LinearLayout(ctx).apply {
        orientation = LinearLayout.VERTICAL
        background = StripedBorderDrawable(ctx, stage)
        val b = ctx.px(stage.borderDp).toInt()
        setPadding(b, b, b, b)
    }

    /** 단계: 줄무늬 색 쌍 + 줄 간격(dp)이 단계마다 다르다 */
    enum class Stage(val a: Int, val b: Int, val bandA: Float, val bandB: Float, val borderDp: Float) {
        SAFE(SIGN_SAFE, Color.WHITE, 6f, 2f, 8f),
        CAUTION(SIGN_CAUTION_DARK, SIGN_CAUTION, 5f, 5f, 8f),
        DANGER(SIGN_DANGER, Color.WHITE, 10f, 10f, 14f),
    }

    /** 단계 헤더: 아이콘 + 굵은 이름 (색 + 모양 + 글자, 색만으로 구분하지 않는다) */
    fun stageHeader(ctx: Context, stage: Stage, label: String): LinearLayout = LinearLayout(ctx).apply {
        orientation = LinearLayout.HORIZONTAL
        gravity = Gravity.CENTER_VERTICAL
        setPadding(0, ctx.px(6f).toInt(), 0, ctx.px(4f).toInt())
        val icon = when (stage) {
            Stage.SAFE -> R.drawable.ic_shield_safe
            Stage.CAUTION -> R.drawable.ic_warning
            Stage.DANGER -> R.drawable.ic_danger
        }
        val s = ctx.px(28f).toInt()
        addView(ImageView(ctx).apply { setImageResource(icon) }, LinearLayout.LayoutParams(s, s))
        addView(TextView(ctx).apply {
            text = label
            textSize = 18f
            typeface = Typeface.DEFAULT_BOLD
            setTextColor(when (stage) { Stage.SAFE -> SIGN_SAFE; Stage.CAUTION -> SIGN_TEXT; Stage.DANGER -> SIGN_DANGER_TEXT })
            setPadding(ctx.px(8f).toInt(), 0, 0, 0)
        })
    }

    /** 45° 사선 줄무늬로 채운 둥근 사각형. 위에 흰 내용 카드를 얹으면 줄무늬 테두리가 된다 (팀원 A안) */
    class StripedBorderDrawable(ctx: Context, private val stage: Stage) : Drawable() {
        private val d = ctx.resources.displayMetrics.density
        private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
        private val clip = Path()
        private val rect = RectF()

        override fun draw(canvas: Canvas) {
            val b = bounds
            rect.set(b.left.toFloat(), b.top.toFloat(), b.right.toFloat(), b.bottom.toFloat())
            clip.reset()
            clip.addRoundRect(rect, SIGN_RADIUS_DP * d, SIGN_RADIUS_DP * d, Path.Direction.CW)
            canvas.save()
            canvas.clipPath(clip)
            canvas.drawColor(stage.b)
            paint.color = stage.a
            val wa = stage.bandA * d
            val period = (stage.bandA + stage.bandB) * d
            val h = rect.height()
            // 왼쪽 아래 → 오른쪽 위 45° 띠 (평행사변형)
            var x = rect.left - h
            val band = Path()
            while (x < rect.right + h) {
                band.reset()
                band.moveTo(x, rect.bottom)
                band.lineTo(x + wa * 1.4142f, rect.bottom)
                band.lineTo(x + wa * 1.4142f + h, rect.top)
                band.lineTo(x + h, rect.top)
                band.close()
                canvas.drawPath(band, paint)
                x += period * 1.4142f
            }
            canvas.restore()
        }

        override fun setAlpha(alpha: Int) { paint.alpha = alpha }
        override fun setColorFilter(colorFilter: ColorFilter?) { paint.colorFilter = colorFilter }
        @Deprecated("Deprecated in Java")
        override fun getOpacity(): Int = PixelFormat.TRANSLUCENT
    }
}
