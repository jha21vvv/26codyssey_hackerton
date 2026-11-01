// AGP 9 는 Kotlin 지원이 내장돼 있어 kotlin 플러그인을 따로 넣지 않는다.
// 서버 호출은 안드로이드 기본 API (HttpURLConnection, org.json). 외부 라이브러리는 푸시(FCM)만.
import groovy.json.JsonSlurper

plugins {
    id("com.android.application")
}

// 앱 ID·이름: 빌드 설정값 (시연용으로 여러 판을 한 폰에 같이 깔 때 -Pjikimi.appId=... -Pjikimi.appName=...)
val appId = (project.findProperty("jikimi.appId") as String?) ?: "kr.codyssey.jikimi"
val appName = (project.findProperty("jikimi.appName") as String?) ?: "부모님 지킴이"

// Firebase 설정: android/app/google-services.json 이 있고 그 안에 지금 앱 ID 가 등록돼 있으면 그 값을 리소스로 넣어 FCM 이 켜진다.
// (google-services 플러그인 대신 같은 일을 여기서 한다. 파일이 없거나 이 앱 ID 가 없으면 푸시 없이 빌드·동작)
// ⚠️ 이 파일은 깃에 올리지 않는다 (.gitignore). Firebase 콘솔에서 받아 복사만 한다
val firebase: Map<String, String> = file("google-services.json").takeIf { it.exists() }?.let { f ->
    @Suppress("UNCHECKED_CAST")
    val json = JsonSlurper().parse(f) as Map<String, Any?>
    val project = json["project_info"] as Map<String, Any?>
    val client = (json["client"] as List<Map<String, Any?>>).firstOrNull {
        ((it["client_info"] as Map<String, Any?>)["android_client_info"] as Map<String, Any?>)["package_name"] == appId
    } ?: return@let null.also { logger.warn("google-services.json 에 $appId 가 없어 푸시 없이 빌드해요") }
    mapOf(
        "google_app_id" to (client["client_info"] as Map<String, Any?>)["mobilesdk_app_id"].toString(),
        "gcm_defaultSenderId" to project["project_number"].toString(),
        "project_id" to project["project_id"].toString(),
        "google_api_key" to ((client["api_key"] as List<Map<String, Any?>>).first()["current_key"]).toString(),
    )
} ?: emptyMap()

android {
    namespace = "kr.codyssey.jikimi"
    compileSdk = 36
    buildFeatures { resValues = true } // 서버 주소·Firebase 설정을 리소스로 넣는다

    defaultConfig {
        applicationId = appId
        minSdk = 26 // "다른 앱 위에 표시"(TYPE_APPLICATION_OVERLAY) 가 26부터
        targetSdk = 36
        versionCode = 1
        versionName = "0.1"
        for ((k, v) in firebase) resValue("string", k, v)
        // BE 서버 주소: android/gradle.properties 의 jikimi.serverUrl (또는 ./gradlew -Pjikimi.serverUrl=...)
        // 기본 http://10.0.2.2:8000 = 에뮬레이터에서 본 이 컴퓨터의 localhost:8000
        val serverUrl = (project.findProperty("jikimi.serverUrl") as String?) ?: "http://10.0.2.2:8000"
        resValue("string", "server_url", serverUrl)
        resValue("string", "app_name", appName)
        resValue("string", "listener_label", "$appName 알림 확인")
    }
}

dependencies {
    // FCM 푸시: BE 가 FID 로 보낸다 (FirebaseMessagingService.onRegistered)
    implementation("com.google.firebase:firebase-messaging:26.0.1")
    // LightModel(가벼운 1차 모델)이 파이썬과 같은 점수를 내는지 확인하는 JVM 단위 테스트
    testImplementation("junit:junit:4.13.2")
}
