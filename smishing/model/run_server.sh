#!/usr/bin/env bash
# GPU 서버(NVIDIA L4 23GB)에서 실행: 환경 구성 -> 데이터 분할 -> 기준 모델 -> 대형 모델 순차 학습
# 사용: cd ~/smishing && nohup bash model/run_server.sh > model/logs/server_run.log 2>&1 &
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p model/logs
if [ ! -x .venv/bin/python ]; then
  rm -rf .venv
  python3 -m venv --without-pip .venv   # python3-venv 패키지(ensurepip)가 없는 서버 대응
fi
. .venv/bin/activate
if ! python -m pip --version >/dev/null 2>&1; then
  curl -fsSL https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py
  python /tmp/get-pip.py -q
fi
python -c "import torch" 2>/dev/null || python -m pip install -q torch --index-url https://download.pytorch.org/whl/cu128
python -m pip install -q transformers scikit-learn sentencepiece
python -c "import torch;print('cuda', torch.cuda.is_available(), torch.cuda.get_device_name(0))"
cd model
python prepare_data.py
python train.py --model klue/bert-base    --tag base  --epochs 3 --bs 64 --max_len 128 --lr 3e-5 2>&1 | tee logs/train_base.log
python train.py --model klue/roberta-large --tag large --epochs 3 --bs 32 --max_len 128 --lr 1.5e-5 2>&1 | tee logs/train_large.log
echo ALL_DONE
