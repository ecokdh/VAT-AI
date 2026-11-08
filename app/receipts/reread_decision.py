"""Choose reread regions and accept or hold candidates without using gold.

Adoption does not treat a matching total as enough evidence. Weak candidates
stay for user review, and fields outside the target rows are left as they were.
"""
from __future__ import annotations

from typing import Any

from app.receipts.line_structure import display_name, parse_number
from app.receipts.relation_config import MAX_REREAD_REGIONS, MAX_REREAD_ROUNDS, REREAD_POLICY_VERSION


def suspicion_rows(checks: list[dict]) -> list[str]:
    found: list[str] = []
    for check in checks:
        if not check.get("reread"):
            continue
        for row_id in check.get("rows") or []:
            if isinstance(row_id, str) and row_id.startswith("r") and row_id not in found:
                found.append(row_id)
    return found


def box_status(box: dict | None, width: int, height: int) -> str:
    if not isinstance(box, dict) or box.get("source") in {None, "none"}:
        return "missing"
    try:
        x0, y0, x1, y1 = (float(box[key]) for key in ("x0", "y0", "x1", "y1"))
    except (KeyError, TypeError, ValueError):
        return "invalid"
    if box.get("space") == "pixels":
        ok = 0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height
    elif box.get("space") == "normalized_0_1":
        ok = 0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1
    else:
        return "invalid"
    return "ok" if ok else "out_of_range"


def _union(boxes: list[dict]) -> dict | None:
    good = []
    for box in boxes:
        if box.get("space") != "normalized_0_1":
            continue
        try:
            good.append(tuple(float(box[key]) for key in ("x0", "y0", "x1", "y1")))
        except (KeyError, TypeError, ValueError):
            continue
    if not good:
        return None
    return {
        "x0": min(item[0] for item in good),
        "y0": min(item[1] for item in good),
        "x1": max(item[2] for item in good),
        "y1": max(item[3] for item in good),
        "space": "normalized_0_1",
        "source": "layout_union",
    }


def _pad(box: dict, pad: float = 0.02) -> dict:
    return {
        **box,
        "x0": max(0.0, box["x0"] - pad),
        "y0": max(0.0, box["y0"] - pad),
        "x1": min(1.0, box["x1"] + pad),
        "y1": min(1.0, box["y1"] + pad),
    }


def select_reread_plan(structure: dict, checks: list[dict], image_size: tuple[int, int]) -> dict[str, Any]:
    width, height = image_size
    reread_checks = [check for check in checks if check.get("reread")]
    row_ids = suspicion_rows(checks)
    rows = structure.get("rows") or []
    by_id = {row["row_id"]: index for index, row in enumerate(rows)}
    if not reread_checks:
        return {
            "version": REREAD_POLICY_VERSION,
            "round": 0,
            "regions": [],
            "case_action": "keep_b",
            "reason": "의심 신호가 없어 재판독을 하지 않음",
        }
    if not row_ids:
        diagnosis = [check.get("diagnosis") for check in reread_checks]
        return {
            "version": REREAD_POLICY_VERSION,
            "round": 1,
            "max_rounds": MAX_REREAD_ROUNDS,
            "max_regions": MAX_REREAD_REGIONS,
            "regions": [{
                "region_id": "region-1",
                "mode": "full_photo",
                "row_ids": [],
                "reason": "행 ID가 없는 문서 금액 신호라 전체 사진을 한 번 재판독",
                "crop": None,
                "column_headers": [column.get("header") for column in structure.get("columns") or []],
                "diagnosis": diagnosis,
            }],
            "dropped_row_ids": [],
            "case_action": "reread",
            "reason": "행 ID가 없는 문서 금액 신호라 전체 사진을 한 번 재판독",
        }
    clusters: list[list[int]] = []
    for row_id in row_ids:
        index = by_id.get(row_id)
        if index is None:
            continue
        band = [position for position in range(max(0, index - 1), min(len(rows), index + 2))]
        if clusters and band[0] <= clusters[-1][-1]:
            clusters[-1] = sorted(set(clusters[-1] + band))
        else:
            clusters.append(band)
    regions = []
    dropped = []
    for band in clusters:
        if len(regions) >= MAX_REREAD_REGIONS:
            dropped.extend(rows[position]["row_id"] for position in band)
            continue
        boxes = []
        for position in band:
            status = box_status(rows[position].get("box"), width, height)
            if status == "ok" and rows[position]["box"].get("space") == "normalized_0_1":
                boxes.append(rows[position]["box"])
        union = _union(boxes)
        header_note = [column.get("header") for column in structure.get("columns") or []]
        diagnosis = [check["diagnosis"] for check in checks if check.get("reread") and set(check.get("rows") or []).intersection({rows[position]["row_id"] for position in band})]
        if union is None:
            regions.append({
                "region_id": f"region-{len(regions) + 1}",
                "mode": "full_photo",
                "row_ids": [rows[position]["row_id"] for position in band],
                "reason": "문제 행의 유효한 원본 좌표가 없어 전체 사진을 사용",
                "crop": None,
                "column_headers": header_note,
                "diagnosis": diagnosis,
            })
            continue
        padded = _pad(union)
        regions.append({
            "region_id": f"region-{len(regions) + 1}",
            "mode": "zoom",
            "row_ids": [rows[position]["row_id"] for position in band],
            "reason": "문제 행과 이웃 행의 검출 좌표로 영역을 잡음",
            "crop": {
                "original_normalized": padded,
                "pixel_box": _pixels(padded, width, height),
                "coordinate_space": "original",
            },
            "column_headers": header_note,
            "diagnosis": diagnosis,
        })
    if not regions:
        return {
            "version": REREAD_POLICY_VERSION,
            "round": 0,
            "regions": [],
            "case_action": "not_run",
            "reason": "의심 행은 있으나 이미지 위치가 없고 전체 사진 영역도 구성하지 못함",
            "dropped_row_ids": dropped,
        }
    return {
        "version": REREAD_POLICY_VERSION,
        "round": 1 if regions else 0,
        "max_rounds": MAX_REREAD_ROUNDS,
        "max_regions": MAX_REREAD_REGIONS,
        "regions": regions[:MAX_REREAD_REGIONS],
        "dropped_row_ids": dropped,
        "case_action": "reread",
        "reason": "검증 신호로 선택한 영역만 한 라운드 재판독",
    }


