"""한국어 BERT 로 스미싱/스팸 이진 분류기를 파인튜닝한다.

사용: python train.py [--model klue/bert-base] [--epochs 3] [--max_steps N(스모크 테스트)]
입력: out/{train,val,test,ext_test}.jsonl (prepare_data.py 가 생성)
출력: out/best/ (모델+토크나이저), out/metrics.json
"""
import argparse, json, random
from pathlib import Path
import numpy as np, torch
from sklearn.metrics import classification_report, f1_score
from torch.utils.data import DataLoader
from transformers import AutoModelForSequenceClassification, AutoTokenizer, get_linear_schedule_with_warmup

OUT = Path(__file__).resolve().parent / "out"


def read(name):
    if not (OUT / f"{name}.jsonl").exists():
        raise SystemExit("학습 데이터가 없습니다. 먼저 `python model/prepare_data.py` 를 실행하세요.")
    return [json.loads(l) for l in open(OUT / f"{name}.jsonl", encoding="utf-8")]


def loader(rows, tok, bs, max_len, shuffle):
    def collate(b):
        enc = tok([r.get("text_tok", r["text"]) for r in b], truncation=True, max_length=max_len, padding=True, return_tensors="pt")
        enc["labels"] = torch.tensor([r["label"] for r in b])
        return enc
    return DataLoader(rows, batch_size=bs, shuffle=shuffle, collate_fn=collate)


@torch.no_grad()
def predict(model, dl, dev):
    model.eval()
    ys, ps = [], []
    for b in dl:
        b = {k: v.to(dev) for k, v in b.items()}
        y = b.pop("labels")
        ps += model(**b).logits.argmax(-1).tolist()
        ys += y.tolist()
    return ys, ps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="klue/bert-base")
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--bs", type=int, default=32)
    ap.add_argument("--lr", type=float, default=3e-5)
    ap.add_argument("--max_len", type=int, default=128)
    ap.add_argument("--max_steps", type=int, default=0)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--tag", default="", help="출력 폴더 접미사: out/best_<tag>, metrics_<tag>.json")
    a = ap.parse_args()

    random.seed(a.seed); np.random.seed(a.seed); torch.manual_seed(a.seed)
    if torch.cuda.is_available():
        dev = "cuda"
    elif hasattr(torch, "xpu") and torch.xpu.is_available():
        dev = "xpu"
    elif torch.backends.mps.is_available():
        dev = "mps"
    else:
        dev = "cpu"
    amp = dev in ("cuda", "xpu")  # cuda, xpu 모두 bf16 혼합정밀
    amp_dtype = torch.bfloat16  # L4(Ada)는 bf16 지원: fp16 스케일러 없이 안정적
    if dev == "cuda":
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True
    sfx = f"_{a.tag}" if a.tag else ""
    print("device:", dev)
    tok = AutoTokenizer.from_pretrained(a.model)
    model = AutoModelForSequenceClassification.from_pretrained(a.model, num_labels=2).to(dev)

    train, val, test, ext, vtest = (read(n) for n in ("train", "val", "test", "ext_test", "voice_test"))
    if a.max_steps:  # 스모크 테스트용 축소
        train, val, test, ext, vtest = train[:64], val[:32], test[:32], ext[:32], vtest[:32]
    tl = loader(train, tok, a.bs, a.max_len, True)
    vl, sl, el, cl = (loader(r, tok, 64, a.max_len, False) for r in (val, test, ext, vtest))

    total = a.max_steps or len(tl) * a.epochs
    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=0.01)
    sch = get_linear_schedule_with_warmup(opt, int(total * 0.1), total)
    scaler = torch.amp.GradScaler(enabled=False)  # bf16 은 스케일러 불필요

    best, step = -1.0, 0
    for ep in range(a.epochs):
        model.train()
        for b in tl:
            b = {k: v.to(dev) for k, v in b.items()}
            with torch.autocast(dev, dtype=amp_dtype, enabled=amp):
                loss = model(**b).loss
            opt.zero_grad()
            scaler.scale(loss).backward()
            scaler.unscale_(opt)
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            scaler.step(opt); scaler.update(); sch.step()
            step += 1
            if step % 50 == 0:
                print(f"step {step}/{total} loss {loss.item():.4f}")
            if a.max_steps and step >= a.max_steps:
                break
        y, p = predict(model, vl, dev)
        f1 = f1_score(y, p, average="macro")  # 일반/스미싱 균형 반영
        print(f"epoch {ep + 1} val macro-f1 {f1:.4f}")
        if f1 > best:
            best = f1
            model.save_pretrained(OUT / f"best{sfx}"); tok.save_pretrained(OUT / f"best{sfx}")
        if a.max_steps and step >= a.max_steps:
            break

    model = AutoModelForSequenceClassification.from_pretrained(OUT / f"best{sfx}").to(dev)
    metrics = {"val_f1": best, "model": a.model}
    for name, dl in (("test", sl), ("ext_test", el), ("voice_test", cl)):
        y, p = predict(model, dl, dev)
        print(f"\n== {name} ==")
        print(classification_report(y, p, labels=[0, 1], target_names=["일반", "스미싱"], digits=4, zero_division=0))
        metrics[name] = classification_report(y, p, labels=[0, 1], target_names=["일반", "스미싱"], output_dict=True, zero_division=0)
    json.dump(metrics, open(OUT / f"metrics{sfx}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
