package kr.codyssey.jikimi

import android.app.Activity
import android.app.AlertDialog
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Intent
import android.widget.Toast
import kr.codyssey.jikimi.Ui.button
import kr.codyssey.jikimi.Ui.gap
import kr.codyssey.jikimi.Ui.heading
import kr.codyssey.jikimi.Ui.infoBox
import kr.codyssey.jikimi.Ui.input
import kr.codyssey.jikimi.Ui.page
import kr.codyssey.jikimi.Ui.text
import kr.codyssey.jikimi.Ui.topBar

/**
 * 가족 연결 (BE: 대표 자녀가 가족을 만들고 초대로 부모·다른 자녀를 부른다. 초대는 24시간·1회).
 * 화면에서는 링크 전체 대신 "초대 코드"(BE 초대 토큰, invite_url 끝부분)만 보여 주고 주고받는다.
 *  - 초대 받기: 초대 코드 붙여 넣기 → 미리보기 → 참여
 *  - 초대 보내기: 대표만. 초대 코드를 만들어 복사·공유, 잘못 보냈으면 그 자리에서 취소
 *    (BE 에 보낸 초대 목록 API 가 없어서, 만들 때 받은 초대 id 로 이 화면에서만 취소한다)
 */
object Join {
    /** 초대 코드 붙여 넣기 → 미리보기 → 수락. 끝나면 Prefs.family 저장 후 done() */
    fun receive(act: Activity, role: String, onBack: () -> Unit, done: () -> Unit) {
        act.page {
            topBar("가족 연결", onBack)
            heading("받은 초대 코드를\n붙여 넣어 주세요")
            text((if (role == "PARENT") "자녀가 보낸 초대 코드예요." else "가족을 만든 형제·자매가 보낸 초대 코드예요.") +
                 " 받은 메시지를 통째로 붙여 넣어도 돼요.", 17f, Ui.MUTED)
            val link = input("초대 코드")
            gap(16)
            button("다음") {
                val token = Api.inviteToken(link.text.toString())
                if (token.isEmpty()) return@button
                Api.io.execute {
                    try {
                        val p = Api.previewInvite(act, token)
                        act.runOnUiThread { confirm(act, token, p.getString("family_id"), p.optString("representative_name"), p.optString("role"), onBack, done) }
                    } catch (e: Exception) {
                        act.runOnUiThread { Toast.makeText(act, message(e), Toast.LENGTH_LONG).show() }
                    }
                }
            }
        }
    }

    private fun confirm(act: Activity, token: String, familyId: String, rep: String, role: String, onBack: () -> Unit, done: () -> Unit) {
        act.page {
            topBar("가족 연결") { receive(act, role, onBack, done) }
            heading("${rep}님 가족에\n참여할까요?")
            infoBox(listOf("가족 대표" to "${rep}님", "내 역할" to if (role == "PARENT") "부모님" else "자녀"))
            gap(24)
            button("참여하기") {
                Api.io.execute {
                    try {
                        Api.acceptInvite(act, token)
                        Prefs.set(act, "family" to familyId)
                        act.runOnUiThread { done() }
                    } catch (e: Exception) {
                        act.runOnUiThread { Toast.makeText(act, message(e), Toast.LENGTH_LONG).show() }
                    }
                }
            }
        }
    }

    /** 대표 자녀: 초대 코드 만들기 → 복사·공유 (링크 전체는 보여 주지 않는다) */
    fun send(act: Activity, role: String, onDone: () -> Unit) {
        Api.io.execute {
            try {
                val inv = Api.invite(act, role)
                val code = Api.inviteToken(inv.getString("invite_url"))
                act.runOnUiThread {
                    act.page {
                        topBar("가족 초대", onDone)
                        heading(if (role == "PARENT") "부모님께 이 초대 코드를\n보내 주세요" else "형제·자매에게 이 초대 코드를\n보내 주세요")
                        text("받은 분이 앱에서 로그인한 뒤 '초대 코드' 칸에 붙여 넣으면 가족으로 연결돼요. 24시간 동안 한 번만 쓸 수 있어요.", 17f, Ui.MUTED)
                        infoBox(listOf("초대 코드" to code))
                        button("코드 복사하기") {
                            act.getSystemService(ClipboardManager::class.java).setPrimaryClip(ClipData.newPlainText("초대 코드", code))
                            Toast.makeText(act, "복사했어요", Toast.LENGTH_SHORT).show()
                        }
                        button("문자·카톡으로 보내기", primary = false) {
                            act.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).setType("text/plain")
                                .putExtra(Intent.EXTRA_TEXT, "부모님 지킴이 가족 초대 코드예요.\n$code\n앱에서 로그인한 뒤 '초대 코드' 칸에 붙여 넣어 주세요."), "초대 코드 보내기"))
                        }
                        gap(16)
                        button("다 했어요", primary = false) { onDone() }
                        button("이 초대 취소하기", outline = true) { revoke(act, inv.getString("id"), onDone) }
                    }
                }
            } catch (e: Exception) {
                act.runOnUiThread { Toast.makeText(act, message(e), Toast.LENGTH_LONG).show(); onDone() }
            }
        }
    }

    /** 보낸 초대 취소 → 이 링크로는 더 참여할 수 없다 */
    private fun revoke(act: Activity, invitationId: String, onDone: () -> Unit) {
        AlertDialog.Builder(act).setMessage("이 초대를 취소할까요?\n보낸 링크로는 더 참여할 수 없어요.")
            .setPositiveButton("초대 취소") { _, _ ->
                Api.io.execute {
                    val err = runCatching { Api.revokeInvite(act, invitationId) }.exceptionOrNull()
                    act.runOnUiThread {
                        // BE revoke: 403 대표 아님 · 404 없는 초대 · 409 이미 참여함 · 410 시간 지남 (이미 취소한 건 204)
                        val msg = when ((err as? Api.HttpError)?.code) {
                            null -> if (err == null) "초대를 취소했어요" else message(err as Exception)
                            409 -> "이미 가족이 참여한 초대라 취소할 수 없어요"
                            410 -> "시간이 지나 이미 쓸 수 없는 초대예요"
                            else -> message(err as Exception)
                        }
                        Toast.makeText(act, msg, Toast.LENGTH_LONG).show()
                        if (err == null || (err as? Api.HttpError)?.code in setOf(409, 410)) onDone()
                    }
                }
            }.setNegativeButton("그대로 두기", null).show()
    }

    /** BE 오류 코드 → 쉬운 말 */
    fun message(e: Exception): String = when ((e as? Api.HttpError)?.code) {
        401 -> "로그인이 끝났어요. 다시 로그인해 주세요" // 로그인 화면으로는 Session 이 보낸다
        403 -> "가족 대표만 할 수 있어요"
        404 -> "초대 코드를 찾을 수 없어요"
        409 -> "이미 쓴 초대 코드이거나 이미 참여한 가족이에요"
        410 -> "시간이 지났거나 취소된 초대 코드예요"
        null -> "서버에 연결하지 못했어요: ${e.message}"
        else -> "실패했어요: ${(e as Api.HttpError).detail}"
    }
}
