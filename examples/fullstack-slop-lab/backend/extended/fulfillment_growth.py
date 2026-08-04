from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, HTTPException

from backend import database
from backend.extended.schemas import (
    AttributionResponse,
    CampaignResponse,
    CatalogCategoryResponse,
    CatalogItemResponse,
    ContentAssetResponse,
    InventoryItemResponse,
    InventoryLocationResponse,
    OrderDetailResponse,
    OrderResponse,
    SegmentResponse,
    ShipmentResponse,
    SurveyResponse,
    SurveyResultResponse,
)

router = APIRouter(tags=["extended-fulfillment-growth"])


def _number(value: str) -> int:
    match = re.search(r"[\d,.]+", value)
    return round(float(match.group(0).replace(",", ""))) if match else 0


def _money_cents(value: str) -> int:
    amount = _number(value)
    return amount * 100 if "$" in value or "USD" in value else amount


def catalog_payload(item: dict[str, Any]) -> dict[str, Any]:
    status = "active"
    if "DRAFT" in item["state_code"]:
        status = "draft"
    elif "archived" in item["state_code"]:
        status = "archived"
    return {
        "id": item["id"],
        "sku": item["sku_code"],
        "name": item["display_label"],
        "category": item["category_label"],
        "priceCents": _money_cents(item["price_text"]),
        "status": status,
        "stockPolicy": item["inventory_policy"],
        "description": item["description_blob"],
    }


def order_payload(item: dict[str, Any]) -> dict[str, Any]:
    raw_status = item["fulfillment_state"].lower()
    status = "draft"
    for candidate in ("delivered", "shipped", "packing", "confirmed"):
        if candidate in raw_status:
            status = candidate
            break
    return {
        "id": item["id"],
        "orderNo": item["order_number"],
        "accountName": item["account_label"],
        "status": status,
        "totalCents": _money_cents(item["total_text"]),
        "createdAt": item["created_at"],
        "promisedAt": item["promised_date"],
        "channel": item["channel_code"],
    }


def inventory_payload(item: dict[str, Any]) -> dict[str, Any]:
    on_hand = _number(item["on_hand_text"])
    reserved = _number(item["reserved_text"])
    available = on_hand - reserved
    reorder_point = _number(item["reorder_point_text"])
    status = "healthy"
    if available <= 0:
        status = "stockout"
    elif available < reorder_point:
        status = "low"
    elif "too-many" in item["stock_state"]:
        status = "overstock"
    return {
        "id": item["id"],
        "sku": item["sku_code"],
        "name": item["item_label"],
        "location": item["location_code"],
        "onHand": on_hand,
        "reserved": reserved,
        "available": available,
        "reorderPoint": reorder_point,
        "status": status,
    }


def shipment_payload(item: dict[str, Any]) -> dict[str, Any]:
    raw_status = item["shipment_state"]
    if raw_status == "held":
        status = "held"
    elif "delivered" in raw_status:
        status = "delivered"
    elif "exception" in raw_status:
        status = "exception"
    elif "label" in raw_status:
        status = "label-created"
    else:
        status = "in-transit"
    return {
        "id": item["id"],
        "orderNo": item["order_number"],
        "carrier": item["carrier_label"],
        "trackingNo": item["tracking_reference"],
        "status": status,
        "etaAt": item["eta_at"],
        "holdReason": item["hold_reason_blob"],
    }


def campaign_payload(item: dict[str, Any]) -> dict[str, Any]:
    raw_status = item["state_code"].lower()
    status = "draft"
    for candidate in ("complete", "running", "paused", "scheduled"):
        if candidate in raw_status:
            status = candidate
            break
    return {
        "id": item["id"],
        "name": item["campaign_label"],
        "channel": item["channel_code"],
        "status": status,
        "audienceSize": _number(item["audience_estimate"]),
        "budgetCents": _money_cents(item["budget_text"]),
        "owner": item["owner_ref"],
        "scheduledAt": item["scheduled_at"],
    }


