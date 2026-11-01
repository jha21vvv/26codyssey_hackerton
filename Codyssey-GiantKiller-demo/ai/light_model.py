"""가벼운 1차 모델: 문자 2~3글자 조각(해싱) + 로지스틱 회귀. 폰 안에서도 돈다 (android/.../LightModel.kt).

C안 비교표의 'light' 칸이자, 폰 1차 필터의 "모델 점수" 조건.
- 표준 라이브러리만 사용 (설치 불필요). 학습: scripts/train_light.py
- 파이썬과 Kotlin 이 **같은 문자에 똑같은 점수**를 내야 한다. 바꾸면 둘 다 바꾸고
  tests/test_light_model.py · android 단위 테스트의 고정 예시를 다시 만든다.

글자 다듬기 (양쪽 동일)
  1) 숫자 0-9 → '0'   2) 영문 A-Z → a-z   3) 공백류(스페이스·탭·줄바꿈·\\u00a0·\\u3000) 연속 → 스페이스 하나, 앞뒤 공백 제거
조각: 유니코드 코드포인트 기준 2·3글자 → UTF-8 바이트 → FNV-1a 32비트 → % DIM
점수: sigmoid(bias + scale × Σ q[idx] / √(조각 종류 수)), q = int8 가중치

파일 (little-endian): b"JKLM" | ver u16 | nmin u8 | nmax u8 | dim u32 | scale f32 | bias f32 | gate f32 | cls f32 | q int8×dim
"""
import math
import random
import struct
from pathlib import Path

MAGIC = b"JKLM"
VERSION = 1
DIM = 1 << 16
NGRAMS = (2, 3)
SPACES = {" ", "\t", "\r", "\n", " ", "　"}


def normalize(text: str) -> str:
    out, space = [], False
    for ch in text or "":
        if "0" <= ch <= "9":
            ch = "0"
        elif "A" <= ch <= "Z":
            ch = chr(ord(ch) + 32)
        if ch in SPACES:
            space = True
            continue
        if space and out:
            out.append(" ")
        space = False
        out.append(ch)
    return "".join(out)


def fnv1a(data: bytes) -> int:
    h = 0x811C9DC5
    for b in data:
        h ^= b
        h = (h * 0x01000193) & 0xFFFFFFFF
    return h


def features(text: str, dim: int = DIM, ngrams=NGRAMS) -> list[int]:
    """겹치지 않는 조각 번호 목록 (같은 조각은 한 번만)"""
    t = normalize(text)
    idx = set()
    for n in ngrams:
        for i in range(len(t) - n + 1):
            idx.add(fnv1a(t[i:i + n].encode("utf-8")) % dim)
    return sorted(idx)


def _f32(x: float) -> float:
    """float32 로 저장·읽기한 값과 똑같이 맞춘다 (Kotlin 과 같은 수를 쓰도록)"""
    return struct.unpack("<f", struct.pack("<f", x))[0]


class LightModel:
    def __init__(self, q: bytearray | list[int], scale: float, bias: float, gate: float = 0.2, cls: float = 0.5,
                 dim: int = DIM, ngrams=NGRAMS):
        self.q = [v - 256 if v > 127 else v for v in q] if isinstance(q, (bytes, bytearray)) else list(q)
        self.scale, self.bias = _f32(scale), _f32(bias)
        self.gate, self.cls = _f32(gate), _f32(cls)
        self.dim, self.ngrams = dim, tuple(ngrams)

    def score(self, text: str) -> float:
        idx = features(text, self.dim, self.ngrams)
        if not idx:
            return 1.0 / (1.0 + math.exp(-self.bias))
        s = sum(self.q[i] for i in idx)
        z = self.bias + self.scale * s / math.sqrt(len(idx))
        return 1.0 / (1.0 + math.exp(-z))

    def is_scam(self, text: str) -> bool:
        return self.score(text) >= self.cls

    def passes_gate(self, text: str) -> bool:
        """폰 1차 필터용 낮은 기준 (애매하면 서버로)"""
        return self.score(text) >= self.gate

    # ── 저장·읽기 ──
    def save(self, path: str | Path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        head = MAGIC + struct.pack("<HBBIffff", VERSION, self.ngrams[0], self.ngrams[-1], self.dim,
                                   self.scale, self.bias, self.gate, self.cls)
        path.write_bytes(head + bytes((v + 256) % 256 for v in self.q))

    @classmethod
    def load(cls, path: str | Path) -> "LightModel":
        data = Path(path).read_bytes()
        if data[:4] != MAGIC:
            raise ValueError(f"{path}: 가벼운 모델 파일이 아니에요")
        ver, nmin, nmax, dim, scale, bias, gate, clsf = struct.unpack("<HBBIffff", data[4:28])
        if ver != VERSION:
            raise ValueError(f"{path}: 모델 버전 {ver} (지원 {VERSION})")
        return cls(bytearray(data[28:28 + dim]), scale, bias, gate, clsf, dim, tuple(range(nmin, nmax + 1)))


def train(xs: list[str], ys: list[int], epochs: int = 6, lr: float = 0.5, l2: float = 1e-6, seed: int = 42,
          dim: int = DIM) -> tuple[list[float], float]:
    """SGD 로지스틱 회귀. 위험(1)이 적은 쪽을 무겁게. (가중치, 편향) — 실수 그대로 (저장할 때 int8 로 줄임)"""
    feats = [features(x, dim) for x in xs]
    pos = sum(ys)
    wpos, wneg = len(ys) / (2 * max(pos, 1)), len(ys) / (2 * max(len(ys) - pos, 1))
    w = [0.0] * dim
    b = 0.0
    order = list(range(len(xs)))
    rng = random.Random(seed)
    step = 0
    for ep in range(epochs):
        rng.shuffle(order)
        for k in order:
            idx = feats[k]
            if not idx:
                continue
            v = 1.0 / math.sqrt(len(idx))
            z = b + v * sum(w[i] for i in idx)
            p = 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))
            g = (p - ys[k]) * (wpos if ys[k] else wneg)
            rate = lr / (1 + 1e-5 * step)
            for i in idx:
                w[i] -= rate * (g * v + l2 * w[i])
            b -= rate * g
            step += 1
    return w, b


def quantize(w: list[float], b: float, gate: float = 0.2, cls: float = 0.5) -> LightModel:
    m = max(abs(x) for x in w) or 1.0
    scale = m / 127.0
    q = [max(-127, min(127, round(x / scale))) for x in w]
    return LightModel(q, scale, b, gate, cls, len(w))
