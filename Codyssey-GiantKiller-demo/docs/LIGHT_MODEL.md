# 폰 안 1차 거르기 모델 (가벼운 모델)

문자가 오면 앱이 폰 안에서 먼저 걸러, 사기일 수 있는 문자만 BE(`POST /api/v1/alerts/check`)로 보낸다.
평범한 문자는 폰 밖으로 나가지 않는다. 최종 판단은 BE(코디세이 LLM)가 한다.

## 모델

- 종류: 로지스틱 회귀 (신경망 아님)
- 입력: 문자를 2·3글자 조각으로 나눔 → UTF-8 바이트 → FNV-1a 32비트 해시 → 65,536칸 중 한 칸
- 출력: 0~1 사이 "사기일 점수"
- 학습 데이터: meal-bbang/Korean_message (허깅페이스). 학습에만 쓰고 재배포하지 않음
- 크기: 가중치를 1바이트 정수로 줄여 64KB. 학습 약 2초, 판단 1ms 미만
- 1차 거르기 규칙: 위험 단어 OR 링크 OR 모델 점수 ≥ 0.3 → BE로 보냄. 등록된 자녀 번호면 '엄마'·'아빠'만으로는 보내지 않음
- 성능(학습에 안 쓴 문자): 사기 99% 잡음, 정상 오탐 0%. 공식 안내 문자는 사기로 보는 경향이 있어 최종 판단이 아니라 1차 거르기로만 씀 (자세한 숫자: `docs/RESULTS.md`)

## 코드 위치

앱 안 (폰에서 도는 부분)

| 파일 | 내용 |
|---|---|
| `android/app/src/main/java/kr/codyssey/jikimi/LightModel.kt` | 모델 본체. 31줄 `parse`(모델 파일 읽기), 64줄 `fnv1a`(해싱), 74줄 `features`(2·3글자 조각 → 칸 번호), 86줄 `score`(사기일 점수) |
| `android/app/src/main/java/kr/codyssey/jikimi/Guard.kt` | 모델을 쓰는 1차 거르기. 52줄 `lightModel`(모델 불러오기), 62줄 `prefilter`(위험 단어·링크·모델 점수로 BE에 보낼지 정함, 71~72줄에서 점수 계산·기준 비교) |
| `android/app/src/main/java/kr/codyssey/jikimi/Inbox.kt` | 39줄: 문자가 오면 `Guard.prefilter` 를 부르는 곳 |
| `android/app/src/main/assets/light_model.bin` | 학습된 모델 파일 (64KB) |

학습 (컴퓨터에서 돌리는 파이썬)

| 파일 | 내용 |
|---|---|
| `scripts/train_light.py` | 학습 실행 스크립트. 맨 위 설명에 데이터 준비 → 학습 → 평가 순서 |
| `ai/light_model.py` | 파이썬 쪽 모델. 44줄 `fnv1a`, 75줄 `score`, 109줄 `train`(학습), 138줄 `quantize`(1바이트로 줄이기) |

파이썬·안드로이드가 같은 점수를 내는지 확인하는 테스트

- `tests/test_light_model.py`
- `android/app/src/test/java/kr/codyssey/jikimi/LightModelTest.kt`
- 고정 예시: `tests/data/light_examples.json`, `tests/data/light_examples.tsv`