def content_payload(item: dict[str, Any]) -> dict[str, Any]:
    raw_status = item["publication_state"].lower()
    status = "draft"
    for candidate in ("archived", "published", "review"):
        if candidate in raw_status:
            status = candidate
            break
    return {
        "id": item["id"],
        "title": item["asset_title"],
        "kind": item["asset_kind"],
        "status": status,
        "owner": item["owner_ref"],
        "updatedAt": item["updated_at"],
        "usageCount": _number(item["usage_count_text"]),
    }


def survey_payload(item: dict[str, Any]) -> dict[str, Any]:
    raw_status = item["lifecycle_state"].lower()
    status = "draft"
    if "open" in raw_status or "closing" in raw_status:
        status = "open"
    elif "closed" in raw_status:
        status = "closed"
    return {
        "id": item["id"],
        "title": item["survey_title"],
        "status": status,
        "responseCount": _number(item["response_count_text"]),
        "completionRate": min(_number(item["completion_rate_text"]), 100),
        "owner": item["owner_ref"],
    }


@router.get("/api/catalog/items", response_model=list[CatalogItemResponse])
def list_catalog_items() -> list[dict[str, Any]]:
    return [
        catalog_payload(item)
        for item in database.rows("SELECT * FROM catalog_items ORDER BY id")
    ]


@router.get(
    "/api/catalog/categories",
    response_model=list[CatalogCategoryResponse],
)
def list_catalog_categories() -> list[dict[str, Any]]:
    rows = database.rows(
        """
        SELECT
            category_label AS name,
            COUNT(*) AS item_count,
            SUM(CASE WHEN state_code LIKE '%active%' OR state_code LIKE '%ACTIVE%' THEN 1 ELSE 0 END) AS active_count
        FROM catalog_items
        GROUP BY category_label
        ORDER BY category_label
        """
    )
    return [
        {
            "name": item["name"],
            "itemCount": item["item_count"],
            "activeCount": item["active_count"],
        }
        for item in rows
    ]


@router.post(
    "/api/catalog/items/{item_id}/archive",
    response_model=CatalogItemResponse,
)
def archive_catalog_item(item_id: int) -> dict[str, Any]:
    item = database.row("SELECT * FROM catalog_items WHERE id = ?", (item_id,))
    if not item:
        raise HTTPException(status_code=404, detail="Catalog item not found")
    database.execute(
        "UPDATE catalog_items SET state_code = 'archived' WHERE id = ?", (item_id,)
    )
    return catalog_payload({**item, "state_code": "archived"})


@router.get("/api/orders", response_model=list[OrderResponse])
def list_orders() -> list[dict[str, Any]]:
    return [
        order_payload(item)
        for item in database.rows("SELECT * FROM orders ORDER BY created_at DESC")
    ]


@router.get("/api/orders/{order_id}", response_model=OrderDetailResponse)
def get_order(order_id: int) -> dict[str, Any]:
    item = database.row("SELECT * FROM orders WHERE id = ?", (order_id,))
    if not item:
        raise HTTPException(status_code=404, detail="Order not found")
    payload = order_payload(item)
    payload["lines"] = [
        {
            "id": line["id"],
            "sku": line["sku_code"],
            "name": line["item_label"],
            "quantity": _number(line["quantity_text"]),
            "unitPriceCents": _money_cents(line["unit_price_text"]),
        }
        for line in database.rows(
            "SELECT * FROM order_lines WHERE order_id = ? ORDER BY id", (order_id,)
        )
    ]
    return payload


