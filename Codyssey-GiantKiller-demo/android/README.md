# 부모님 지킴이 — 안드로이드 앱

> **이 브랜치(be-align)는 백엔드 레포(ted1117/Codyssey-GiantKiller-BE)의 API 에 맞춘 앱이에요.**
> BE 서버의 `/api/v1/...` 를 부른다.
>
> **서버 주소 = 빌드 설정값 `jikimi.serverUrl`** (앱 안에서는 바꾸지 않는다). 배포 주소가 정해지면 이 값만 바꿔 다시 빌드한다.
> - 바꾸는 곳: `android/gradle.properties` 의 `jikimi.serverUrl=http://10.0.2.2:8000`
> - 또는 빌드할 때만: `./gradlew :app:assembleDebug -Pjikimi.serverUrl=https://BE주소`
> - 기본값 `http://10.0.2.2:8000` = 에뮬레이터에서 본 이 컴퓨터의 `localhost:8000`. 실기기를 USB 로 이을 땐 `adb reverse tcp:8000 tcp:8000` 후 `http://127.0.0.1:8000` 으로 빌드
> - 앱 코드에서는 리소스 `R.string.server_url` (`Prefs.server()`)
>
> | 앱이 하는 일 | BE API |
> |---|---|
> | 가입·로그인 (JWT, 만료되면 다시 로그인) | `POST /api/v1/auth/register`, `POST /api/v1/auth/login`, `GET /api/v1/users/me` |
> | 자녀: 가족 만들기(대표) → 부모님·형제 초대 코드 | `POST /api/v1/families`, `POST /api/v1/families/{id}/invitations` |
> | 자녀(대표): 보낸 초대 취소 (초대 코드 화면에서) | `DELETE /api/v1/families/{id}/invitations/{invitation_id}` |
> | 부모님·다른 자녀: 초대 코드로 참여 | `GET /api/v1/invitations/{token}`, `POST /api/v1/invitations/{token}/accept` |
> | 부모님 폰: 문자(1차 필터 통과·가린 내용) | `POST /api/v1/alerts/check` → 사칭이면 확인 중 카드 + `GET /api/v1/verify/{id}` 로 결과 확인, 주의 필요면 경고창 |
> | 부모님 폰: 통화 녹음 | `POST /api/v1/calls/analyze` → 주의 필요면 경고창 |
> | 부모님 폰: 앱 설치 | `POST /api/v1/actions/app-install` (스토어 밖 설치 여부 포함) → 위험이면 경고창 |
> | 자녀 폰: 푸시 | FCM FID → `PUT/DELETE /api/v1/users/me/push-registrations`. 가족 확인 요청엔 알림 버튼 → `POST /api/v1/verify/respond` |
> | 자녀 폰: 사건 목록·상세·확인했어요/해결됐어요 | `GET /api/v1/events`, `GET /api/v1/events/{id}`, `PATCH /api/v1/events/{id}/status` |
>
> **[yellow 브랜치] 디자인**: 참고 시안 "머꼬 핵심 화면 컨셉" — 노랑 윗띠(머꼬 로고·화면 제목)·노랑 상태바, 흰 바탕, 검정 주요 버튼,
> 긴급은 연분홍 칸 + 빨강 글씨, 알림은 구분선 목록(제목·설명·상태·시간), 정보 칸은 따뜻한 회색. 글꼴 Pretendard, 로고·앱 아이콘은 고양이 그림(`ic_logo_cat`, 적응형 `mipmap-anydpi/ic_launcher.xml`).
> 시안의 "어머니께 전화하기"·보낸 번호는 BE 에 전화번호가 없어 뺌(긴급 칸 버튼은 "사건 자세히 보기"). 부모님 경고창·안내 카드는 팀원 A안 그대로.
> 앱 ID·이름도 빌드 설정값: `-Pjikimi.appId=… -Pjikimi.appName=…` (기본 kr.codyssey.jikimi · 부모님 지킴이)
>
> **푸시(Firebase)**: Firebase 프로젝트는 **BE 담당이 만든다** (푸시 발송·서버 키 파일이 BE 쪽, PRD-004).
> 그 프로젝트에 안드로이드 앱(패키지 `kr.codyssey.jikimi`)을 등록해 받은 `google-services.json` 을 `android/app/` 에 넣고 빌드하면 켜진다.
> 없으면 푸시 없이 빌드·동작하고, 자녀 폰은 새 알림·가족 확인 요청을 받지 못한다 (앱을 열면 사건 기록은 보임).
>
> BE 에 없어서 뺀 것: 자녀·부모님께 전화하기, 사기 번호로 다시 온 전화 경고, 진짜 자녀 번호 구분, 연결 코드 6자리, 서버 폴링.


