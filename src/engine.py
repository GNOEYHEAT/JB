# -*- coding: utf-8 -*-
"""
engine.py — Compliance AI 코어 엔진

MVP 단계에서는 외부 LLM/벡터DB 없이 동작하도록,
  - RAG 검색  -> 키워드 기반 검색(_search)
  - 답변 생성 -> 검색 근거 기반 추출·요약(_compose_answer)
  - Guardrail -> 규칙 기반 리스크 스코어링(assess_risk)
으로 구현한다.

실제 서비스로 확장 시 아래 함수만 교체하면 된다:
  _search()        -> 임베딩 벡터 검색(RAG)
  _compose_answer()-> 금융특화 LLM 호출(sLLM/상용 LLM 하이브리드)
"""
import re
from data import (
    REGULATIONS, AD_RULES, CHECKLISTS, REGULATORY_UPDATES, HIGH_RISK_TERMS,
)

# 고위험 판정 임계값 (이 점수 이상이면 준법감시인 검토 라우팅)
RISK_THRESHOLD_HIGH = 70
RISK_THRESHOLD_MID = 40


def _tokenize(text: str):
    """간단 토크나이저: 한글/영문/숫자 단위로 분리하여 소문자화."""
    return [t.lower() for t in re.findall(r"[가-힣A-Za-z0-9]+", text or "")]


# ---------------------------------------------------------------------------
# [기능 1] 자연어 법규·내부규정 질의응답 (RAG)
# ---------------------------------------------------------------------------
def _search(query: str, top_k: int = 3):
    """키워드 기반 규정 검색. (실서비스: 임베딩 벡터 검색으로 교체)"""
    tokens = set(_tokenize(query))
    scored = []
    for reg in REGULATIONS:
        score = 0
        # 등록 키워드 매칭(가중치 2) + 본문/제목 토큰 매칭(가중치 1)
        for kw in reg["keywords"]:
            if kw.lower() in query.lower():
                score += 2
        body_tokens = set(_tokenize(reg["title"] + " " + reg["content"] + " " + reg["category"]))
        score += len(tokens & body_tokens)
        if score > 0:
            scored.append((score, reg))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:top_k]


def _compose_answer(query: str, hits):
    """검색 근거를 바탕으로 답변 생성. (실서비스: LLM 호출로 교체)"""
    if not hits:
        return (
            "관련 규정을 지식베이스에서 찾지 못했습니다. 준법감시부서에 직접 문의하시기 바랍니다."
        )
    lead = hits[0][1]
    lines = [f"질의하신 내용은 「{lead['category']}」 관련 사항으로 판단됩니다.", ""]
    lines.append("[핵심 근거]")
    for _, reg in hits:
        lines.append(f"· {reg['source']} — {reg['title']}")
        lines.append(f"  {reg['content']}")
    lines.append("")
    lines.append("※ 본 답변은 참고용이며, 구체적 사안은 근거 조항 원문과 준법감시인 검토를 확인하시기 바랍니다.")
    return "\n".join(lines)


def answer_query(query: str):
    """질의응답 통합 처리: 검색 -> 답변 생성 -> 리스크 판정 -> 라우팅 결정."""
    hits = _search(query)
    answer = _compose_answer(query, hits)
    sources = [
        {"source": reg["source"], "title": reg["title"], "category": reg["category"], "score": score}
        for score, reg in hits
    ]
    # 검색 신뢰도(0~1): 최고 점수를 정규화
    confidence = min(1.0, (hits[0][0] / 8.0)) if hits else 0.0
    risk = assess_risk(query + " " + answer, matched=len(hits), confidence=confidence)
    return {
        "answer": answer,
        "sources": sources,
        "confidence": round(confidence, 2),
        "risk": risk,
    }


# ---------------------------------------------------------------------------
# [기능 2] 광고·상품 문구 사전검토
# ---------------------------------------------------------------------------
def review_copy(text: str):
    """광고/상품 문구 위반 소지 탐지 + 수정안 제안."""
    findings = []
    lower = text.lower()
    for rule in AD_RULES:
        hit = False
        matched = None
        if rule["type"] == "CONTAINS":
            for trg in rule["triggers"]:
                if trg.lower() in lower:
                    hit, matched = True, trg
                    break
        elif rule["type"] == "MISSING":
            has_context = any(c.lower() in lower for c in rule["context"])
            has_required = any(r.lower() in lower for r in rule["required"])
            if has_context and not has_required:
                hit, matched = True, "(필수 표기 누락)"
        if hit:
            findings.append({
                "rule_id": rule["id"],
                "law": rule["law"],
                "severity": rule["severity"],
                "matched": matched,
                "message": rule["message"],
                "suggestion": rule["suggestion"],
            })

    risk = assess_risk(text, matched=1, confidence=1.0, extra_findings=findings)
    verdict = "위반 소지 없음 (자동 검토 기준)" if not findings else f"{len(findings)}건의 위반 소지 발견"
    return {"findings": findings, "verdict": verdict, "risk": risk}


# ---------------------------------------------------------------------------
# [기능 3] 준법 체크리스트 자동생성
# ---------------------------------------------------------------------------
def generate_checklist(transaction_type: str):
    items = CHECKLISTS.get(transaction_type)
    if items is None:
        return {"transaction_type": transaction_type, "available": list(CHECKLISTS.keys()), "items": []}
    return {
        "transaction_type": transaction_type,
        "available": list(CHECKLISTS.keys()),
        "items": [dict(it, done=False) for it in items],
    }


# ---------------------------------------------------------------------------
# [기능 4] 규제 변경 모니터링
# ---------------------------------------------------------------------------
def get_regulatory_updates(dept: str = None):
    if dept:
        return [u for u in REGULATORY_UPDATES if dept in u["target_depts"]]
    return list(REGULATORY_UPDATES)


# ---------------------------------------------------------------------------
# [Guardrail] 리스크 스코어링 (기능 5의 라우팅 판단 근거)
# ---------------------------------------------------------------------------
def assess_risk(text: str, matched: int = 0, confidence: float = 1.0, extra_findings=None):
    """텍스트/문맥 기반 리스크 점수(0~100)와 등급·사유를 산출한다."""
    score = 15  # 기본 점수
    reasons = []

    for term, weight in HIGH_RISK_TERMS.items():
        if term.lower() in (text or "").lower():
            score += weight
            reasons.append(f"고위험 용어 '{term}' 포함 (+{weight})")

    # 검색 근거를 찾지 못했거나 신뢰도가 낮으면 불확실성 리스크 가산
    if matched == 0:
        score += 25
        reasons.append("관련 규정 미검색 — 답변 신뢰도 낮음 (+25)")
    elif confidence < 0.4:
        score += 15
        reasons.append("검색 신뢰도 낮음 (+15)")

    # 광고 문구 검토에서 발견된 위반 심각도 반영
    if extra_findings:
        for f in extra_findings:
            add = 30 if f["severity"] == "high" else 15
            score += add
            reasons.append(f"위반 소지({f['rule_id']}, {f['severity']}) (+{add})")

    score = min(score, 100)
    if score >= RISK_THRESHOLD_HIGH:
        level = "고위험"
    elif score >= RISK_THRESHOLD_MID:
        level = "중위험"
    else:
        level = "저위험"

    return {
        "score": score,
        "level": level,
        "reasons": reasons or ["특이사항 없음"],
        "route_to_officer": level == "고위험",  # 고위험 -> 준법감시인 검토 라우팅
    }
