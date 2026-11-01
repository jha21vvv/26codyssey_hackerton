// 앱 설치 감지 시험용 가짜 앱. 아무 기능 없이 글자 한 줄만 보여 준다.
// 이름에 '검찰'이 들어 있어 부모님 폰에 깔면 '기관 사칭 의심 앱' 경고가 떠야 한다.
plugins {
    id("com.android.application")
}

android {
    namespace = "kr.codyssey.testscamapp"
    compileSdk = 36

    defaultConfig {
        applicationId = "kr.codyssey.testscamapp"
        minSdk = 26
        targetSdk = 36
        versionCode = 1
        versionName = "0.1"
    }
}
