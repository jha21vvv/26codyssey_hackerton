package kr.codyssey.jikimi

import android.app.Activity
import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.view.Gravity
import android.view.ViewGroup
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import kr.codyssey.jikimi.Ui.button
import kr.codyssey.jikimi.Ui.dp
import kr.codyssey.jikimi.Ui.gap
import kr.codyssey.jikimi.Ui.heading
import kr.codyssey.jikimi.Ui.input
import kr.codyssey.jikimi.Ui.page
import kr.codyssey.jikimi.Ui.text
import kr.codyssey.jikimi.Ui.topBar

/**
 * 앱 첫 화면: (디자인 시안 01) "이 휴대폰은 누가 사용하나요?" → BE 계정 로그인·가입 → 역할 화면.
 * 로그인(JWT)이 있으면 바로 역할 화면으로. 푸시 알림을 눌러 열린 경우 사건 ID 를 자녀 화면으로 넘긴다.
 */
class MainActivity : Activity() {
    override fun onCreate(savedInstanceState: android.os.Bundle?) {
        super.onCreate(savedInstanceState)
        SystemBars.apply(this)
    }

    private var pick = ""  // 처음에는 아무것도 고르지 않은 상태

    override fun onResume() {
        super.onResume()
        Notifier.channels(this)
        when {
            Prefs.role(this).isEmpty() -> chooser()
            Prefs.token(this).isEmpty() -> login()
            else -> go(if (Prefs.role(this) == "parent") ParentActivity::class.java else ChildActivity::class.java)
        }
    }

    private fun go(cls: Class<*>) {
        // 앱이 뒤에 있을 때 온 BE 푸시를 누르면 data(event_id·verification_id)가 여기 extras 로 온다
        val i = Intent(this, cls)
        intent?.extras?.let { ex ->
            ex.getString("event_id")?.let { i.putExtra(ChildActivity.EXTRA_EVENT, it) }
            ex.getString("verification_id")?.let { i.putExtra(ChildActivity.EXTRA_VERIFICATION, it); Prefs.addVerification(this, it) }
        }
        startActivity(i)
        finish()
    }

    // ── BE 계정: 로그인 / 처음이면 가입 ──
    private fun login(signup: Boolean = false) {
        val act = this
        page {
            topBar(if (signup) "가입하기" else "로그인") { if (signup) login() else { Prefs.set(act, "role" to null); chooser() } }
            heading(if (signup) "처음 오셨군요\n계정을 만들어 주세요" else "다시 오셨군요\n로그인해 주세요")
            val name = if (signup) input("이름 (자녀 화면에 보여요)") else null
            val email = input("이메일").apply { inputType = android.text.InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS or android.text.InputType.TYPE_CLASS_TEXT }
            val password = input("비밀번호").apply {
                inputType = android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_VARIATION_PASSWORD
            }
            gap(16)
            button(if (signup) "가입하고 시작하기" else "로그인") {
                val e = email.text.toString().trim()
                val p = password.text.toString()
                val n = name?.text?.toString()?.trim().orEmpty()
                if (e.isEmpty() || p.isEmpty() || (signup && n.isEmpty())) {
                    Toast.makeText(act, "빈칸을 모두 채워 주세요", Toast.LENGTH_SHORT).show()
                    return@button
                }
                Api.io.execute {
                    val err = try {
                        if (signup) Api.register(act, e, p, n)
                        Api.login(act, e, p)
                        Push.start(act)
                        null
                    } catch (x: Api.HttpError) {
                        when (x.detail) {
                            "REGISTER_USER_ALREADY_EXISTS" -> "이미 가입한 이메일이에요. 로그인해 주세요"
                            "LOGIN_BAD_CREDENTIALS" -> "이메일이나 비밀번호가 맞지 않아요"
                            else -> "실패했어요: ${x.detail}"
                        }
                    } catch (x: Exception) {
                        "서버에 연결하지 못했어요: ${x.message}"
                    }
                    runOnUiThread {
                        if (err != null) Toast.makeText(act, err, Toast.LENGTH_LONG).show()
                        else go(if (Prefs.role(act) == "parent") ParentActivity::class.java else ChildActivity::class.java)
                    }
                }
            }
            if (!signup) button("처음이에요 (가입하기)", primary = false) { login(signup = true) }
            if (!signup) {
                gap(24)
                // 시험용: 로그인·서버 없이 예시 데이터로 화면을 둘러본다 (Demo.kt)
                button("테스트로 둘러보기 (로그인 없이)", outline = true) {
                    Demo.start(act)
                    go(if (Prefs.role(act) == "parent") ParentActivity::class.java else ChildActivity::class.java)
                }
            }
        }
    }

    private fun chooser() {
        val act = this
        page {
            topBar("시작하기", null)
            heading("이 휴대폰은\n누가 사용하나요?")
            gap(12)
            for ((role, title, sub) in listOf(
                Triple("parent", "부모님이 사용해요", "위험한 문자와 전화를 알려드려요"),
                Triple("child", "자녀가 사용해요", "부모님께 온 위험 알림을 확인해요"),
            )) radioCard(title, sub, pick == role) { pick = role; chooser() }
            gap(24)
            button("다음") {
                if (pick.isEmpty()) {
                    Toast.makeText(act, "누가 사용하는지 골라 주세요", Toast.LENGTH_SHORT).show()
                    return@button
                }
                Prefs.set(act, "role" to pick)
                login()
            }
        }
    }

    /** 고르는 카드: 고르면 파란 테두리 + 채운 동그라미 */
    private fun LinearLayout.radioCard(title: String, sub: String, on: Boolean, onClick: () -> Unit) {
        addView(LinearLayout(context).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(20), dp(18), dp(20), dp(18))
            background = GradientDrawable().apply {
                cornerRadius = dp(14).toFloat()
                setColor(if (on) Color.parseColor("#FFF8D6") else Color.WHITE)
                setStroke(dp(if (on) 2 else 1), if (on) Ui.INK else Ui.LINE)
            }
            setOnClickListener { onClick() }
            addView(LinearLayout(context).apply {
                orientation = LinearLayout.VERTICAL
                addView(TextView(context).apply { text = title; textSize = 20f; setTextColor(Ui.INK); typeface = Typeface.DEFAULT_BOLD })
                addView(TextView(context).apply { text = sub; textSize = 15f; setTextColor(Ui.MUTED); setPadding(0, dp(4), 0, 0) })
            }, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
            addView(TextView(context).apply {
                background = GradientDrawable().apply {
                    shape = GradientDrawable.OVAL
                    setColor(if (on) Ui.INK else Color.WHITE)
                    setStroke(dp(if (on) 6 else 2), if (on) Ui.YELLOW else Color.parseColor("#C7C7CC"))
                }
            }, LinearLayout.LayoutParams(dp(26), dp(26)))
        }, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { topMargin = dp(12) })
    }
}