서버 호출은 안드로이드 기본 API(HttpURLConnection, org.json)만 쓰고, 외부 라이브러리는 푸시(FCM)뿐이다.

| 파일 | 하는 일 |
|---|---|
| `MainActivity.kt` | 첫 화면: 부모님 폰 / 자녀 폰 고르기 → BE 로그인·가입 (+ 테스트로 둘러보기) |
| `ParentActivity.kt` | 부모님 폰: 자녀가 보낸 초대 코드로 가족 참여 → 보호 설정(권한 4개) → 지킴이 켜짐. 시험 문자 버튼 |
| `ChildActivity.kt` | 자녀 폰: 가족 만들기(대표)·초대 코드로 참여 → 알림 · 오늘 · 기록 · 사건 상세 · 가족 확인 |
| `Join.kt` | 초대 코드 보내기(대표만, `POST /families/{id}/invitations`) · 그 자리에서 취소(`DELETE …/invitations/{id}`, BE 에 보낸 초대 목록이 없어서) · 받기(`GET/POST /invitations/{token}…`) 화면 |
| `Api.kt` | BE API 호출(JWT Bearer), 로그인·가족 ID 저장. 서버 주소는 빌드 설정값 `jikimi.serverUrl` |
| `SmsReceiver.kt` | **문자 직접 받기** (진짜 번호·전체 내용, 잠금화면 '내용 숨김'이어도) |
| `NotiListener.kt` | **알림 읽기** (알림 접근 권한). 카톡·RCS 채팅 등 문자 직접 받기로 안 오는 메시지 |
| `Inbox.kt` | 두 길로 온 같은 문자를 한 번만 처리 → 폰 안 1차 필터 → 걸린 것만 가려서 `POST /api/v1/alerts/check`. 응답을 보고 경고창·안내 카드 (`Reactions`) |
| `Guard.kt` | 폰 안 1차 필터(`prefilter`)·가리기(`mask`). 파이썬 `ai/prefilter.py` 와 같은 규칙. 아는 번호는 연락처로 확인 |
| `LightModel.kt` | **가벼운 1차 모델** (assets/light_model.bin, 64KB). 파이썬 `ai/light_model.py` 와 같은 점수 — `./gradlew :app:testDebugUnitTest`. 1차 필터: 위험 단어 OR 링크 OR 점수 ≥ 0.3 |
| `GuardService.kt` | 부모님 폰에서 뒤에서 도는 서비스: **앱 설치 감지** → `POST /api/v1/actions/app-install`, **통화 녹음 감지** → `POST /api/v1/calls/analyze` |
| `Push.kt` | FCM 푸시: FID 등록(`PUT/DELETE /users/me/push-registrations`), 자녀 폰 알림(가족 확인 요청엔 "내가 보냈어요/안 보냈어요" → `POST /verify/respond`), 재부팅 시 다시 시작 |
| `Overlay.kt` | `Overlay`(화면 덮는 경고창)·`InfoCard`(위쪽 안내 카드)는 팀원 A안 코드 그대로 (위치만 헤드업 알림 아래로), `Notifier`(알림 채널) |
| `Ui.kt` | 화면 부품 (제목·버튼·카드·정보 칸·목록 줄·위 막대). 경고창용 줄무늬 부품은 팀원 A안 |
| `SystemBars.kt` | 상태바·내비게이션 바와 겹치지 않게 (안드로이드 15+ edge-to-edge) |
| `Demo.kt` | "테스트로 둘러보기": 로그인·서버 없이 BE 응답 모양의 예시 데이터 |
| `testscamapp/` | 앱 설치 감지 시험용 빈 앱 **"시험용 검찰사칭앱"** (`./gradlew :testscamapp:assembleDebug`) |

