# 스미싱·스팸 판별 파이프라인

문자 메시지와 통화 전사본이 스미싱/스팸인지 판별한다. 폴더 구조만 지키면 다른 컴퓨터에서도 그대로 동작한다.

## 필요한 폴더 구조
```
20261030-20261102해커톤/
├── model/            이 폴더 (코드)
├── data/
│   ├── build_unified.py
│   ├── Korean_message/lgaidataset.csv
│   ├── KR-MOB-SMISHING-v2/incidents/*.json
│   └── derived/unified.jsonl      (없으면 자동 생성)
├── stt/stt_local.py               (통화 전사에만 필요)
└── data/voice/*.m4a               (통화 전사에만 필요)
```
게이트웨이 코드(`cody_api.py`)는 필요 없다. `llm_classify.py` 가 직접 호출한다.

## 설치
```bash
pip install -r model/requirements.txt
```
리눅스 GPU 서버는 CUDA 에 맞는 torch 를 먼저 설치한다. macOS 에서는 `python` 대신 `python3` 를 쓴다.

## 키 (AI 판별에만 필요)
`model/.env.example` 을 `model/.env` 로 복사해 `CODY_GPT_KEY`, `CODY_CLAUDE_KEY` 를 채우거나 같은 이름의 환경 변수를 설정한다.
`CODY_BASE_URL` 은 선택이며 기본값은 `https://copa.codyssey.kr` 이다. `.env` 는 커밋하지 않는다.

## 실행 순서
```bash
python model/prepare_data.py                      # 학습/검증/테스트/외부 평가셋 생성 (unified.jsonl 자동 생성)
python model/llm_classify.py sms --n 100 --model claude-haiku-4   # 문자 AI 판별
python model/voice_stt.py 30                      # 통화 앞 30건 전사 (GPU 있으면 자동 사용)
python model/llm_classify.py voice --model claude-haiku-4         # 전사본 AI 판별
python model/train.py --epochs 3                  # BERT 파인튜닝 (cuda > mps > cpu 자동 선택)
```
동작 확인만: `python model/train.py --max_steps 2 --epochs 1 --bs 8`

## 입출력
| 파일 | 내용 |
|---|---|
| `out/{train,val,test,ext_test}.jsonl` | 분할 데이터. `text_tok` 은 링크를 `[URL_종류]` 로 바꾼 학습 입력 |
| `out/llm_sms_<모델>.jsonl` | 문자 AI 판별 결과(`gold` 정답, `label` 예측) |
| `out/llm_voice_<모델>.jsonl` | 통화 AI 판별 결과 |
| `out/best/`, `out/metrics.json` | 학습된 모델과 평가 지표 |

## 데이터 규칙
- 라벨: 0 일반, 1 스미싱/스팸, 라벨 없음은 학습 제외(택배 사칭 템플릿 중 정상 브랜드 링크뿐인 것).
- 학습은 `korean_message` 만 쓰고, 합성 사례(KR-MOB)와 통화 전사본은 외부 평가셋이다.
- 출처와 라이선스는 `data/SOURCES.md` 를 따른다.
