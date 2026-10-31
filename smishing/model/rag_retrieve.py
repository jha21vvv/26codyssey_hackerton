import argparse
import glob
import json
import os
from typing import Dict, List, Tuple

import numpy as np
from sentence_transformers import SentenceTransformer


def script_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def load_train_examples(train_path: str) -> Tuple[List[Dict], List[Dict]]:
    seen_texts = set()
    normal_examples: List[Dict] = []
    fraud_examples: List[Dict] = []

    with open(train_path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            text = row["text"]
            label = int(row["label"])

            if text in seen_texts:
                continue
            seen_texts.add(text)

            item = {"text": text, "label": label}
            if label == 1:
                fraud_examples.append(item)
            elif label == 0:
                normal_examples.append(item)
            else:
                raise ValueError(f"알 수 없는 라벨입니다: line={line_no}, label={label}")

    return normal_examples, fraud_examples


def load_sms_queries(path: str) -> List[Dict]:
    queries: List[Dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            query_id = str(row.get("orig_id", idx))
            queries.append(
                {
                    "id": query_id,
                    "y": int(row["label"]),
                    "text": row["text"],
                    "embed_text": row["text"],
                }
            )
    return queries


def load_voice_queries(pattern: str) -> List[Dict]:
    queries: List[Dict] = []
    for path in sorted(glob.glob(pattern)):
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        file_name = os.path.splitext(os.path.basename(path))[0]
        queries.append(
            {
                "id": file_name,
                "y": 1,
                "text": text,
                "embed_text": text[:500],
            }
        )
    return queries


def encode_texts(model: SentenceTransformer, texts: List[str]) -> np.ndarray:
    embeddings = model.encode(
        texts,
        batch_size=64,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=True,
    )
    return np.asarray(embeddings, dtype=np.float32)


def top_k_shots(
    query_vec: np.ndarray,
    examples: List[Dict],
    example_matrix: np.ndarray,
    k: int,
) -> Tuple[List[Dict], float]:
    if len(examples) == 0:
        return [], 0.0

    sims = example_matrix @ query_vec
    take_k = min(k, len(examples))
    top_idx = np.argsort(-sims)[:take_k]

    shots: List[Dict] = []
    top_sims: List[float] = []
    for idx in top_idx:
        sim = float(sims[idx])
        top_sims.append(sim)
        shots.append(
            {
                "text": examples[idx]["text"],
                "label": examples[idx]["label"],
                "sim": sim,
            }
        )

    avg_sim = float(np.mean(top_sims)) if top_sims else 0.0
    return shots, avg_sim


def main() -> None:
    parser = argparse.ArgumentParser(description="RAG용 유사 사례 검색")
    parser.add_argument("target", choices=["sms", "voice"])
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--model", default="intfloat/multilingual-e5-base")
    args = parser.parse_args()

    if args.k <= 0:
        raise ValueError("--k 는 1 이상이어야 합니다.")

    base_dir = script_dir()
    out_dir = os.path.join(base_dir, "out")
    train_path = os.path.join(out_dir, "train.jsonl")

    normal_examples, fraud_examples = load_train_examples(train_path)

    if args.target == "sms":
        query_path = os.path.join(out_dir, "ext_test.jsonl")
        queries = load_sms_queries(query_path)
    else:
        voice_pattern = os.path.join(base_dir, "..", "data", "derived", "voice_transcripts_large", "*.txt")
        queries = load_voice_queries(voice_pattern)

    device = "cuda" if os.environ.get("CUDA_VISIBLE_DEVICES", None) != "" else "cpu"
    try:
        model = SentenceTransformer(args.model, device="cuda")
    except Exception:
        model = SentenceTransformer(args.model, device="cpu")
        device = "cpu"

    print(f"임베딩 모델: {args.model}")
    print(f"임베딩 장치: {device}")
    print(f"학습 정상 사례 수: {len(normal_examples)}")
    print(f"학습 사기 사례 수: {len(fraud_examples)}")
    print(f"질의 수: {len(queries)}")

    normal_passages = ["passage: " + item["text"] for item in normal_examples]
    fraud_passages = ["passage: " + item["text"] for item in fraud_examples]
    query_inputs = ["query: " + item["embed_text"] for item in queries]

    normal_matrix = encode_texts(model, normal_passages) if normal_passages else np.zeros((0, 0), dtype=np.float32)
    fraud_matrix = encode_texts(model, fraud_passages) if fraud_passages else np.zeros((0, 0), dtype=np.float32)
    query_matrix = encode_texts(model, query_inputs) if query_inputs else np.zeros((0, 0), dtype=np.float32)

    results: List[Dict] = []
    avg_top_sims: List[float] = []

    for idx, query in enumerate(queries):
        query_vec = query_matrix[idx]

        fraud_shots, fraud_avg = top_k_shots(query_vec, fraud_examples, fraud_matrix, args.k)
        normal_shots, normal_avg = top_k_shots(query_vec, normal_examples, normal_matrix, args.k)

        shots = fraud_shots + normal_shots
        present_sims = [x for x in [fraud_avg, normal_avg] if x != 0.0]
        avg_top_sims.append(float(np.mean(present_sims)) if present_sims else 0.0)

        results.append(
            {
                "id": query["id"],
                "y": query["y"],
                "text": query["text"],
                "shots": shots,
            }
        )

    output_path = os.path.join(out_dir, f"rag_shots_{args.target}.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)

    overall_avg = float(np.mean(avg_top_sims)) if avg_top_sims else 0.0
    print(f"저장 경로: {output_path}")
    print(f"질의 수: {len(results)}")
    print(f"평균 상위 유사도: {overall_avg:.6f}")


if __name__ == "__main__":
    main()
