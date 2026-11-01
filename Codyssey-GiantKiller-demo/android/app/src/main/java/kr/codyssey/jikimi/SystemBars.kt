package kr.codyssey.jikimi

import android.app.Activity
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.ColorFilter
import android.graphics.Paint
import android.graphics.PixelFormat
import android.graphics.drawable.Drawable
import android.os.Build
import android.view.ViewGroup
import android.view.WindowInsets
import android.view.WindowInsetsController

/**
 * 상태바·내비게이션 바와 겹치지 않게.
 * 안드로이드 15+ 는 targetSdk 35 이상 앱을 시스템 바 밑까지 그린다(edge-to-edge 강제) → 윗띠가 상태바·전면 카메라에 붙고,
 * 아래 탭이 내비게이션 바(제스처 줄)와 겹쳤다. 안드로이드 11+ 에서는 모두 똑같이 시스템 바 밑까지 그리게 하고,
 * 화면 내용은 시스템 바 크기만큼 비운 뒤 그 자리를 위(top)·아래(bottom) 색으로 칠한다. 기기마다 다른 바 높이를 그대로 쓴다.
 */
object SystemBars {
    fun apply(act: Activity, top: Int = Ui.SURFACE, bottom: Int = Ui.SURFACE) { // 시계 줄(상태바)은 칠하지 않고 흰색 그대로 (사용자 요청)
        if (Build.VERSION.SDK_INT < 30) return // 10 이하는 원래 시스템 바 밖에만 그린다 (테마 색)
        val w = act.window
        w.decorView // 창 틀을 먼저 만든다 (setContentView 전에 부르므로 — 없으면 insetsController 가 null)
        w.setDecorFitsSystemWindows(false)
        @Suppress("DEPRECATION") run { w.statusBarColor = Color.TRANSPARENT; w.navigationBarColor = Color.TRANSPARENT }
        // 상태바·내비게이션 바 글자·아이콘은 어둡게 (밝은 바탕 위)
        w.insetsController?.setSystemBarsAppearance(
            WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS or WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS,
            WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS or WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS)
        val content = act.findViewById<ViewGroup>(android.R.id.content)
        val paint = BarsDrawable(top, bottom)
        content.background = paint
        content.setOnApplyWindowInsetsListener { v, insets ->
            val i = insets.getInsets(WindowInsets.Type.systemBars() or WindowInsets.Type.displayCutout())
            v.setPadding(i.left, i.top, i.right, i.bottom)
            paint.top = i.top
            paint.bottom = i.bottom
            paint.invalidateSelf()
            insets
        }
        content.requestApplyInsets()
    }

    /** 위 top 픽셀은 위 색, 아래 bottom 픽셀은 아래 색 (시스템 바 뒤) */
    private class BarsDrawable(private val topColor: Int, private val bottomColor: Int) : Drawable() {
        var top = 0
        var bottom = 0
        private val p = Paint()
        override fun draw(canvas: Canvas) {
            val b = bounds
            p.color = topColor
            canvas.drawRect(b.left.toFloat(), b.top.toFloat(), b.right.toFloat(), (b.top + top).toFloat(), p)
            p.color = bottomColor
            canvas.drawRect(b.left.toFloat(), (b.bottom - bottom).toFloat(), b.right.toFloat(), b.bottom.toFloat(), p)
        }
        override fun setAlpha(alpha: Int) {}
        override fun setColorFilter(colorFilter: ColorFilter?) {}
        @Deprecated("Deprecated in Java")
        override fun getOpacity() = PixelFormat.TRANSLUCENT
    }
}
