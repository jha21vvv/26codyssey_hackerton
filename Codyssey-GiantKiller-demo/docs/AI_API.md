# AI 서버 API 계약 (v2)

백엔드(BE 레포 `ted1117/Codyssey-GiantKiller-BE`)의 `app/core/ai.py` `AIClient` 가 HTTP 로 부르는 **별도 AI 서버**예요.
주소는 `AIClient` 의 두 함수에 맞춘 **두 개뿐**이고, 응답은 BE 내부 결과 모델 **그대로**예요 (다른 필드 없음).

- 코드: `ai/server.py` · 계약 테스트: `tests/test_ai_server.py` (이 문서의 모양이 바뀌면 테스트가 깨짐)
- 실행: `bash deploy/run.sh` (= `uvicorn ai.server:app --host 0.0.0.0 --port 8100`)

## 주소

| BE 함수 | 이 서버 | 요청 | 응답 (BE 모델) |
|---|---|---|---|
| `analyze_alert(text)` | `POST /v1/alerts/analyze` | JSON `{"text": "가린 문자"}` | `AlertAnalysisResult`: `{"classification", "requires_attention", "risk_level", "summary"}` |
| `analyze_call(file)` | `POST /v1/calls/analyze` | multipart `file` (녹음) | `CallAnalysisResult`: 위 + `"instructions": [{"instruction_type", "description"}]` |
| (상태 확인) | `GET /health` | | `{"ok", "schema_version": "2", "llm": "cody|openai|rule", "transcribe": "whisper_api|whisper_local|none", "bert": 모델 폴더|null}` |

예:

```bash
curl -s localhost:8100/v1/alerts/analyze -H 'content-type: application/json' -d '{"text":"엄마 나 폰 고장났어 이 번호로 문자줘"}'
# {"classification":"CHILD_IMPERSONATION","requires_attention":true,"risk_level":"HIGH","summary":"…"}

curl -s localhost:8100/v1/calls/analyze -F file=@samples/calls/prosecutor_1.txt
# {"classification":"SCAM","requires_attention":true,"risk_level":"HIGH","summary":"…",
#  "instructions":[{"instruction_type":"INSTALL_APP","description":"검찰청 보안"},{"instruction_type":"TRANSFER","description":null}]}
```

BE 쪽 연결 예 (`AIClient` 의 두 함수만, BE 코드는 BE 담당이 고친다):

```python
r = await http.post(f"{AI_URL}/v1/alerts/analyze", json={"text": text}, headers={"X-AI-Key": KEY}, timeout=30)
return AlertAnalysisResult.model_validate(r.raise_for_status().json())
# 통화: files={"file": (file.filename, await file.read())} → CallAnalysisResult.model_validate(...)
```

## 값

| 필드 | 값 | 뜻 |
|---|---|---|
| `classification` | `SCAM` | 사기·스미싱·보이스피싱 |
| | `CHILD_IMPERSONATION` | 자녀 사칭 → BE 가 가족 확인 요청을 만든다 |
| | `NEED_EXPLAIN` | 헷갈리는 안내(관리비 자동이체·인증번호 등) — `summary` 에 부모님께 보여 줄 쉬운 설명 |
| | `SAFE` | 할 일 없음 |
| `requires_attention` | `true` / `false` | `SCAM`·`CHILD_IMPERSONATION` 일 때만 `true` (BE 규칙: 사칭이면 반드시 true) |
| `risk_level` | `LOW` `MEDIUM` `HIGH` | 사기·사칭은 최소 `MEDIUM` |
| `summary` | | 자녀에게 보여 줄 요약 (원문 아님, 이름·번호는 가림) |
| `instruction_type` | `INSTALL_APP` | 앱 설치 (링크, "보안 앱" 등) |
| | `INSTALL_REMOTE` | 원격 제어 앱 (팀뷰어·애니데스크·퀵서포트) |
| | `TRANSFER` | 계좌 이체·송금·상품권 |
| | `CASH` | 현금 인출·전달·보관 |
| | `SHARE_INFO` | 인증번호·비밀번호·카드번호·신분증 요구 |
| `description` | | `INSTALL_*` 이면 통화에서 설치하라고 한 앱 이름 (예: `"검찰청 보안"`), 그 밖은 `null` |

