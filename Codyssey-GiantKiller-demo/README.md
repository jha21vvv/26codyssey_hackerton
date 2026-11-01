# 🛡️ 부모님 지킴이 (머꼬) — AI 서버 · 안드로이드 앱

부모님 폰에 오는 문자·통화·앱 설치를 AI가 확인하고, 위험하면 가족(자녀)과 함께 막는 서비스.
코디세이 AI 해커톤 2026 · 팀 자이언트킬러

이 레포는 **백엔드(BE 레포 `ted1117/Codyssey-GiantKiller-BE`)에 붙일 두 가지**예요. BE 코드는 BE 레포에 있어요.

| 무엇 | 폴더 | BE 와 연결 |
|---|---|---|
| **AI 서버** | `ai/` · `deploy/` | BE `app/core/ai.py` 의 `AIClient` 가 부른다 → 계약 **[docs/AI_API.md](docs/AI_API.md)** |
| **안드로이드 앱** (부모님 폰·자녀 폰) | `android/` | BE `/api/v1/...` 를 부른다 → **[android/README.md](android/README.md)** |

평가·검증 숫자: [docs/RESULTS.md](docs/RESULTS.md)

## AI 서버

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env            # 코디세이 게이트웨이 키·BERT 폴더·Whisper 주소 (없어도 규칙으로 동작)
bash deploy/run.sh              # 0.0.0.0:8100  (재부팅 후 자동 시작: deploy/jikimi.service)
```

| 주소 | BE 함수 | 응답 (BE 모델 그대로) |
|---|---|---|
| `POST /v1/alerts/analyze` `{"text"}` | `analyze_alert(text)` | `classification` · `requires_attention` · `risk_level` · `summary` |
| `POST /v1/calls/analyze` (file) | `analyze_call(file)` | 위 + `instructions[{instruction_type, description}]` |

**판단 순서** (`ai/analyzer.py`): ① 키워드 규칙 → ② 팀원 BERT(`CLASSIFIER_DIR`) → ③ LLM(코디세이 게이트웨이) → ④ 안전망.
LLM 이 실패하거나 엉뚱하게 답해도 '안전'으로 넘기지 않고 규칙으로 대신한다. 자세히: [docs/AI_API.md](docs/AI_API.md)

| 설정 (`.env`) | 쓰임 |
|---|---|
| `CODY_CLAUDE_KEY` / `CODY_GPT_KEY` (+ `CODY_MODEL`, 기본 claude-haiku-4) | 코디세이 게이트웨이 LLM — 팀원 `model/llm_classify.py` 와 같은 호출 |
| `CLASSIFIER_DIR` | 팀원이 학습한 BERT (서버 `~/nahyun/model/out/best`, large 는 `out/best_large` 로 폴더만 바꾸면 됨). `requirements-gpu.txt` |
| `WHISPER_API_URL` · `WHISPER_MODEL` (기본 large-v3) | 받아쓰기: GPU 서버 faster-whisper (`deploy/whisper_server.py`), 없으면 이 컴퓨터의 faster-whisper |
| `WHISPER_DIARIZE=1` + `HF_TOKEN` | 화자 구분 (pyannote) → `상대:` / `부모님:` 줄. 지시는 상대 말에서만 (`ai/diarize.py`) |
| 아무것도 없음 | 키워드 규칙 (`ai/rules.py`), 녹음은 `.txt` 대본만 |

AI만 따로 시험:

```bash
.venv/bin/python scripts/try_ai.py --demo
curl -s localhost:8100/v1/alerts/analyze -H 'content-type: application/json' -d '{"text":"엄마 나 폰 고장났어 이 번호로 문자줘"}'
curl -s localhost:8100/v1/calls/analyze -F file=@samples/calls/prosecutor_1.txt
```

## 안드로이드 앱

```bash
cd android && ./gradlew :app:assembleDebug -Pjikimi.serverUrl=https://BE주소     # app/build/outputs/apk/debug/app-debug.apk
```

앱 하나로 두 역할: **부모님 폰**(문자·통화 녹음·앱 설치를 BE 로 보고, 위험하면 화면 위 경고창) / **자녀 폰**(가족 확인 "내가 보냈어요 / 안 보냈어요", 사건 목록·상세).
로그인 화면의 **"테스트로 둘러보기"** 는 서버 없이 예시 데이터로 모든 화면을 본다. 자세히: [android/README.md](android/README.md)

## 개인정보 설계

1. **폰 안에서 먼저 거름** (`Guard.kt` = `ai/prefilter.py`): 위험 단어 OR 링크 OR **폰 안 가벼운 모델 점수 ≥ 0.3** 일 때만 BE 로. 평범한 문자는 폰 밖으로 안 나간다 ([RESULTS](docs/RESULTS.md): Korean_message 평범한 문자 70% 가 폰에 남음)
2. **가려서 전송** (폰 `Guard.mask`, AI 서버 `ai/privacy.py` 에서 한 번 더): 이름·전화번호·계좌번호·주민번호 → `[이름]` `[전화번호]` `[계좌번호]`. 링크는 판단에 필요해서 남긴다
3. **원문은 로그에 남기지 않음**, 자녀에게는 요약만
4. **통화 원본은 Whisper 로만**(GPU 서버 또는 이 컴퓨터), 받아쓰기 직후 삭제. 외부 음성 API 로 보내지 않는다

## 테스트

```bash
.venv/bin/python -m unittest                      # AI 서버 계약(BE 모양)·LLM 호출·BERT 판단·데이터·1차 필터·가벼운 모델·화자 구분
cd android && ./gradlew :app:testDebugUnitTest    # 가벼운 모델·1차 필터가 파이썬과 같은 결과
.venv/bin/python scripts/eval_ai.py               # 비교표 (규칙 / 가벼운 모델 / BERT). LLM 은 --engines 로 지정할 때만
```

⚠️ `ai/data/testset.jsonl` 55개는 직접 쓴 예시이고 규칙을 이걸 보며 다듬었다. 발표용 정확도는 처음 보는 사례로 잰다.

## 데이터

| 데이터 | 쓰임 | 라이선스 |
|---|---|---|
| KR-MOB-SMISHING v1 (합성) | 평가 | CC BY-NC 4.0 (비상업, 출처 표기) |
| meal-bbang/Korean_message (Hugging Face) | 가벼운 모델 학습·평가 | 표기 없음 — 학습에만, 데이터 재배포 안 함 |

데이터 파일은 저장소에 없다 (`/data/`). 받아서 쓰는 법:

```bash
mkdir -p data/raw/korean_message && curl -L -o data/raw/korean_message/lgaidataset.csv \
  https://huggingface.co/datasets/meal-bbang/Korean_message/resolve/main/lgaidataset.csv
