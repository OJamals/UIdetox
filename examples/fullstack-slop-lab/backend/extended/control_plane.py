from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, HTTPException

from backend import database
from backend.extended.schemas import (
    AuditEventResponse,
    FeatureFlagResponse,
    FeatureFlagUpdate,
    IncidentResponse,
    MarketplaceAppResponse,
    UsageMetricResponse,
    WorkItemResponse,
)

router = APIRouter(tags=["extended-control-plane"])


def _number(value: str) -> int:
    match = re.search(r"\d+", value)
    return int(match.group(0)) if match else 0


def audit_payload(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item["id"],
        "actor": item["actor_ref"],
        "action": item["action_code"],
        "resource": item["resource_ref"],
        "detail": item["detail_blob"],
        "createdAt": item["created_at"],
        "ipHint": item["ip_hint"],
    }


def feature_flag_payload(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "key": item["flag_key"],
        "title": item["display_label"],
        "enabled": bool(item["enabled_flag"]),
        "rolloutPercent": min(_number(item["rollout_text"]), 100),
        "audience": item["audience_query"],
        "owner": item["owner_ref"],
    }


def incident_payload(item: dict[str, Any]) -> dict[str, Any]:
    raw_severity = item["severity_code"].lower().replace("_", "-")
    severity = "sev-3"
    if "one" in raw_severity or raw_severity == "sev-1":
        severity = "sev-1"
    elif raw_severity == "sev-2":
        severity = "sev-2"
    raw_status = item["incident_state"].lower()
    status = "investigating"
    if "monitoring" in raw_status:
        status = "monitoring"
    elif "resolved" in raw_status:
        status = "resolved"
    return {
        "id": item["id"],
        "title": item["incident_title"],
        "severity": severity,
        "status": status,
        "affectedService": item["service_ref"],
        "startedAt": item["started_at"],
        "acknowledged": bool(item["acknowledged_flag"]),
    }


def marketplace_payload(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item["id"],
        "name": item["app_label"],
        "category": item["category_code"],
        "installed": bool(item["installed_flag"]),
        "permissions": [
            permission.strip()
            for permission in item["permissions_blob"].split(",")
            if permission.strip()
        ],
        "description": item["description_blob"],
    }


def work_item_payload(item: dict[str, Any]) -> dict[str, Any]:
    raw_status = item["state_code"].lower()
    status = "unclaimed"
    if "blocked" in raw_status:
        status = "blocked"
    elif "done" in raw_status:
        status = "done"
    elif "claimed" in raw_status:
        status = "claimed"
    return {
        "id": item["id"],
        "title": item["work_title"],
        "kind": item["work_kind"],
        "status": status,
        "owner": item["owner_ref"],
        "dueAt": item["due_at"],
        "priority": _number(item["priority_text"]),
        "source": item["source_ref"],
    }


@router.get("/api/audit/events", response_model=list[AuditEventResponse])
def list_audit_events() -> list[dict[str, Any]]:
    return [
        audit_payload(item)
        for item in database.rows("SELECT * FROM audit_events ORDER BY created_at DESC")
    ]


@router.get("/api/audit/events/{event_id}", response_model=AuditEventResponse)
def get_audit_event(event_id: int) -> dict[str, Any]:
    item = database.row("SELECT * FROM audit_events WHERE id = ?", (event_id,))
    if not item:
        raise HTTPException(status_code=404, detail="Audit event not found")
    return audit_payload(item)


@router.get(
    "/api/platform/feature-flags",
    response_model=list[FeatureFlagResponse],
)
def list_feature_flags() -> list[dict[str, Any]]:
    return [
        feature_flag_payload(item)
        for item in database.rows("SELECT * FROM feature_flags ORDER BY flag_key")
    ]


@router.put(
    "/api/platform/feature-flags/{flag_key}",
    response_model=FeatureFlagResponse,
)
def update_feature_flag(
    flag_key: str, payload: FeatureFlagUpdate
) -> dict[str, Any]:
    item = database.row(
        "SELECT * FROM feature_flags WHERE flag_key = ?", (flag_key,)
    )
    if not item:
        raise HTTPException(status_code=404, detail="Feature flag not found")
    database.execute(
        "UPDATE feature_flags SET enabled_flag = ? WHERE flag_key = ?",
        (int(payload.enabled), flag_key),
    )
    return feature_flag_payload({**item, "enabled_flag": int(payload.enabled)})


