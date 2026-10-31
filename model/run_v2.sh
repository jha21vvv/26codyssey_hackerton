set -e
cd ~/smishing/model
. ../.venv/bin/activate
python train.py --model klue/bert-base --tag base_v2 --epochs 3 --bs 64 --max_len 128 --lr 3e-5 2>&1 | tee logs/train_base_v2.log
python train.py --model klue/roberta-large --tag large_v2 --epochs 3 --bs 32 --max_len 128 --lr 1.5e-5 2>&1 | tee logs/train_large_v2.log
echo ALL_DONE
