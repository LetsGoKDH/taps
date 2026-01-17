# Update Log

프로젝트 주요 업데이트 내역을 기록합니다.

---

## 2026-01-17: 파이프라인 설계 확정 (v1.1)

### 변경 사항

#### 1. 전체 파이프라인 재설계 (7단계)

기존 4단계 파이프라인(ASR → 트리아지 → 검수 → 정규화)을 7단계로 확장:

| Stage | 이름 | 설명 |
|-------|------|------|
| A | 데이터 입력 | Acoustic audio, speaker_id + sentence_id → utt_id |
| B | ASR | Whisper-large-v3, text_raw + 메타 출력 |
| C | **correct_model** | text_avail (자동확정) + text_check (Issue) 출력 |
| D | 1차 검수 | Excel 기반, user_fix → text_avail_final |
| E | kornormalizer | text_normalized 출력 |
| F | verifier | 2차 검증 (추후 구축), text_fin 출력 |
| G | 학습 루프 | 검수 결과 누적 → BTC/verifier 개선 |

#### 2. correct_model 3레이어 구성 확정

| 레이어 | 역할 | 세부 |
|--------|------|------|
| Span Finder | 신호/규칙 | 숫자/알파벳/URL/OOV 스팬 탐지 (교정 금지) |
| BTC Rewriter | 주력 엔진 | ByT5-Korean, KsponSpeech STW/WTS 파인튜닝 |
| Decision Layer | 정책/가드레일 | 자동확정 vs 검수 결정 |

#### 3. 정책 확정

- **U1** (URL/도메인): 자동확정 금지, 항상 검수
- **N3** (숫자): BTC 확신도 높으면 자동확정 가능
- **E2** (영문/알파벳): 혼종/도메인은 검수
- **OOV**: 어간 기준 조건부 트리거 (조사 붙은 단어 폭증 방지)

#### 4. 관용구 파괴 탐지 추가

- "제 도끼에 제 발등" → "제도기의 재발동" 같은 케이스
- OOV로 못 잡음 (틀린 단어 없음)
- 퍼지 매칭 + avg_logprob 연계로 탐지

#### 5. Excel 검수 워크플로우 확정

- JSON → Excel 변환 (사용자 친화적)
- 스팬 표시: `⟦ ⟧` 마커 사용
- Excel → JSON 역변환 (학습용 + normalizer용)

#### 6. 평가 프로토콜 확정

- Gold: `kornormalizer(text_avail_final)` vs `text_normalized`
- 단어 단위 정확도 우선 (띄어쓰기보다 중요)

### 수정된 파일

- `README.md`: 파이프라인 개요 섹션 추가
- `docs/correct_model_spec_v1.md`: v1.1로 업데이트

### 참조

- 상세 설계: [correct_model_spec_v1.md](./correct_model_spec_v1.md)

---

*이전 업데이트는 [progress.md](./progress.md)를 참조하세요.*
