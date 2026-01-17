#!/usr/bin/env python3
"""
ASR Transcription Script for TAPS Dataset (1000 samples)

HuggingFace 데이터셋에서 acoustic 오디오를 로드하고
faster-whisper로 전사하여 JSONL 파일로 저장합니다.

Usage:
    python -m taps.asr.asr_transcribe_1000 --out_jsonl data/outputs/asr_results.jsonl

Colab Example:
    !pip install faster-whisper datasets
    !python -m taps.asr.asr_transcribe_1000 --out_jsonl /content/asr_results.jsonl --max_items 100
"""

import argparse
import json
import os
from pathlib import Path
from typing import Optional, Set, Dict, Any, List

import re

import numpy as np


def compute_triage_features(text: str) -> Dict[str, Any]:
    """
    트리아지용 텍스트 피처를 계산합니다.

    Returns:
        dict with has_digit, latin_count, unit_like_count
    """
    # 숫자 포함 여부
    has_digit = bool(re.search(r'\d', text))

    # 라틴 알파벳 개수 (한글 사이에 있는 영문은 위험 신호)
    latin_count = len(re.findall(r'[a-zA-Z]', text))

    # 단위 유사 패턴 (cm, kg, ml, m, km, g, L, cc, % 등)
    unit_patterns = [
        r'\d+\s*(?:cm|mm|m|km|kg|g|mg|ml|L|cc|%|도|원|개|명|번|회|시|분|초|년|월|일)',
        r'(?:제|약|총|각)\s*\d+',
    ]
    unit_like_count = sum(
        len(re.findall(pattern, text, re.IGNORECASE))
        for pattern in unit_patterns
    )

    return {
        "has_digit": has_digit,
        "latin_count": latin_count,
        "unit_like_count": unit_like_count,
    }


def find_acoustic_field(dataset) -> str:
    """데이터셋에서 acoustic 오디오 필드를 찾습니다."""
    features = dataset.features

    # 가능한 필드명들
    candidates = [
        "Acoustic_Microphone",
        "acoustic_microphone",
        "Acoustic",
        "acoustic",
        "audio",
    ]

    for name in candidates:
        if name in features:
            return name

    # 모든 필드 중 'acoustic'이 포함된 것 찾기
    for name in features:
        if "acoustic" in name.lower():
            return name

    # Audio 타입인 필드 찾기
    from datasets import Audio
    for name, feat in features.items():
        if isinstance(feat, Audio):
            return name

    raise ValueError(f"Acoustic audio field not found. Available fields: {list(features.keys())}")


def load_done_set(jsonl_path: str) -> Set[str]:
    """이미 처리된 utt_id 집합을 로드합니다."""
    done = set()
    if os.path.exists(jsonl_path):
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        record = json.loads(line)
                        if "utt_id" in record:
                            done.add(record["utt_id"])
                    except json.JSONDecodeError:
                        continue
    return done