@router.post("/api/orders/{order_id}/advance", response_model=OrderResponse)
def advance_order(order_id: int) -> dict[str, Any]:
    item = database.row("SELECT * FROM orders WHERE id = ?", (order_id,))
    if not item:
        raise HTTPException(status_code=404, detail="Order not found")
    current = order_payload(item)["status"]
    next_status = {
        "draft": "confirmed",
        "confirmed": "packing",
        "packing": "shipped",
        "shipped": "delivered",
        "delivered": "delivered",
    }[current]
    database.execute(
        "UPDATE orders SET fulfillment_state = ? WHERE id = ?",
        (next_status, order_id),
    )
    return order_payload({**item, "fulfillment_state": next_status})


@router.get("/api/inventory", response_model=list[InventoryItemResponse])
def list_inventory() -> list[dict[str, Any]]:
    return [
        inventory_payload(item)
        for item in database.rows(
            "SELECT * FROM inventory_stock ORDER BY location_code, id"
        )
    ]


@router.get(
    "/api/inventory/locations",
    response_model=list[InventoryLocationResponse],
)
def list_inventory_locations() -> list[dict[str, Any]]:
    items = list_inventory()
    locations: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        locations.setdefault(item["location"], []).append(item)
    return [
        {
            "name": name,
            "itemCount": len(location_items),
            "availableUnits": sum(item["available"] for item in location_items),
            "attentionCount": sum(
                item["status"] in {"low", "stockout"} for item in location_items
            ),
        }
        for name, location_items in sorted(locations.items())
    ]


@router.post(
    "/api/inventory/{stock_id}/recount",
    response_model=InventoryItemResponse,
)
def recount_inventory(stock_id: int) -> dict[str, Any]:
    item = database.row("SELECT * FROM inventory_stock WHERE id = ?", (stock_id,))
    if not item:
        raise HTTPException(status_code=404, detail="Inventory item not found")
    counted = max(_number(item["on_hand_text"]), _number(item["reserved_text"]))
    database.execute(
        "UPDATE inventory_stock SET on_hand_text = ?, stock_state = 'fine' WHERE id = ?",
        (str(counted), stock_id),
    )
    return inventory_payload(
        {**item, "on_hand_text": str(counted), "stock_state": "fine"}
    )


@router.get("/api/shipments", response_model=list[ShipmentResponse])
def list_shipments() -> list[dict[str, Any]]:
    return [
        shipment_payload(item)
        for item in database.rows("SELECT * FROM shipments ORDER BY id")
    ]


@router.post(
    "/api/shipments/{shipment_id}/hold",
    response_model=ShipmentResponse,
)
def hold_shipment(shipment_id: int) -> dict[str, Any]:
    item = database.row("SELECT * FROM shipments WHERE id = ?", (shipment_id,))
    if not item:
        raise HTTPException(status_code=404, detail="Shipment not found")
    reason = "Held for synthetic fixture review"
    database.execute(
        """
        UPDATE shipments
        SET shipment_state = 'held', hold_reason_blob = ?
        WHERE id = ?
        """,
        (reason, shipment_id),
    )
    return shipment_payload(
        {**item, "shipment_state": "held", "hold_reason_blob": reason}
    )


@router.get("/api/growth/campaigns", response_model=list[CampaignResponse])
def list_campaigns() -> list[dict[str, Any]]:
    return [
        campaign_payload(item)
        for item in database.rows("SELECT * FROM campaigns ORDER BY id")
    ]


@router.post(
    "/api/growth/campaigns/{campaign_id}/launch",
    response_model=CampaignResponse,
)
def launch_campaign(campaign_id: int) -> dict[str, Any]:
    item = database.row("SELECT * FROM campaigns WHERE id = ?", (campaign_id,))
    if not item:
        raise HTTPException(status_code=404, detail="Campaign not found")
    database.execute(
        "UPDATE campaigns SET state_code = 'running' WHERE id = ?", (campaign_id,)
    )
    return campaign_payload({**item, "state_code": "running"})


