import argparse
import glob
import json
import os
import re
import subprocess
import sys
import sysconfig
import tempfile
from typing import Any, Dict, List, Optional, Tuple

SYSTEM_PROMPT = '너는 한국어 문자·통화 사기(스미싱, 보이스피싱) 탐지기다. 입력이 사기/스팸이면 1, 정상이면 0 으로 판정한다. 기관·택배·은행을 사칭한 공지 형식이라도 링크·요구 사항이 정상적이면 0 일 수 있다. JSON 한 줄로만 답한다: {"label":0|1,"reason":"한 문장"}'
LABEL_RE = re.compile(r'"label"\s*:\s*([01])')
REASON_RE = re.compile(r'"reason"\s*:\s*"([^"]*)"')

HERE = os.path.expanduser("~/smishing/judge")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+", help="입력 파일 경로들")
    parser.add_argument("--sms", action="store_true", help="SMS 모드 (전체 텍스트)")
    parser.add_argument("--k", type=int, default=3, help="유사 사례 개수")
    parser.add_argument("--llm", default="claude-haiku-4", help="LLM 모델명")
    return parser.parse_args()


def load_ask():
    """cody_api 에서 ask 함수 로드"""
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    from cody_api import ask
    return ask


def build_env() -> Dict[str, str]:
    """LD_LIBRARY_PATH 에 nvidia 라이브러리 경로 추가"""
    env = os.environ.copy()
    purelib = sysconfig.get_paths()['purelib']
    nvidia_libs = glob.glob(os.path.join(purelib, 'nvidia', '*', 'lib'))
    if nvidia_libs:
        ld_path = ':'.join(nvidia_libs)
        existing_ld = env.get('LD_LIBRARY_PATH', '')
        if existing_ld:
            ld_path = ld_path + ':' + existing_ld
        env['LD_LIBRARY_PATH'] = ld_path
    return env


def run_rag_query(input_files: List[str], k: int, sms: bool) -> List[Dict[str, Any]]:
    """rag_query.py 를 subprocess 로 호출하고 결과 반환"""
    with tempfile.TemporaryDirectory() as tmpdir:
        out_json = os.path.join(tmpdir, "result.json")
        rag_query_path = os.path.join(HERE, "..", "model", "rag_query.py")
        corpus_path = os.path.join(HERE, "..", "model", "out", "train.jsonl")
        
        # 입력 파일의 절대경로
        abs_files = [os.path.abspath(f) for f in input_files]
        
        cmd = [sys.executable, rag_query_path] + abs_files + [
            '--out', out_json,
            '--k', str(k),
            '--corpus', corpus_path,
        ]
        if sms:
            cmd.append('--sms')
        
        env = build_env()
        subprocess.run(cmd, check=True, env=env, timeout=600)
        
        # 결과 읽기
        with open(out_json, 'r', encoding='utf-8') as f:
            results = json.load(f)
        
        if not isinstance(results, list):
            results = [results]
        
        return results


def trim_text(text: str, limit: int) -> str:
    return text[:limit]


def build_user_prompt(shot_text: str, input_text: str) -> str:
    """RAG 조건으로 프롬프트 생성"""
    input_trimmed = trim_text(str(input_text), 2500)
    if shot_text:
        return f"유사 사례:\n{shot_text}\n\n입력:\n{input_trimmed}"
    else:
        return f"입력:\n{input_trimmed}"


def build_shot_line(shot: Dict[str, Any]) -> str:
    """한 개 사례를 포맷팅"""
    label = int(shot["label"])
    prefix = "[사기]" if label == 1 else "[정상]"
    text = trim_text(str(shot["text"]), 160).replace("\r\n", "\n").replace("\r", "\n")
    return f"{prefix} {text}"


def extract_pred(raw: str) -> Optional[int]:
    """응답에서 label 추출"""
    try:
        data = json.loads(raw)
        if "label" in data:
            return int(data["label"])
    except (json.JSONDecodeError, ValueError, KeyError):
        pass
    
    # 정규식 폴백
    match = LABEL_RE.search(raw)
    if match is not None:
        return int(match.group(1))
    
    return None


def judge_one(ask, item: Dict[str, Any], model: str) -> Tuple[int, str, int, int, float]:
    """한 건 판정: (label, reason, fraud_count, normal_count, max_similarity)"""
    shots = item.get("shots", [])
    shot_texts = [build_shot_line(shot) for shot in shots]
    shots_block = "\n".join(shot_texts)
    
    fraud_count = sum(1 for shot in shots if int(shot["label"]) == 1)
    normal_count = sum(1 for shot in shots if int(shot["label"]) == 0)
    similarities = [shot.get("sim", 0.0) for shot in shots]
    max_similarity = max(similarities) if similarities else 0.0
    
    prompt = build_user_prompt(shots_block, item["text"])
    
    try:
        raw = ask(
            prompt,
            model=model,
            system=SYSTEM_PROMPT,
            max_tokens=200,
            temperature=0,
        )
        pred = extract_pred(raw)
        
        # JSON 파싱 시도 후 reason 추출
        reason = "판정 불가"
        m = REASON_RE.search(raw)
        if m:
            reason = m.group(1)
        
    except Exception as e:
        pred = None
        reason = f"오류: {type(e).__name__}"
    
    return pred, reason, fraud_count, normal_count, max_similarity


def main() -> None:
    # stdout 을 UTF-8 로 설정
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    
    args = parse_args()
    
    # 파일 유효성 확인
    valid_files = []
    for fpath in args.files:
        if not os.path.isfile(fpath):
            print(f"오류: 파일을 찾을 수 없습니다: {fpath}")
            sys.exit(1)
        valid_files.append(fpath)
    
    # rag_query.py 실행
    try:
        results = run_rag_query(valid_files, args.k, args.sms)
    except Exception as e:
        print(f"오류: rag_query.py 실행 실패: {e}")
        sys.exit(1)
    
    # 판정 실행
    ask = load_ask()
    judgments = []
    
    for idx, (orig_path, result) in enumerate(zip(valid_files, results)):
        orig_name = os.path.basename(orig_path)
        pred, reason, fraud_count, normal_count, max_sim = judge_one(ask, result, args.llm)
        
        label_str = "사기 의심" if pred == 1 else ("정상 추정" if pred == 0 else "판정 불가")
        sim_str = f"{max_sim:.3f}"
        output_line = f"{orig_name}: {label_str} - {reason} (참고한 사례: 사기 {fraud_count} / 정상 {normal_count}, 최고 유사도 {sim_str})"
        print(output_line)
        
        judgments.append({
            "file": orig_name,
            "label": pred,
            "reason": reason,
            "fraud_count": fraud_count,
            "normal_count": normal_count,
            "max_similarity": max_sim,
        })
    
    # 결과 저장
    out_dir = "out"
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "judge_rag_last.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