def transcribe_audio(
    model,
    audio_array: np.ndarray,
    sample_rate: int,
    language: str = "ko",
    beam_size: int = 5,
) -> Dict[str, Any]:
    """
    오디오를 전사하고 메타데이터를 반환합니다.

    Returns:
        dict with text_raw, avg_logprob, avg_no_speech_prob, compression_ratio,
        language, duration, temperature_fallback
    """
    # 샘플레이트가 16000이 아니면 리샘플링 필요
    if sample_rate != 16000:
        try:
            import librosa
            audio_array = librosa.resample(audio_array, orig_sr=sample_rate, target_sr=16000)
        except ImportError:
            # librosa 없으면 scipy 사용
            from scipy import signal
            num_samples = int(len(audio_array) * 16000 / sample_rate)
            audio_array = signal.resample(audio_array, num_samples)

    # Whisper 전사
    segments, info = model.transcribe(
        audio_array,
        language=language,
        beam_size=beam_size,
        temperature=[0.0, 0.2, 0.4],
        vad_filter=True,
    )

    segments = list(segments)

    if len(segments) == 0:
        return {
            "text_raw": "",
            "avg_logprob": -1.0,
            "avg_no_speech_prob": 1.0,
            "compression_ratio": 0.0,
            "language": language,
            "duration": info.duration,
            "temperature_fallback": False,
        }

    # 텍스트 합치기
    text_raw = "".join(seg.text for seg in segments).strip()

    # 메트릭 계산 (duration 가중 평균)
    total_duration = sum(seg.end - seg.start for seg in segments)

    if total_duration > 0:
        # duration 가중 평균
        avg_logprob = sum(
            seg.avg_logprob * (seg.end - seg.start) for seg in segments
        ) / total_duration
        avg_no_speech_prob = sum(
            seg.no_speech_prob * (seg.end - seg.start) for seg in segments
        ) / total_duration
        compression_ratio = sum(
            seg.compression_ratio * (seg.end - seg.start) for seg in segments
        ) / total_duration
    else:
        # 단순 평균 (fallback)
        avg_logprob = sum(seg.avg_logprob for seg in segments) / len(segments)
        avg_no_speech_prob = sum(seg.no_speech_prob for seg in segments) / len(segments)
        compression_ratio = sum(seg.compression_ratio for seg in segments) / len(segments)

    # Temperature fallback 감지: 0.0이 아닌 temperature 사용 시 fallback 발생
    # faster-whisper segment에는 temperature 속성이 있음
    temperature_fallback = any(
        getattr(seg, "temperature", 0.0) > 0.0 for seg in segments
    )

    return {
        "text_raw": text_raw,
        "avg_logprob": avg_logprob,
        "avg_no_speech_prob": avg_no_speech_prob,
        "compression_ratio": compression_ratio,
        "language": info.language or language,
        "duration": info.duration,
        "temperature_fallback": temperature_fallback,
    }


