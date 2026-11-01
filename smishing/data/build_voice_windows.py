"""금감원 보이스피싱 전사본(large-v3)을 200자 창으로 잘라 학습용 행으로 만든다. 서버에서 실행한다.

사용: python build_voice_windows.py <전사본 폴더>
출력: derived/voice_transcripts.jsonl  (text, label=1, orig_id="<통화파일명>#<창번호>")
- 창은 겹치지 않게 자른다(같은 통화의 창이 분할에 걸치지 않도록 prepare_data.py 가 통화 단위로 나눈다).
- 통화 앞부분(인사·확인)은 사기 내용이 아닐 수 있으나 통화 단위 라벨을 그대로 쓴다.
"""
import json, sys
from pathlib import Path

D = Path(__file__).resolve().parent
CHUNK = 200


def main():
    files = sorted(Path(sys.argv[1]).glob("*.txt"))
    n = 0
    with open(D / "derived" / "voice_transcripts.jsonl", "w", encoding="utf-8") as f:
        for fp in files:
            text = " ".join(fp.read_text(encoding="utf-8").split())
            for k, i in enumerate(range(0, len(text), CHUNK)):
                w = text[i:i + CHUNK]
                if len(w) < CHUNK // 2:
                    continue
                f.write(json.dumps({"text": w, "label": 1, "orig_id": f"{fp.stem}#{k}"}, ensure_ascii=False) + "\n")
                n += 1
    print(f"통화 {len(files)}건 -> 창 {n}개")


if __name__ == "__main__":
    main()