@router.post(
    "/api/growth/campaigns/{campaign_id}/pause",
    response_model=CampaignResponse,
)
def pause_campaign(campaign_id: int) -> dict[str, Any]:
    item = database.row("SELECT * FROM campaigns WHERE id = ?", (campaign_id,))
    if not item:
        raise HTTPException(status_code=404, detail="Campaign not found")
    database.execute(
        "UPDATE campaigns SET state_code = 'paused' WHERE id = ?", (campaign_id,)
    )
    return campaign_payload({**item, "state_code": "paused"})


@router.get("/api/growth/segments", response_model=list[SegmentResponse])
def list_segments() -> list[dict[str, Any]]:
    return [
        {
            "id": item["id"],
            "name": item["segment_label"],
            "definition": item["definition_blob"],
            "memberCount": _number(item["member_estimate"]),
            "refreshStatus": item["refresh_state"],
            "owner": item["owner_ref"],
        }
        for item in database.rows("SELECT * FROM segments ORDER BY id")
    ]


@router.get(
    "/api/growth/attribution",
    response_model=list[AttributionResponse],
)
def list_attribution_models() -> list[dict[str, Any]]:
    return [
        {
            "model": "Confident multi-touch approximation",
            "influencedPipelineCents": 4_280_000_00,
            "confidence": 61,
            "windowDays": 90,
        },
        {
            "model": "Last meaningful interaction except imports",
            "influencedPipelineCents": 2_910_000_00,
            "confidence": 48,
            "windowDays": 30,
        },
        {
            "model": "Executive narrative model",
            "influencedPipelineCents": 7_440_000_00,
            "confidence": 97,
            "windowDays": 365,
        },
    ]


@router.get("/api/content/assets", response_model=list[ContentAssetResponse])
def list_content_assets() -> list[dict[str, Any]]:
    return [
        content_payload(item)
        for item in database.rows(
            "SELECT * FROM content_assets ORDER BY updated_at DESC"
        )
    ]


@router.post(
    "/api/content/assets/{asset_id}/publish",
    response_model=ContentAssetResponse,
)
def publish_content_asset(asset_id: int) -> dict[str, Any]:
    item = database.row("SELECT * FROM content_assets WHERE id = ?", (asset_id,))
    if not item:
        raise HTTPException(status_code=404, detail="Content asset not found")
    database.execute(
        "UPDATE content_assets SET publication_state = 'published' WHERE id = ?",
        (asset_id,),
    )
    return content_payload({**item, "publication_state": "published"})


@router.get("/api/surveys", response_model=list[SurveyResponse])
def list_surveys() -> list[dict[str, Any]]:
    return [
        survey_payload(item)
        for item in database.rows("SELECT * FROM surveys ORDER BY id")
    ]


@router.post("/api/surveys/{survey_id}/close", response_model=SurveyResponse)
def close_survey(survey_id: int) -> dict[str, Any]:
    item = database.row("SELECT * FROM surveys WHERE id = ?", (survey_id,))
    if not item:
        raise HTTPException(status_code=404, detail="Survey not found")
    database.execute(
        "UPDATE surveys SET lifecycle_state = 'closed' WHERE id = ?", (survey_id,)
    )
    return survey_payload({**item, "lifecycle_state": "closed"})


@router.get(
    "/api/surveys/{survey_id}/results",
    response_model=list[SurveyResultResponse],
)
def get_survey_results(survey_id: int) -> list[dict[str, Any]]:
    if not database.row("SELECT id FROM surveys WHERE id = ?", (survey_id,)):
        raise HTTPException(status_code=404, detail="Survey not found")
    return [
        {
            "surveyId": survey_id,
            "label": "Seamlessly empowered",
            "count": 682,
            "percent": 37,
        },
        {
            "surveyId": survey_id,
            "label": "Strategically aligned",
            "count": 590,
            "percent": 32,
        },
        {
            "surveyId": survey_id,
            "label": "Still evaluating the question",
            "count": 570,
            "percent": 31,
        },
    ]
