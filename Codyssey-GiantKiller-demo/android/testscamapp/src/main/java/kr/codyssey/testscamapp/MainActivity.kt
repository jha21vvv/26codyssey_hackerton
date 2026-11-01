package kr.codyssey.testscamapp

import android.app.Activity
import android.os.Bundle
import android.view.Gravity
import android.widget.TextView

/** 부모님 지킴이의 '앱 설치 감지'를 시험하려고 만든 빈 앱 */
class MainActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(TextView(this).apply {
            text = "부모님 지킴이 시험용 앱입니다.\n아무 기능이 없어요."
            textSize = 22f
            gravity = Gravity.CENTER
            setPadding(48, 48, 48, 48)
        })
    }
}
