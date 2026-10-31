#!/usr/bin/env bash
# GPU 서버: large-v3 전사 -> 분류기 평가. 사용: nohup bash model/run_voice_server.sh > model/logs/voice_run.log 2>&1 &
set -euo pipefail
cd "$(dirname "$0")/.."
. .venv/bin/activate
python -m pip install -q faster-whisper
SP=$(python -c "import site;print(site.getsitepackages()[0])")
export LD_LIBRARY_PATH=$(ls -d "$SP"/nvidia/*/lib | tr '\n' ':')${LD_LIBRARY_PATH:-}
cd model
python voice_large.py
python eval_voice.py ../data/derived/voice_transcripts_large out/best_base out/best_large
echo VOICE_ALL_DONE
