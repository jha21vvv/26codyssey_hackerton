import argparse
import glob
import json
import os
from typing import Dict, List, Tuple
import hashlib

import numpy as np
from sentence_transformers import SentenceTransformer

try:
    from faster_whisper import WhisperModel
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False

_whisper_model = None


def get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        if not WHISPER_AVAILABLE:
            raise ImportError("faster_whisper가 설치되어 있지 않습니다.")
        _whisper_model = WhisperModel('large-v3', device='cuda', compute_type='float16')
    return _whisper_model


def transcribe_audio(audio_path: str) -> str:
    model = get_whisper_model()
    segments, _ = model.transcribe(audio_path, language='ko', vad_filter=True, beam_size=5)
    text = ' '.join([segment.text for segment in segments])
    return text


def read_text_file(text_path: str) -> str:
    with open(text_path, 'r', encoding='utf-8') as f:
        return f.read()


def load_input_text(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    if ext in ['.m4a', '.mp3', '.wav', '.mp4']:
        return transcribe_audio(file_path)
    elif ext == '.txt':
        return read_text_file(file_path)
    else:
        raise ValueError(f"지원하지 않는 파일 확장자: {ext}")


def normalize_whitespace(text: str) -> str:
    return ' '.join(text.split())


def create_windows(text: str, window_size: int = 200, stride: int = 100) -> List[str]:
    # --sms 옵션이면 호출 전에 전체 텍스트를 반환하므로 여기서는 일반 창 생성
    windows = []
    for i in range(0, len(text), stride):
        window = text[i:i + window_size]
        if window.strip():
            windows.append(window)
    return windows if windows else [text]


def load_corpus(corpus_path: str) -> Tuple[List[Dict], List[Dict]]:
    seen_texts = set()
    normal_examples: List[Dict] = []
    fraud_examples: List[Dict] = []

    with open(corpus_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            text = row['text']
            label = int(row['label'])

            if label not in [0, 1]:
                continue
            if text in seen_texts:
                continue
            seen_texts.add(text)

            item = {'text': text, 'label': label}
            if label == 1:
                fraud_examples.append(item)
            else:
                normal_examples.append(item)

    return normal_examples, fraud_examples


def compute_cache_hash(normal_texts: List[str], fraud_texts: List[str]) -> str:
    combined = '|'.join(normal_texts + fraud_texts)
    return hashlib.sha256(combined.encode()).hexdigest()


def load_or_create_embeddings(
    model: SentenceTransformer,
    normal_examples: List[Dict],
    fraud_examples: List[Dict],
    cache_path: str
) -> Tuple[np.ndarray, np.ndarray]:
    normal_texts = ['passage: ' + item['text'] for item in normal_examples]
    fraud_texts = ['passage: ' + item['text'] for item in fraud_examples]

    current_hash = compute_cache_hash(normal_texts, fraud_texts)

    # 캐시 로드 시도
    if os.path.exists(cache_path):
        try:
            cache_data = np.load(cache_path, allow_pickle=True)
            cached_hash = str(cache_data['hash'])
            if cached_hash == current_hash:
                normal_matrix = cache_data['normal_matrix']
                fraud_matrix = cache_data['fraud_matrix']
                return normal_matrix, fraud_matrix
        except Exception:
            pass

    # 캐시 없으면 임베딩 생성
    if normal_texts:
        normal_matrix = model.encode(
            normal_texts,
            batch_size=64,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False
        ).astype(np.float32)
    else:
        normal_matrix = np.zeros((0, 0), dtype=np.float32)

    if fraud_texts:
        fraud_matrix = model.encode(
            fraud_texts,
            batch_size=64,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False
        ).astype(np.float32)
    else:
        fraud_matrix = np.zeros((0, 0), dtype=np.float32)

    # 캐시 저장
    np.savez(cache_path, hash=current_hash, normal_matrix=normal_matrix, fraud_matrix=fraud_matrix)

    return normal_matrix, fraud_matrix


def top_k_per_window(
    query_vecs: np.ndarray,
    normal_examples: List[Dict],
    normal_matrix: np.ndarray,
    fraud_examples: List[Dict],
    fraud_matrix: np.ndarray,
    k: int
) -> List[Dict]:
    # 각 창별로 상위 k개씩 검색
    fraud_per_window = []
    normal_per_window = []

    for query_vec in query_vecs:
        if len(fraud_examples) > 0:
            sims = fraud_matrix @ query_vec
            take_k = min(k, len(fraud_examples))
            top_idx = np.argsort(-sims)[:take_k]
            for idx in top_idx:
                fraud_per_window.append({
                    'text': fraud_examples[idx]['text'],
                    'label': 1,
                    'sim': float(sims[idx])
                })

        if len(normal_examples) > 0:
            sims = normal_matrix @ query_vec
            take_k = min(k, len(normal_examples))
            top_idx = np.argsort(-sims)[:take_k]
            for idx in top_idx:
                normal_per_window.append({
                    'text': normal_examples[idx]['text'],
                    'label': 0,
                    'sim': float(sims[idx])
                })

    # 전체에서 클래스별 상위 k개 추출 (중복 제거)
    seen = set()
    final_shots = []

    fraud_per_window.sort(key=lambda x: -x['sim'])
    fraud_count = 0
    for shot in fraud_per_window:
        if shot['text'] not in seen and fraud_count < k:
            final_shots.append(shot)
            seen.add(shot['text'])
            fraud_count += 1

    normal_per_window.sort(key=lambda x: -x['sim'])
    normal_count = 0
    for shot in normal_per_window:
        if shot['text'] not in seen and normal_count < k:
            final_shots.append(shot)
            seen.add(shot['text'])
            normal_count += 1

    return final_shots


def main() -> None:
    parser = argparse.ArgumentParser(description='RAG용 유사 사례 검색')
    parser.add_argument('files', nargs='+', help='입력 파일(음성/텍스트)')
    parser.add_argument('--out', required=True, help='출력 JSON 파일')
    parser.add_argument('--k', type=int, default=3, help='상위 k개')
    parser.add_argument('--sms', action='store_true', help='SMS 모드 (전체 텍스트 사용)')
    parser.add_argument('--corpus', default='out/train.jsonl', help='코퍼스 경로')
    parser.add_argument('--model', default='intfloat/multilingual-e5-base', help='임베딩 모델')

    args = parser.parse_args()

    if args.k <= 0:
        raise ValueError('--k는 1 이상이어야 합니다.')

    # 코퍼스 로드
    normal_examples, fraud_examples = load_corpus(args.corpus)
    print(f'코퍼스 로드: 정상 {len(normal_examples)}, 사기 {len(fraud_examples)}')

    # 임베딩 모델 로드
    device = 'cuda' if os.environ.get('CUDA_VISIBLE_DEVICES', '0') != '' else 'cpu'
    try:
        model = SentenceTransformer(args.model, device='cuda')
        device = 'cuda'
    except Exception:
        model = SentenceTransformer(args.model, device='cpu')
        device = 'cpu'

    # 캐시 경로
    cache_dir = os.path.dirname(args.corpus) or '.'
    cache_path = os.path.join(cache_dir, 'rag_corpus_cache.npz')

    # 임베딩 로드 또는 생성
    normal_matrix, fraud_matrix = load_or_create_embeddings(
        model, normal_examples, fraud_examples, cache_path
    )

    results: List[Dict] = []

    for file_path in args.files:
        file_stem = os.path.splitext(os.path.basename(file_path))[0]
        text = load_input_text(file_path)
        text = normalize_whitespace(text)

        # 창 생성
        if args.sms:
            windows = [text]
        else:
            windows = create_windows(text, window_size=200, stride=100)

        # 질의 임베딩
        query_inputs = ['query: ' + window for window in windows]
        query_matrix = model.encode(
            query_inputs,
            batch_size=64,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False
        ).astype(np.float32)

        # 유사도 검색
        shots = top_k_per_window(
            query_matrix,
            normal_examples, normal_matrix,
            fraud_examples, fraud_matrix,
            args.k
        )

        results.append({
            'id': file_stem,
            'text': text,
            'shots': shots
        })

    # 결과 저장
    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f'결과 저장: {args.out}')


if __name__ == '__main__':
    main()
