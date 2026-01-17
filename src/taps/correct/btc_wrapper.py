"""
BTC (ByT5-Korean) 모델 래퍼

everdoubling/byt5-Korean-base 모델을 사용하여 canonicalization 수행

프롬프트 포맷 (implementation_contract_v1.md 준수):
- STW_CANON: 문장 전체 canonicalization
- STW_SPAN: 스팬 중심 리라이트
- STW_URL: URL/도메인 전용 (자동 확정 금지)
"""

from typing import List, Literal, Optional

from .models import Candidate

TaskType = Literal["STW_CANON", "STW_SPAN", "STW_URL"]


class BTCWrapper:
    """
    BTC 모델 래퍼 (lazy loading)

    사용법:
        btc = BTCWrapper()
        candidates = btc.generate(
            task="STW_SPAN",
            left="인증번호가 ",
            span="일이삼사",
            right="야",
            k=5
        )
    """

    DEFAULT_MODEL_NAME = "everdoubling/byt5-Korean-base"

    def __init__(
        self,
        model_name: Optional[str] = None,
        device: str = "auto",
    ):
        """
        Args:
            model_name: HuggingFace 모델명 (기본: everdoubling/byt5-Korean-base)
            device: 디바이스 (auto/cuda/cpu)
        """
        self.model_name = model_name or self.DEFAULT_MODEL_NAME
        self._device_setting = device
        self._model = None
        self._tokenizer = None
        self._device = None

    @property
    def model(self):
        """모델 lazy loading"""
        if self._model is None:
            self._load_model()
        return self._model

    @property
    def tokenizer(self):
        """토크나이저 lazy loading"""
        if self._tokenizer is None:
            self._load_model()
        return self._tokenizer

    @property
    def device(self) -> str:
        """실제 디바이스"""
        if self._device is None:
            self._load_model()
        return self._device

    def _load_model(self) -> None:
        """모델 및 토크나이저 로드"""
        from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
        import torch

        print(f"BTC 모델 로드 중: {self.model_name}")

        # 디바이스 결정
        if self._device_setting == "auto":
            self._device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self._device = self._device_setting

        # 토크나이저 로드
        self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)

        # 모델 로드
        self._model = AutoModelForSeq2SeqLM.from_pretrained(self.model_name)
        self._model.to(self._device)
        self._model.eval()

        print(f"BTC 모델 로드 완료 (device={self._device})")

    def generate(
        self,
        task: TaskType,
        left: str,
        span: str,
        right: str,
        k: int = 5,
        max_length: int = 128,
    ) -> List[Candidate]:
        """
        BTC 모델로 후보 생성

        Args:
            task: STW_CANON / STW_SPAN / STW_URL
            left: 왼쪽 컨텍스트 (STW_CANON일 경우 빈 문자열)
            span: 대상 스팬 (STW_CANON일 경우 전체 문장)
            right: 오른쪽 컨텍스트 (STW_CANON일 경우 빈 문자열)
            k: 생성할 후보 수
            max_length: 최대 출력 길이

        Returns:
            List[Candidate]: 점수 내림차순 정렬된 후보 리스트
        """
        import torch

        # 프롬프트 생성
        prompt = self._format_prompt(task, left, span, right)

        # 토크나이즈
        inputs = self.tokenizer(
            prompt,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=512,
        ).to(self.device)

        # 생성
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_length=max_length,
                num_beams=max(k, 4),  # beam 수는 최소 4개
                num_return_sequences=k,
                return_dict_in_generate=True,
                output_scores=True,
                early_stopping=True,
            )

        # 후보 디코딩
        candidates = []
        sequences = outputs.sequences

        for i, seq in enumerate(sequences):
            text = self.tokenizer.decode(seq, skip_special_tokens=True).strip()
            score = self._compute_score(outputs, i, len(sequences))
            candidates.append(Candidate(text=text, score=score))

        # 점수 내림차순 정렬 + 중복 제거
        seen = set()
        unique_candidates = []
        for c in sorted(candidates, key=lambda x: x.score, reverse=True):
            if c.text not in seen:
                seen.add(c.text)
                unique_candidates.append(c)

        return unique_candidates

    def _format_prompt(
        self,
        task: TaskType,
        left: str,
        span: str,
        right: str,
    ) -> str:
        """
        BTC 프롬프트 포맷 (implementation_contract_v1.md 준수)

        STW_CANON:
            <STW_CANON>
            {text_raw}
            </STW_CANON>

        STW_SPAN:
            <STW_SPAN>
            LEFT: {left_context}
            SPAN: ⟦{raw_span}⟧
            RIGHT: {right_context}
            </STW_SPAN>

        STW_URL:
            <STW_URL>
            LEFT: {left_context}
            SPAN: ⟦{raw_span}⟧
            RIGHT: {right_context}
            </STW_URL>
        """
        if task == "STW_CANON":
            return f"<STW_CANON>\n{span}\n</STW_CANON>"
        elif task == "STW_SPAN":
            return f"<STW_SPAN>\nLEFT: {left}\nSPAN: ⟦{span}⟧\nRIGHT: {right}\n</STW_SPAN>"
        elif task == "STW_URL":
            return f"<STW_URL>\nLEFT: {left}\nSPAN: ⟦{span}⟧\nRIGHT: {right}\n</STW_URL>"
        else:
            raise ValueError(f"Unknown task: {task}")

    def _compute_score(self, outputs, seq_idx: int, total_seqs: int) -> float:
        """
        시퀀스 점수 계산

        sequences_scores가 있으면 사용, 없으면 순위 기반 fallback
        """
        # beam search는 sequences_scores 제공
        if hasattr(outputs, "sequences_scores") and outputs.sequences_scores is not None:
            return float(outputs.sequences_scores[seq_idx])

        # fallback: 순위 기반 (1등이 가장 높음)
        return 1.0 - (seq_idx / max(total_seqs, 1))


