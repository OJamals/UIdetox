from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, HTTPException

from backend import database
from backend.extended.schemas import (
    ForecastResponse,
    OpportunityDetailResponse,
    OpportunityResponse,
    OpportunityUpdate,
    RevenueTargetResponse,
    SlaPolicyResponse,
    SupportAssignment,
    SupportCaseDetailResponse,
    SupportCaseResponse,
    SupportMacroResponse,
)

router = APIRouter(tags=["extended-revenue-support"])


def _integer_text(value: str) -> int:
    match = re.search(r"[\d,.]+", value)
    if not match:
        return 0
    return round(float(match.group(0).replace(",", "")))


def opportunity_payload(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item["id"],
        "name": item["deal_name"],
        "accountName": item["account_label"],
        "stage": item["stage_code"],
        "amountCents": _integer_text(item["amount_text"]) * (
            100 if "$" in item["amount_text"] or "USD" in item["amount_text"] else 1
        ),
        "probability": item["probability_percent"],
        "owner": item["owner_ref"],
        "closeAt": item["expected_close_date"],
        "nextStep": item["next_action_blob"],
    }


def support_case_payload(item: dict[str, Any]) -> dict[str, Any]:
    priority = {
        "urgent-purple": "urgent",
        "highish": "high",
        "normal": "normal",
    }.get(item["priority_code"], "low")
    status = {
        "OPEN_NOW": "open",
        "waiting_customer_or_us": "waiting",
        "resolved_maybe": "resolved",
    }.get(item["state_code"], "open")
    return {
        "id": item["id"],
        "title": item["subject_line"],
        "accountName": item["account_label"],
        "priority": priority,
        "status": status,
        "assignee": item["assignee_ref"],
        "openedAt": item["opened_at"],
        "lastReplyAt": item["last_reply_at"],
        "slaMinutes": _integer_text(item["sla_minutes_text"]),
    }


@router.get("/api/revenue/opportunities", response_model=list[OpportunityResponse])
def list_opportunities() -> list[dict[str, Any]]:
    return [
        opportunity_payload(item)
        for item in database.rows("SELECT * FROM opportunities ORDER BY amount_text DESC")
    ]


@router.get(
    "/api/revenue/opportunities/{opportunity_id}",
    response_model=OpportunityDetailResponse,
)
def get_opportunity(opportunity_id: int) -> dict[str, Any]:
    item = database.row("SELECT * FROM opportunities WHERE id = ?", (opportunity_id,))
    if not item:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    payload = opportunity_payload(item)
    payload["history"] = [
        {
            "id": history["id"],
            "action": history["action_code"],
            "detail": history["detail_blob"],
            "actor": history["actor_ref"],
            "createdAt": history["happened_at"],
        }
        for history in database.rows(
            """
            SELECT * FROM opportunity_history
            WHERE opportunity_id = ?
            ORDER BY happened_at DESC
            """,
            (opportunity_id,),
        )
    ]
    return payload


