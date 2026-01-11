# 프로젝트 진행 상황

## 현재 상태 (Current Status)

### 사전 작업 (Preliminary Work)
본격적인 연구 참여 시작 전, 프로젝트 이해를 위한 탐색적 작업을 수행했습니다.

**완료한 작업**
- Normalizer v0.6.4 임시 구현
  - 한국어 텍스트 정규화 규칙 기반 엔진 (regex + Kiwi)
  - 숫자, 영문, 기호, 복합어 띄어쓰기 등 처리
  - 위치: [src/taps/normalizer.py](../src/taps/normalizer.py)
- Whisper 모델을 이용한 ASR + 정규화 파이프라인 테스트
  - 테스트 노트북: [docs/pre_test.ipynb](./pre_test.ipynb)
  - TAPS 데이터셋 일부 샘플로 end-to-end 흐름 확인

**목적:**
- 프로젝트 도메인(한국어 음성 데이터 정규화) 이해
- 기술 스택 및 데이터셋 구조 파악
- 향후 체계적인 작업을 위한 기반 마련

---

## 로드맵 진행 상황

본격적인 연구 참여를 시작하면서 [roadmap.md](https://example.com/roadmap.md)의 3.1부터 체계적으로 진행할 예정입니다.

### 3.1 라벨링 자동화 워크플로우 조사
- [x] 기존 워크플로우 조사 (ASR 중심, Forced Alignment, 하이브리드 비교)
- [x] 베이스 워크플로우 선정 (하이브리드 접근: ASR + 트리아지 + 검수 + 정규화)
- [x] **ASR 모델 벤치마크 수행** (2026-01-06)
  - TAPS Test split(~1,000 samples) 대상 CER 평가
  - Whisper Large-v3 (beam=5): **6.71% CER** (최우수)
  - 다른 후보들: Whisper fine-tuned (10.47%), Wav2Vec2 계열 (20%+)
  - 최종 선정: `Systran/faster-whisper-large-v3` (beam=5, language="ko")
- [x] 한국어 도메인 적용 방법 결정 (결정론적 규칙 기반, 모듈화, 보수적 정규화)
- [x] 워크플로우 결정 문서 작성 ([docs/3.1_labeling_workflow_survey.md](./3.1_labeling_workflow_survey.md))

### 3.2 한국어 도메인 조사
- [x] 한국어 특성 조사 (숫자, 알파벳, 복합명사, 1음절 명사)
- [x] 정규화 규칙 정의
- [x] **Kornormalizer 모듈 구현** (진행 중, 2026-01-12)
  - 저장소: [LetsGoKDH/Kornormalizer](https://github.com/LetsGoKDH/Kornormalizer)
  - 구현: NumberToKorean, AlphabetToKorean, CompoundNounSplitter
  - 사전: 152,000+ 항목 (국립국어원 + 법제처)
- [x] 도메인 조사 문서 작성 ([docs/3.2_korean_domain_analysis.md](./3.2_korean_domain_analysis.md))

### 3.3 라벨링 자동화 워크플로우 구성
- [ ] 워크플로우 설계
- [ ] 도구 선정

### 3.4 라벨링 자동화 워크플로우 구현
- [ ] 워크플로우 구현
- [ ] 통합 테스트

### 3.5 검증 시스템 구현 및 검증
- [ ] 검증 시스템 구현
- [ ] 엣지케이스 테스트

### 3.6 최종 검증
- [ ] 전체 시스템 검증
- [ ] 성능 평가

### 3.7 워크플로우 일반화 (Ablation Study)
- [ ] KsponSpeech 적용
- [ ] Zeroth Korean Speech 적용
- [ ] 정확도 측정

### 3.8 한국어 CER 평가 시스템
- [ ] nlptutti 분석
- [ ] 한국어 정규화 고려한 평가 시스템 구축

---

## 코드베이스 관리 상태

### 5.1 Git Repository 구성
- ✅ Repository 생성 및 초기 구성
- ✅ .gitignore 설정 (대용량 데이터 제외)
- ✅ 기본 프로젝트 구조 구성

### 5.2 인코드 문서화
- [ ] Google Style Docstring 작성 (진행 예정)

### 5.3 프로젝트 수준 문서화
- ✅ README.md - 프로젝트 개요, 설치/실행 방법
- ✅ CHANGELOG.md - git-cliff 자동 생성
- ✅ CLAUDE.md - 프로젝트 구조 및 quickstart
- ✅ docs/ - 문서 디렉토리 구성
- ✅ docs/progress.md - 진행 상황 추적 (현재 문서)

---

## 다음 단계 (Next Steps)

1. **Kornormalizer 완성**: 시간/날짜 세부 규칙, 고유어/한자어 수사 문맥 판단 로직 구현
2. **TAPS 프로젝트 통합**: Kornormalizer를 src/taps/normalizer.py에 통합 또는 의존성으로 추가
3. **라벨 스키마 정의**: sample_id 기준 필드 정의 (`text_raw`, `text_verified`, `text_normalized`, 트리아지 메타데이터)
4. **로드맵 3.3 시작**: 라벨링 자동화 워크플로우 설계

---

*최종 업데이트: 2026-01-12*