## 빌드·실행

Android Studio 에서 `android/` 폴더를 연다 (AGP 9.0.1, Gradle 9.2.1, minSdk 26, compileSdk 36).
Gradle 동기화가 안 되면 Android Studio 가 권하는 버전으로 올리면 된다.

터미널:

```bash
cd android
./gradlew :app:assembleDebug          # app/build/outputs/apk/debug/app-debug.apk
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

## 처음 설정 — 앱 하나로 두 역할 (BE 흐름)

처음 열면 **"이 휴대폰은 누가 사용하나요?"** → BE 계정 로그인·가입 (JWT, 만료되면 다시 로그인)

**자녀 폰** (`ChildActivity`)
1. "가족 만들기(내가 대표)" → 부모님 초대 코드 만들기·복사·공유 (24시간·1회) / 또는 "받은 초대 코드로 참여"
2. 가족 확인 요청은 BE 푸시(VERIFY_REQUEST) 알림의 **"내가 보냈어요 / 안 보냈어요"** 버튼으로 답한다 (`Push.kt` `VerifyReceiver` → `/verify/respond`)
3. 앱: 아래 탭 **알림 · 오늘 · 기록** + 사건 상세 ("확인했어요 / 해결됐어요" → `PATCH /events/{id}/status`)

**부모님 폰** (`ParentActivity`)
1. 자녀가 보낸 초대 코드를 붙여 넣어 참여
2. 보호 설정: ① 알림 읽기 ② 다른 앱 위에 표시 ③ 연락처·문자·녹음 파일 ④ 배터리 — ①②가 켜지면 지킴이 시작, 이후 앱을 열 필요 없다
3. 문자 → `/alerts/check`, 통화 녹음 → `/calls/analyze`, 앱 설치 → `/actions/app-install`. 응답을 보고 폰이 경고창·안내 카드를 띄운다
   (경고창·안내 카드는 팀원 A안. 문자 앱 헤드업 알림과 안 겹치게 위쪽 200dp 를 비움)

**테스트로 둘러보기** (로그인 화면 아래): 로그인·서버 없이 BE 응답과 같은 모양의 예시 데이터(`Demo.kt`)로 모든 화면을 본다.
부모님 폰은 시험 문자·실제 문자에 예시 판단으로 경고창이 뜬다. 서버로는 아무것도 보내지 않는다.

폰을 다시 켜면 `BootReceiver` 가 지킴이를 다시 시작한다.

에뮬레이터에서 권한을 adb 로 한 번에 켜기:

```bash
adb shell cmd notification allow_listener kr.codyssey.jikimi/kr.codyssey.jikimi.NotiListener
adb shell appops set kr.codyssey.jikimi SYSTEM_ALERT_WINDOW allow
adb emu sms send 01098765432 "엄마 나 폰 액정 깨져서 수리 맡겼어. 이 번호로 문자줘"   # 에뮬레이터로 문자 보내기
```

로그: `adb logcat -s jikimi`

## 확인된 것 / 남은 것

- [x] 빌드·단위 테스트 (가벼운 모델·1차 필터가 파이썬과 같은 결과)
- [x] 에뮬레이터 테스트 모드: 실제 문자(adb emu sms) → 경고창·안내 카드가 헤드업 알림과 안 겹침, 자녀 화면 탭·상세
- [x] 통화 녹음 감지 (에뮬레이터): `Recordings/Call/…m4a` → 감지 → 업로드. 미디어 변경 알림 + 15초마다 확인, 처음 켤 때 있던 녹음은 안 올림
  - 시험 팁: `adb push` 한 파일은 '쓰는 중(is_pending=1)'으로 남아 다른 앱에 안 보인다 → `adb shell content update --uri content://media/external/file/<id> --bind is_pending:i:0`
- [ ] 실제 BE 서버와 연결 (가입·초대·분석·가족 확인·사건)
- [ ] 푸시: BE 담당이 만든 Firebase 의 `google-services.json` 을 넣고 빌드
- [ ] 실기기 갤럭시: '통화 자동 녹음' 실제 폴더·파일 이름 형식 (`GuardService.newestCallRecording()`)
