package kr.codyssey.jikimi

import org.junit.Assert.assertEquals
import org.junit.Test

/** 초대 코드 골라내기: 코드만 / 공유 메시지 통째로 / 예전 링크 어느 것을 붙여 넣어도 같은 코드 */
class InviteTokenTest {
    private val code = "724N1RCaMrG0uQwbbh4WFa8W6Jv81Ewo3dkpgODhQn0" // BE secrets.token_urlsafe(32) 모양 (43자)

    @Test fun codeOnly() = assertEquals(code, Api.inviteToken("  $code \n"))

    @Test fun shareMessage() = assertEquals(code,
        Api.inviteToken("부모님 지킴이 가족 초대 코드예요.\n$code\n앱에서 로그인한 뒤 '초대 코드' 칸에 붙여 넣어 주세요."))

    @Test fun oldLink() = assertEquals(code,
        Api.inviteToken("http://long-temporary-tunnel-name-here.example.com/api/v1/invitations/$code"))

    @Test fun shortDemoLink() = assertEquals("test-token", Api.inviteToken("https://jikimi.test/invite/test-token"))
}
