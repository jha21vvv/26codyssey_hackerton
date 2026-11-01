"""판단 AI 모듈. 백엔드는 analyze() 와 transcribe() 두 함수만 쓴다.

    from ai import analyze, transcribe
"""
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from .analyzer import analyze  # noqa: E402
from .privacy import mask_text  # noqa: E402
from .transcribe import transcribe  # noqa: E402

__all__ = ["analyze", "transcribe", "mask_text"]