.venv/bin/python scripts/import_korean_message.py          # 1=정상, 2=사기(⚠️ 반대), 3=정상 안내 → data/sets/korean_message.jsonl
.venv/bin/python scripts/split_data.py data/sets/korean_message.jsonl --test-ratio 0.1
.venv/bin/python scripts/train_light.py                    # 폰 안 가벼운 모델 → android/app/src/main/assets/light_model.bin
unzip ~/Downloads/KR-MOB-SMISHING-100-v1.zip -d data/raw && .venv/bin/python scripts/import_kr_mob.py
```

BERT 학습은 팀원 것 (서버 `~/nahyun/model`: `prepare_data.py` → `train.py`).

## 구조

```
ai/            AI 서버와 판단
  server.py      BE AIClient 용 주소 2개 (docs/AI_API.md)
  analyzer.py    판단 순서: 규칙 → BERT → LLM → 안전망
  rules.py       키워드 규칙 (LLM 없을 때·실패 시, 안전망)
  classifier.py  팀원 BERT 불러 쓰기 (링크 전처리도 팀원과 같게)
  llm.py         코디세이 게이트웨이(기본) · OpenAI 호환 호출 (httpx)
  prompts.py     LLM 프롬프트
  transcribe.py  녹음 → 텍스트 (Whisper API / faster-whisper / .txt)
  diarize.py     통화 화자 구분 (pyannote) → '상대:' / '부모님:'
  privacy.py     가리기
  light_model.py 폰 안 가벼운 1차 모델 (안드로이드 LightModel.kt 와 같은 점수)
  prefilter.py   폰 1차 필터 규칙 (Guard.kt 와 같음)
  schema.py      결과 형식 정규화
  data/          판단 테스트 문자 (testset.jsonl)
android/       안드로이드 앱 (BE API) — android/README.md
  testscamapp/   앱 설치 감지 시험용 빈 앱 "시험용 검찰사칭앱"
deploy/        AI 서버 실행 스크립트·systemd, GPU 서버용 Whisper 서버
docs/          AI_API.md (AI 서버 계약), RESULTS.md (평가·검증 결과)
tests/         테스트 (unittest), data/ (파이썬·안드로이드 공통 고정 예시)
samples/calls/ 시험용 통화 대본·음성
scripts/       try_ai.py, eval_ai.py, import_*.py, split_data.py, train_light.py
```