def _pixels(box: dict, width: int, height: int) -> dict:
    return {
        "x0": int(round(box["x0"] * width)),
        "y0": int(round(box["y0"] * height)),
        "x1": int(round(box["x1"] * width)),
        "y1": int(round(box["y1"] * height)),
        "space": "pixels",
        "mapped_from": "normalized_0_1",
    }


def map_crop_box_to_original(crop_box: dict, reported: dict) -> dict | None:
    """Map a box returned inside a crop back to original normalized coordinates."""
    try:
        origin_x0 = float(crop_box["x0"])
        origin_y0 = float(crop_box["y0"])
        origin_x1 = float(crop_box["x1"])
        origin_y1 = float(crop_box["y1"])
        x0, y0, x1, y1 = (float(reported[key]) for key in ("x0", "y0", "x1", "y1"))
    except (KeyError, TypeError, ValueError):
        return None
    if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
        return None
    width = origin_x1 - origin_x0
    height = origin_y1 - origin_y0
    return {
        "x0": origin_x0 + x0 * width,
        "y0": origin_y0 + y0 * height,
        "x1": origin_x0 + x1 * width,
        "y1": origin_y0 + y1 * height,
        "space": "normalized_0_1",
        "source": "reread_mapped_to_original",
    }


def adopt_reread(structure: dict, region: dict, candidate: dict | None) -> dict[str, Any]:
    """Keep the model raw rows. Copy a candidate only onto target rows with evidence."""
    raw_rows = [dict(row) for row in structure.get("rows") or []]
    if not candidate or candidate.get("status") != "success":
        return {
            "decision": "hold",
            "reason": "재판독 응답이 없거나 실패",
            "rows": raw_rows,
            "model_rows_preserved": True,
            "changed_row_ids": [],
            "user_review_row_ids": list(region.get("row_ids") or []),
        }
    targets = set(region.get("row_ids") or [])
    candidate_rows = {row.get("row_id"): row for row in candidate.get("rows") or [] if isinstance(row, dict)}
    changed = []
    review = []
    updated = []
    for row in raw_rows:
        if row["row_id"] not in targets or row["row_id"] not in candidate_rows:
            updated.append(row)
            continue
        proposal = candidate_rows[row["row_id"]]
        evidence_ok = bool(str(proposal.get("source_label") or "").strip()) and bool(str(proposal.get("relation_note") or "").strip())
        numbers_printed = any(parse_number(proposal.get(key)) is not None for key in ("q", "u", "p"))
        same_name = display_name(proposal.get("n")) == display_name(row.get("raw_name")) or not str(proposal.get("n") or "").strip()
        if not evidence_ok or not numbers_printed or not same_name:
            review.append(row["row_id"])
            updated.append(row)
            continue
        if proposal.get("checksum_only") is True:
            review.append(row["row_id"])
            updated.append(row)
            continue
        merged = dict(row)
        for source_key, dest_key in (("q", "quantity"), ("u", "unit_price"), ("p", "line_amount")):
            if source_key in proposal:
                merged[dest_key] = proposal.get(source_key)
        if proposal.get("t") in {"item", "option", "discount", "notice"}:
            merged["row_type"] = proposal["t"]
        if "parent" in proposal:
            parent = proposal.get("parent")
            if parent is None:
                merged["parent_row_id"] = None
                merged["parent_index"] = None
            elif isinstance(parent, int) and 0 <= parent < len(raw_rows) and raw_rows[parent].get("row_type") == "item":
                merged["parent_index"] = parent
                merged["parent_row_id"] = raw_rows[parent]["row_id"]
        merged["reread_candidate"] = {
            "source_label": proposal.get("source_label"),
            "relation_note": proposal.get("relation_note"),
            "values": {"q": proposal.get("q"), "u": proposal.get("u"), "p": proposal.get("p")},
        }
        merged["selection_reason"] = "인쇄 라벨과 관계 설명이 있는 재판독 후보만 대상 행에 반영"
        changed.append(row["row_id"])
        updated.append(merged)
    for position, row in enumerate(updated):
        parent = row.get("parent_index")
        if isinstance(parent, int) and (parent < 0 or parent >= len(updated) or updated[parent].get("row_type") != "item" or parent == position):
            row["parent_index"] = None
            row["parent_row_id"] = None
            row.setdefault("uncertainty", []).append("parent_rechecked_after_reread")
            review.append(row["row_id"])
    decision = "adopt" if changed else "hold"
    return {
        "decision": decision,
        "reason": "대상 행만 반영" if changed else "근거가 부족해 사용자 확인으로 남김",
        "rows": updated,
        "model_rows_preserved": True,
        "changed_row_ids": changed,
        "user_review_row_ids": sorted(set(review)),
    }
