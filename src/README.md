# Compliance AI — 준법자문가 AI Agent (MVP)

JB금융그룹 AX전략부 제안 서비스의 **가장 간단한 실행형 프로토타입**입니다.
기능 명세서 / MVP 제안서의 6대 핵심 기능을 외부 LLM·벡터DB 없이 로컬에서 바로 동작시킵니다.

> ⚠️ MVP 검증용입니다. 답변 생성(LLM)과 검색(RAG)은 규칙·키워드 기반으로 **시뮬레이션**되어 있으며,
> 실제 서비스에서는 `engine.py`의 `_search()`/`_compose_answer()`만 실 LLM·RAG로 교체하면 됩니다.

## 6대 핵심 기능

| # | 기능 | 구현 위치 |
|---|------|-----------|
| ① | 자연어 법규·내부규정 질의응답 (RAG) | `engine.answer_query` |
| ② | 광고·상품 문구 사전검토 | `engine.review_copy` |
| ③ | 준법 체크리스트 자동생성 | `engine.generate_checklist` |
| ④ | 규제 변경 모니터링·알림 | `engine.get_regulatory_updates` |
| ⑤ | 준법감시인 검토 라우팅 (Human-in-the-loop) | `store.enqueue_review` / `decide_review` |
| ⑥ | 감사증적(Audit Trail) 자동 기록 | `store.record` / `audit_trail` |

Guardrail(리스크 스코어링)은 `engine.assess_risk`가 담당하며, **고위험(70점 이상)** 사안은
자동으로 준법감시인 검토 큐(⑤)로 라우팅됩니다.

## 실행 방법

```bash
cd compliance-ai
pip install -r requirements.txt
python app.py
```

브라우저에서 **http://127.0.0.1:8000** 접속 → 상단 탭에서 6개 기능을 확인합니다.

## 데모 시나리오

1. **① 법규 질의응답**: "대출을 조건으로 예금 가입을 권유해도 되나요?" → 꺾기(금소법 제20조) 근거 제시
2. **② 문구 사전검토**: "누구나 무조건 승인! 업계 최저금리, 원금보장 확정수익" → 위반 소지 다수 탐지 → **고위험 → ⑤로 자동 라우팅**
3. **⑤ 준법감시인 검토**: 라우팅된 항목을 승인/반려
4. **⑥ 감사증적**: 위 모든 행위가 자동 기록됨 (`audit_log.jsonl` 파일에도 append)

## 파일 구성

```
compliance-ai/
├─ app.py            # FastAPI 서버 (REST API + UI 서빙)
├─ engine.py         # 코어 엔진 (RAG 검색·답변·문구검토·체크리스트·리스크 스코어링)
├─ store.py          # 감사증적 로그 + 준법감시인 검토 큐 (메모리 + JSONL)
├─ data.py           # 지식베이스 (법령·내부규정·위반규칙·체크리스트·규제피드)
├─ index.html        # 단일 페이지 UI (탭 6개)
├─ requirements.txt
└─ README.md
```

## 실서비스 확장 포인트 (제안서 2·3단계)

- `engine._search`  → 임베딩 기반 벡터 검색(RAG), 내부규정/법령/판례 DB 연동
- `engine._compose_answer` → 금융특화 sLLM + 외부 상용 LLM 하이브리드 호출
- `data.py` 정적 데이터 → 실 규정 DB / 규제기관 공시 크롤링 구독
- `store.py` 메모리·JSONL → 감사 로그 DB / 워크플로 승인 시스템
- 폐쇄망·온프레미스 배포, 민감정보 마스킹 Guardrail 강화