@router.get("/api/platform/incidents", response_model=list[IncidentResponse])
def list_incidents() -> list[dict[str, Any]]:
    return [
        incident_payload(item)
        for item in database.rows("SELECT * FROM incidents ORDER BY started_at DESC")
    ]


@router.post(
    "/api/platform/incidents/{incident_id}/acknowledge",
    response_model=IncidentResponse,
)
def acknowledge_incident(incident_id: int) -> dict[str, Any]:
    item = database.row("SELECT * FROM incidents WHERE id = ?", (incident_id,))
    if not item:
        raise HTTPException(status_code=404, detail="Incident not found")
    database.execute(
        "UPDATE incidents SET acknowledged_flag = 1 WHERE id = ?", (incident_id,)
    )
    return incident_payload({**item, "acknowledged_flag": 1})


@router.post(
    "/api/platform/incidents/{incident_id}/resolve",
    response_model=IncidentResponse,
)
def resolve_incident(incident_id: int) -> dict[str, Any]:
    item = database.row("SELECT * FROM incidents WHERE id = ?", (incident_id,))
    if not item:
        raise HTTPException(status_code=404, detail="Incident not found")
    database.execute(
        """
        UPDATE incidents
        SET incident_state = 'resolved', acknowledged_flag = 1
        WHERE id = ?
        """,
        (incident_id,),
    )
    return incident_payload(
        {**item, "incident_state": "resolved", "acknowledged_flag": 1}
    )


@router.get("/api/platform/usage", response_model=list[UsageMetricResponse])
def list_platform_usage() -> list[dict[str, Any]]:
    return [
        {
            "metric": "Tracked customer events",
            "value": 8_840_221,
            "limit": 10_000_000,
            "unit": "events",
            "trend": 18,
        },
        {
            "metric": "Active automation executions",
            "value": 46_012,
            "limit": 50_000,
            "unit": "runs",
            "trend": 31,
        },
        {
            "metric": "AI enrichment credits",
            "value": 102_442,
            "limit": 100_000,
            "unit": "credits",
            "trend": 72,
        },
    ]


@router.get("/api/marketplace/apps", response_model=list[MarketplaceAppResponse])
def list_marketplace_apps() -> list[dict[str, Any]]:
    return [
        marketplace_payload(item)
        for item in database.rows("SELECT * FROM marketplace_apps ORDER BY id")
    ]


@router.post(
    "/api/marketplace/apps/{app_id}/install",
    response_model=MarketplaceAppResponse,
)
def install_marketplace_app(app_id: int) -> dict[str, Any]:
    item = database.row("SELECT * FROM marketplace_apps WHERE id = ?", (app_id,))
    if not item:
        raise HTTPException(status_code=404, detail="Marketplace app not found")
    database.execute(
        "UPDATE marketplace_apps SET installed_flag = 1 WHERE id = ?", (app_id,)
    )
    return marketplace_payload({**item, "installed_flag": 1})


@router.get("/api/work-queue", response_model=list[WorkItemResponse])
def list_work_items() -> list[dict[str, Any]]:
    return [
        work_item_payload(item)
        for item in database.rows(
            "SELECT * FROM work_items ORDER BY priority_text DESC, due_at"
        )
    ]


@router.post(
    "/api/work-queue/{work_item_id}/claim",
    response_model=WorkItemResponse,
)
def claim_work_item(work_item_id: int) -> dict[str, Any]:
    item = database.row("SELECT * FROM work_items WHERE id = ?", (work_item_id,))
    if not item:
        raise HTTPException(status_code=404, detail="Work item not found")
    database.execute(
        """
        UPDATE work_items
        SET state_code = 'claimed', owner_ref = 'Fixture Operator'
        WHERE id = ?
        """,
        (work_item_id,),
    )
    return work_item_payload(
        {**item, "state_code": "claimed", "owner_ref": "Fixture Operator"}
    )


@router.post(
    "/api/work-queue/{work_item_id}/complete",
    response_model=WorkItemResponse,
)
def complete_work_item(work_item_id: int) -> dict[str, Any]:
    item = database.row("SELECT * FROM work_items WHERE id = ?", (work_item_id,))
    if not item:
        raise HTTPException(status_code=404, detail="Work item not found")
    database.execute(
        "UPDATE work_items SET state_code = 'done' WHERE id = ?", (work_item_id,)
    )
    return work_item_payload({**item, "state_code": "done"})