통화 지시는 받아쓰기의 `상대:` 줄에서만 뽑아요 (부모님이 "이체요?" 하고 되묻는 말은 지시가 아님). 화자 구분은 `WHISPER_DIARIZE=1`.

## 판단 순서 (`ai/analyzer.py`)

1. **키워드 규칙** (`ai/rules.py`) — 항상
2. **팀원 BERT** (스미싱/스팸 이진 분류, `CLASSIFIER_DIR`) — 설정했을 때만. large 모델로 바꿀 땐 폴더만 바꾼다
3. **LLM** (코디세이 게이트웨이, `CODY_*`) — 설정했을 때만
4. **안전망**
   - LLM 이 있으면 LLM 판단이 기본. 규칙이 위험이라 했는데 LLM 이 놓치면 규칙, LLM 이 '안전'인데 BERT ≥ 0.9(`CLASSIFIER_STRONG`) 면 사기(주의)
   - LLM 이 없거나 실패하면 규칙. 규칙이 '안전'인데 BERT ≥ 0.5(`CLASSIFIER_THRESHOLD`) 면 사기(주의), 규칙이 '안내'인데 BERT ≥ 0.9 면 사기(주의)
   - BERT 기준을 높게 둔 이유: 팀원 base 모델이 외부 시험(공식 안내 문자·통화 전사)을 전부 스미싱으로 봐서. large 결과를 보고 조정

## 오류 — 절대 '안전'으로 처리하지 말 것

| 코드 | 언제 | BE 처리 |
|---|---|---|
| 200 | 정상. LLM 이 실패하거나 엉뚱하게 답해도 **규칙으로 대신** 판단하므로 200 | 그대로 사용 |
| 400 | 빈 파일 | 실패 기록 |
| 401 | `X-AI-Key` 틀림 | 설정 확인 |
| 413 / 415 | 파일이 너무 큼 / 형식이 다름 | 실패 기록 |
| 422 | 입력 형식 오류, 녹음에 말소리 없음 | 실패 기록 |
| 502 | 받아쓰기(Whisper) 실패 | BE: `AI_REQUEST_FAILED` |
| 503 | 받아쓰기 엔진 미설정 | 운영자에게 알림 |

## 공통

| 항목 | 값 |
|---|---|
| 인증 | `.env` 에 `AI_SERVER_KEY` 를 정하면 모든 요청에 헤더 `X-AI-Key: <값>` (정하지 않으면 인증 없음) |
| 개인정보 | 받은 내용을 한 번 더 가림(이름·전화번호·계좌·주민번호). 원문은 로그에 안 남김. 녹음은 받아쓰기 직후 삭제, 외부 API 로 안 보냄 |
| 녹음 형식 | `.m4a .mp3 .wav .aac .ogg .flac .amr .3gp .aiff` (최대 25MB, `AI_MAX_AUDIO_MB`). 시험용 `.txt` 대본도 받음 |

## 설정 (`.env`)

| 설정 | 설명 |
|---|---|
| `CODY_CLAUDE_KEY` `CODY_GPT_KEY` `CODY_MODEL` `CODY_BASE_URL` | 코디세이 게이트웨이 LLM (기본 claude-haiku-4, 팀원 `llm_classify.py` 와 같은 호출) |
| `OPENAI_BASE_URL` `OPENAI_API_KEY` `OPENAI_MODEL` | OpenAI 호환 LLM (GPU 서버 vLLM 등) |
| `CLASSIFIER_DIR` `CLASSIFIER_THRESHOLD` `CLASSIFIER_STRONG` | 팀원 BERT 폴더(`out/best` → large 는 `out/best_large`), 기준 0.5 / 0.9 |
| `WHISPER_API_URL` `WHISPER_MODEL` `WHISPER_DIARIZE` `HF_TOKEN` | GPU 서버 faster-whisper(`deploy/whisper_server.py`, 기본 large-v3), 화자 구분 |
| `LLM_TIMEOUT` `LLM_DAILY_LIMIT` | LLM 대기 초(20), 하루 상한(200) — 넘으면 규칙 |
| `AI_SERVER_KEY` `AI_MAX_AUDIO_MB` | BE ↔ AI 서버 공유 키, 녹음 최대 크기 |