# =============================================================================
# 편의 함수
# =============================================================================

def btc_generate_candidates(
    task: TaskType,
    left: str,
    span: str,
    right: str,
    k: int = 5,
    model_name: Optional[str] = None,
    _wrapper: Optional[BTCWrapper] = None,
) -> List[Candidate]:
    """
    BTC 후보 생성 함수 (implementation_contract_v1.md 시그니처)

    전역 wrapper를 재사용하여 모델 로드 오버헤드 최소화

    Args:
        task: STW_CANON / STW_SPAN / STW_URL
        left: 왼쪽 컨텍스트
        span: 대상 스팬
        right: 오른쪽 컨텍스트
        k: 후보 수
        model_name: 모델명 (기본: everdoubling/byt5-Korean-base)
        _wrapper: 기존 wrapper 재사용 (내부용)

    Returns:
        List[Candidate]: 후보 리스트
    """
    if _wrapper is not None:
        wrapper = _wrapper
    else:
        wrapper = BTCWrapper(model_name=model_name)

    return wrapper.generate(task, left, span, right, k)


# =============================================================================
# 테스트용
# =============================================================================

if __name__ == "__main__":
    print("BTC Wrapper 테스트")
    print("=" * 50)

    # 테스트 케이스
    test_cases = [
        {
            "task": "STW_SPAN",
            "left": "인증번호가 ",
            "span": "일이삼사",
            "right": "야",
        },
        {
            "task": "STW_CANON",
            "left": "",
            "span": "오늘 회의는 삼시에 시작합니다",
            "right": "",
        },
        {
            "task": "STW_URL",
            "left": "주소는 ",
            "span": "더블유더블유더블유 점 네이버 점 컴",
            "right": "이야",
        },
    ]

    btc = BTCWrapper()

    for tc in test_cases:
        print(f"\n태스크: {tc['task']}")
        print(f"  입력: left='{tc['left']}' span='{tc['span']}' right='{tc['right']}'")

        prompt = btc._format_prompt(tc["task"], tc["left"], tc["span"], tc["right"])
        print(f"  프롬프트:\n{prompt}")

        # 실제 생성은 모델 로드 필요
        # candidates = btc.generate(tc["task"], tc["left"], tc["span"], tc["right"], k=3)
        # for c in candidates:
        #     print(f"    후보: '{c.text}' (score={c.score:.4f})")