@router.patch(
    "/api/revenue/opportunities/{opportunity_id}",
    response_model=OpportunityResponse,
)
def update_opportunity(
    opportunity_id: int, payload: OpportunityUpdate
) -> dict[str, Any]:
    existing = database.row(
        "SELECT * FROM opportunities WHERE id = ?", (opportunity_id,)
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    database.execute(
        """
        UPDATE opportunities
        SET stage_code = ?, probability_percent = ?
        WHERE id = ?
        """,
        (payload.stage, payload.probability, opportunity_id),
    )
    database.execute(
        """
        INSERT INTO opportunity_history
            (opportunity_id, action_code, detail_blob, actor_ref, happened_at)
        VALUES (?, 'stage_changed', ?, 'Fixture Operator', CURRENT_TIMESTAMP)
        """,
        (
            opportunity_id,
            f"Moved to {payload.stage} with {payload.probability}% probability",
        ),
    )
    return opportunity_payload(
        {
            **existing,
            "stage_code": payload.stage,
            "probability_percent": payload.probability,
        }
    )


@router.get("/api/revenue/forecast", response_model=ForecastResponse)
def get_revenue_forecast() -> dict[str, Any]:
    opportunities = list_opportunities()
    pipeline = sum(item["amountCents"] for item in opportunities)
    weighted = sum(
        item["amountCents"] * item["probability"] // 100 for item in opportunities
    )
    return {
        "quarter": "FY26 Q3",
        "pipelineCents": pipeline,
        "weightedCents": weighted,
        "commitCents": sum(
            item["amountCents"]
            for item in opportunities
            if item["stage"] in {"proposal", "negotiation"}
        ),
        "atRiskCents": sum(
            item["amountCents"]
            for item in opportunities
            if item["probability"] < 50
        ),
    }


@router.get("/api/revenue/targets", response_model=list[RevenueTargetResponse])
def list_revenue_targets() -> list[dict[str, Any]]:
    return [
        {
            "team": "Enterprise North America",
            "targetCents": 3_800_000_00,
            "attainedCents": 2_410_000_00,
            "confidence": 72,
        },
        {
            "team": "Strategic Accounts and Expansion",
            "targetCents": 2_100_000_00,
            "attainedCents": 1_920_000_00,
            "confidence": 58,
        },
        {
            "team": "Digital and Self-Serve Assisted",
            "targetCents": 940_000_00,
            "attainedCents": 611_000_00,
            "confidence": 84,
        },
    ]


@router.get("/api/support/cases", response_model=list[SupportCaseResponse])
def list_support_cases() -> list[dict[str, Any]]:
    return [
        support_case_payload(item)
        for item in database.rows(
            "SELECT * FROM support_cases ORDER BY last_reply_at DESC"
        )
    ]


@router.get(
    "/api/support/cases/{case_id}",
    response_model=SupportCaseDetailResponse,
)
def get_support_case(case_id: int) -> dict[str, Any]:
    item = database.row("SELECT * FROM support_cases WHERE id = ?", (case_id,))
    if not item:
        raise HTTPException(status_code=404, detail="Support case not found")
    payload = support_case_payload(item)
    payload["messages"] = [
        {
            "id": message["id"],
            "author": message["author_ref"],
            "body": message["message_blob"],
            "channel": message["source_channel"],
            "createdAt": message["created_at"],
        }
        for message in database.rows(
            "SELECT * FROM support_messages WHERE case_id = ? ORDER BY created_at",
            (case_id,),
        )
    ]
    return payload


@router.post(
    "/api/support/cases/{case_id}/assign",
    response_model=SupportCaseResponse,
)
def assign_support_case(
    case_id: int, payload: SupportAssignment
) -> dict[str, Any]:
    item = database.row("SELECT * FROM support_cases WHERE id = ?", (case_id,))
    if not item:
        raise HTTPException(status_code=404, detail="Support case not found")
    database.execute(
        "UPDATE support_cases SET assignee_ref = ? WHERE id = ?",
        (payload.assignee, case_id),
    )
    return support_case_payload({**item, "assignee_ref": payload.assignee})


@router.post(
    "/api/support/cases/{case_id}/close",
    response_model=SupportCaseResponse,
)
def close_support_case(case_id: int) -> dict[str, Any]:
    item = database.row("SELECT * FROM support_cases WHERE id = ?", (case_id,))
    if not item:
        raise HTTPException(status_code=404, detail="Support case not found")
    database.execute(
        "UPDATE support_cases SET state_code = 'resolved_maybe' WHERE id = ?",
        (case_id,),
    )
    return support_case_payload({**item, "state_code": "resolved_maybe"})


@router.get("/api/support/sla-policies", response_model=list[SlaPolicyResponse])
def list_sla_policies() -> list[dict[str, Any]]:
    return [
        {
            "id": item["id"],
            "name": item["policy_label"],
            "priority": item["priority_code"],
            "firstResponseMinutes": _integer_text(item["first_response_text"]),
            "resolutionMinutes": _integer_text(item["resolution_text"]),
            "coverage": item["coverage_window"],
        }
        for item in database.rows("SELECT * FROM sla_policies ORDER BY id")
    ]


@router.get("/api/support/macros", response_model=list[SupportMacroResponse])
def list_support_macros() -> list[dict[str, Any]]:
    return [
        {
            "id": "macro-export-progress",
            "title": "Export processing reassurance",
            "bodyPreview": "Your export is progressing through our resilient queue...",
            "usageCount": 184,
            "owner": "Support Operations",
        },
        {
            "id": "macro-duplicate-contacts",
            "title": "Duplicate contact investigation",
            "bodyPreview": "We are reconciling identity across your connected sources...",
            "usageCount": 92,
            "owner": "Data Reliability",
        },
        {
            "id": "macro-strategic-apology",
            "title": "Strategic alignment apology",
            "bodyPreview": "We recognize this experience did not feel seamlessly empowering...",
            "usageCount": 47,
            "owner": "Executive Escalations",
        },
    ]
