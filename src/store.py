# -*- coding: utf-8 -*-
"""
store.py — 런타임 상태 저장소

  - 감사증적(Audit Trail): 모든 질의·응답·검토·승인 이력을 기록 (기능 6)
  - 검토 큐(Review Queue): 고위험 사안을 준법감시인 승인 대상으로 관리 (기능 5)

MVP 단계에서는 메모리 + JSONL 파일에 저장한다.
실서비스에서는 감사 로그 DB / 워크플로 시스템으로 교체한다.
"""
import json
import os
import itertools
from datetime import datetime

_BASE = os.path.dirname(os.path.abspath(__file__))
_AUDIT_FILE = os.path.join(_BASE, "audit_log.jsonl")

# 메모리 상태
_AUDIT = []          # 감사증적 이력
_REVIEW_QUEUE = []    # 준법감시인 검토 큐
_id_seq = itertools.count(1)


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# 감사증적 (Audit Trail)
# ---------------------------------------------------------------------------
def record(action: str, user: str, detail: dict):
    """감사 이벤트를 기록한다."""
    event = {
        "id": next(_id_seq),
        "time": _now(),
        "action": action,      # QUERY / COPY_REVIEW / CHECKLIST / ROUTE / APPROVE / REJECT
        "user": user,
        "detail": detail,
    }
    _AUDIT.append(event)
    # 파일에도 append (감사 대응 자료)
    try:
        with open(_AUDIT_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except OSError:
        pass  # 파일 기록 실패해도 서비스는 계속
    return event


def audit_trail(limit: int = 100):
    """최근 감사 이력을 최신순으로 반환."""
    return list(reversed(_AUDIT[-limit:]))


# ---------------------------------------------------------------------------
# 준법감시인 검토 큐 (Human-in-the-loop)
# ---------------------------------------------------------------------------
def enqueue_review(kind: str, user: str, content: str, ai_result: dict):
    """고위험 사안을 검토 큐에 등록한다."""
    item = {
        "id": next(_id_seq),
        "time": _now(),
        "kind": kind,             # QUERY / COPY_REVIEW
        "user": user,
        "content": content,
        "risk": ai_result.get("risk", {}),
        "ai_result": ai_result,
        "status": "대기",          # 대기 / 승인 / 반려
        "reviewer": None,
        "comment": None,
        "decided_at": None,
    }
    _REVIEW_QUEUE.append(item)
    record("ROUTE", user, {"queue_id": item["id"], "kind": kind,
                            "risk_level": item["risk"].get("level")})
    return item


def review_queue(status: str = None):
    if status:
        return [q for q in _REVIEW_QUEUE if q["status"] == status]
    return list(_REVIEW_QUEUE)


def decide_review(queue_id: int, decision: str, reviewer: str, comment: str = ""):
    """준법감시인이 검토 큐 항목을 승인/반려한다."""
    for item in _REVIEW_QUEUE:
        if item["id"] == queue_id:
            if item["status"] != "대기":
                return {"ok": False, "error": "이미 처리된 항목입니다."}
            item["status"] = decision           # 승인 / 반려
            item["reviewer"] = reviewer
            item["comment"] = comment
            item["decided_at"] = _now()
            record("APPROVE" if decision == "승인" else "REJECT", reviewer,
                   {"queue_id": queue_id, "comment": comment})
            return {"ok": True, "item": item}
    return {"ok": False, "error": "해당 항목을 찾을 수 없습니다."}
