# -*- coding: utf-8 -*-
"""
app.py — Compliance AI (준법자문가 AI Agent) API 서버

실행:
    pip install -r requirements.txt
    python app.py
    -> http://127.0.0.1:8000 접속

6대 핵심 기능을 REST API로 제공하고, 단일 HTML UI(index.html)를 서빙한다.
"""
import os
from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel

import engine
import store

app = FastAPI(title="Compliance AI — 준법자문가 AI Agent", version="0.1.0 (MVP)")
_BASE = os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------------------
# 요청 모델
# ---------------------------------------------------------------------------
class QueryReq(BaseModel):
    query: str
    user: str = "영업점직원"


class CopyReq(BaseModel):
    text: str
    user: str = "마케팅담당자"


class DecisionReq(BaseModel):
    queue_id: int
    decision: str            # "승인" | "반려"
    reviewer: str = "준법감시인"
    comment: str = ""


# ---------------------------------------------------------------------------
# 기능 1: 자연어 법규·내부규정 질의응답
# ---------------------------------------------------------------------------
@app.post("/api/query")
def api_query(req: QueryReq):
    result = engine.answer_query(req.query)
    store.record("QUERY", req.user, {"query": req.query,
                                     "risk_level": result["risk"]["level"],
                                     "confidence": result["confidence"]})
    # 고위험 -> 준법감시인 검토 큐로 자동 라우팅 (Human-in-the-loop)
    routed = None
    if result["risk"]["route_to_officer"]:
        routed = store.enqueue_review("QUERY", req.user, req.query, result)
    result["routed_queue_id"] = routed["id"] if routed else None
    return result


# ---------------------------------------------------------------------------
# 기능 2: 광고·상품 문구 사전검토
# ---------------------------------------------------------------------------
@app.post("/api/review-copy")
def api_review_copy(req: CopyReq):
    result = engine.review_copy(req.text)
    store.record("COPY_REVIEW", req.user, {"text": req.text[:200],
                                           "findings": len(result["findings"]),
                                           "risk_level": result["risk"]["level"]})
    routed = None
    if result["risk"]["route_to_officer"]:
        routed = store.enqueue_review("COPY_REVIEW", req.user, req.text, result)
    result["routed_queue_id"] = routed["id"] if routed else None
    return result


# ---------------------------------------------------------------------------
# 기능 3: 준법 체크리스트 자동생성
# ---------------------------------------------------------------------------
@app.get("/api/checklist")
def api_checklist(transaction_type: str = "여신", user: str = "영업점직원"):
    result = engine.generate_checklist(transaction_type)
    store.record("CHECKLIST", user, {"transaction_type": transaction_type,
                                     "items": len(result["items"])})
    return result


# ---------------------------------------------------------------------------
# 기능 4: 규제 변경 모니터링
# ---------------------------------------------------------------------------
@app.get("/api/regulatory-updates")
def api_regulatory_updates(dept: str = None):
    return {"updates": engine.get_regulatory_updates(dept)}


# ---------------------------------------------------------------------------
# 기능 5: 준법감시인 검토 라우팅 (Human-in-the-loop)
# ---------------------------------------------------------------------------
@app.get("/api/review-queue")
def api_review_queue(status: str = None):
    return {"queue": store.review_queue(status)}


@app.post("/api/review-decide")
def api_review_decide(req: DecisionReq):
    return store.decide_review(req.queue_id, req.decision, req.reviewer, req.comment)


# ---------------------------------------------------------------------------
# 기능 6: 감사증적
# ---------------------------------------------------------------------------
@app.get("/api/audit-trail")
def api_audit_trail(limit: int = 100):
    return {"events": store.audit_trail(limit)}


# ---------------------------------------------------------------------------
# UI 서빙
# ---------------------------------------------------------------------------
@app.get("/")
def index():
    return FileResponse(os.path.join(_BASE, "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
