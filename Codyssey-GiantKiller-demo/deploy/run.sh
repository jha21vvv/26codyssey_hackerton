#!/usr/bin/env bash
# AI 서버 실행 (BE 의 AIClient 가 부르는 곳): 가상환경 준비 → 패키지 설치 → 서버 켜기
#   bash deploy/run.sh            # 0.0.0.0:8100
#   PORT=9100 bash deploy/run.sh
set -euo pipefail
cd "$(dirname "$0")/.."

PY=${PYTHON:-python3}
if [ ! -d .venv ]; then
  "$PY" -m venv .venv
fi
.venv/bin/pip install -q -r requirements.txt
[ -f .env ] || { cp .env.example .env; echo ".env 를 만들었어요. 키를 넣어 주세요: $(pwd)/.env"; }

exec .venv/bin/uvicorn ai.server:app --host 0.0.0.0 --port "${PORT:-8100}"