def main():
    parser = argparse.ArgumentParser(
        description="ASR transcription for TAPS dataset (1000 samples)"
    )
    parser.add_argument(
        "--out_jsonl",
        type=str,
        default="data/outputs/asr_results.jsonl",
        help="Output JSONL file path",
    )
    parser.add_argument(
        "--model_size",
        type=str,
        default="large-v3",
        help="Whisper model size (default: large-v3)",
    )
    parser.add_argument(
        "--beam_size",
        type=int,
        default=5,
        help="Beam size for decoding (default: 5)",
    )
    parser.add_argument(
        "--max_items",
        type=int,
        default=None,
        help="Maximum number of items to process (default: all)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        default=True,
        help="Resume from existing output file (default: True)",
    )
    parser.add_argument(
        "--no-resume",
        action="store_false",
        dest="resume",
        help="Do not resume, overwrite existing output file",
    )
    parser.add_argument(
        "--flush_every",
        type=int,
        default=10,
        help="Flush to disk every N records (default: 10)",
    )
    parser.add_argument(
        "--device",
        type=str,
        default="auto",
        help="Device: 'cuda', 'cpu', or 'auto' (default: auto)",
    )

    args = parser.parse_args()

    # 출력 디렉토리 생성
    out_path = Path(args.out_jsonl)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 이미 처리된 항목 로드
    done_set: Set[str] = set()
    if args.resume and out_path.exists():
        done_set = load_done_set(str(out_path))
        print(f"Resuming: {len(done_set)} items already processed")

    # 데이터셋 로드
    print("Loading dataset...")
    from datasets import load_dataset

    dataset = load_dataset(
        "yskim3271/Throat_and_Acoustic_Pairing_Speech_Dataset",
        "with_normalized_text",
        split="test",
    )

    # Acoustic 필드 찾기
    acoustic_field = find_acoustic_field(dataset)
    print(f"Found acoustic field: {acoustic_field}")

    # 처리할 항목 수 결정
    total_items = len(dataset)
    if args.max_items:
        total_items = min(total_items, args.max_items)
    print(f"Total items to process: {total_items}")

    # Whisper 모델 로드
    print(f"Loading Whisper model: {args.model_size}")
    from faster_whisper import WhisperModel

    # Device 설정
    if args.device == "auto":
        try:
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            device = "cpu"
    else:
        device = args.device

    compute_type = "float16" if device == "cuda" else "int8"
    print(f"Using device: {device}, compute_type: {compute_type}")

    model = WhisperModel(
        args.model_size,
        device=device,
        compute_type=compute_type,
    )
    print("Model loaded!")

    # 전사 시작
    processed = 0
    skipped = 0
    errors = 0
    buffer: List[Dict[str, Any]] = []

    # 출력 파일 열기 (append 모드)
    with open(out_path, "a", encoding="utf-8") as f_out:
        for idx, sample in enumerate(dataset):
            if idx >= total_items:
                break

            # ID 추출
            speaker_id = str(sample.get("speaker_id", sample.get("Speaker_ID", f"S{idx:04d}")))
            sentence_id = str(sample.get("sentence_id", sample.get("Sentence_ID", f"{idx:06d}")))
            utt_id = f"{speaker_id}_{sentence_id}"

            # 이미 처리됨
            if utt_id in done_set:
                skipped += 1
                continue

            # 오디오 추출
            try:
                audio_data = sample[acoustic_field]

                # nested dict 처리 (acoustic_microphone이 dict 안에 있을 수 있음)
                if isinstance(audio_data, dict):
                    if "array" in audio_data:
                        audio_array = np.array(audio_data["array"])
                        sample_rate = audio_data.get("sampling_rate", 16000)
                    elif "acoustic_microphone" in audio_data:
                        audio_array = np.array(audio_data["acoustic_microphone"]["array"])
                        sample_rate = audio_data["acoustic_microphone"].get("sampling_rate", 16000)
                    else:
                        raise ValueError(f"Unknown audio format: {audio_data.keys()}")
                else:
                    audio_array = np.array(audio_data)
                    sample_rate = 16000

            except Exception as e:
                print(f"[{idx}] Error extracting audio for {utt_id}: {e}")
                errors += 1
                continue

            # 전사
            try:
                result = transcribe_audio(
                    model,
                    audio_array,
                    sample_rate,
                    language="ko",
                    beam_size=args.beam_size,
                )
            except Exception as e:
                print(f"[{idx}] Error transcribing {utt_id}: {e}")
                errors += 1
                continue

            # Triage features 계산
            triage_feat = compute_triage_features(result["text_raw"])

            # 레코드 생성
            record = {
                "utt_id": utt_id,
                "speaker_id": speaker_id,
                "sentence_id": sentence_id,
                "audio_source": {
                    "dataset": "yskim3271/Throat_and_Acoustic_Pairing_Speech_Dataset",
                    "split": "test",
                    "field": acoustic_field,
                },
                "text_raw": result["text_raw"],
                "avg_logprob": result["avg_logprob"],
                "avg_no_speech_prob": result["avg_no_speech_prob"],
                "compression_ratio": result["compression_ratio"],
                "temperature_fallback": result["temperature_fallback"],
                "language": result["language"],
                "duration": result["duration"],
                "triage_feat": triage_feat,
            }

            # 버퍼에 추가
            buffer.append(record)
            processed += 1

            # 진행 상황 출력
            if processed % 10 == 0:
                print(f"Processed: {processed}, Skipped: {skipped}, Errors: {errors}")

            # Flush
            if len(buffer) >= args.flush_every:
                for rec in buffer:
                    f_out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                f_out.flush()
                buffer.clear()

        # 남은 버퍼 flush
        if buffer:
            for rec in buffer:
                f_out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f_out.flush()

    print(f"\nDone!")
    print(f"  Processed: {processed}")
    print(f"  Skipped (already done): {skipped}")
    print(f"  Errors: {errors}")
    print(f"  Output: {out_path}")


if __name__ == "__main__":
    main()
