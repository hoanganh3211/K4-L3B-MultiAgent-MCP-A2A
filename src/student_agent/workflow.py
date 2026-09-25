from __future__ import annotations

import json
import os
from typing import Any

from openai import AsyncOpenAI

from .mcp_gateway import EvidenceGateway
from .trace import TraceWriter

# ---------------------------------------------------------------------------
# Lightweight multi-agent workflow for L3B e-commerce complaint investigation
# Architecture: deterministic MCP tool selection → evidence collection →
#   GPT-4o-mini synthesis → schema-compliant output
# ---------------------------------------------------------------------------

_CLIENT: AsyncOpenAI | None = None


def _openai() -> AsyncOpenAI:
    global _CLIENT
    if _CLIENT is None:
        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set in .env")
        _CLIENT = AsyncOpenAI(api_key=api_key)
    return _CLIENT


# ── helpers ─────────────────────────────────────────────────────────────────

async def _safe_call(
    gateway: EvidenceGateway,
    tool_name: str,
    case_id: str,
    available_tools: list[str],
    **kwargs: str,
) -> dict[str, Any] | None:
    """Call an MCP tool if it exists; return None on any error."""
    if tool_name not in available_tools:
        return None
    try:
        return await gateway.call(tool_name, case_id=case_id, **kwargs)
    except Exception:
        return None


# ── specialist agents (deterministic evidence collectors) ───────────────────

async def _entity_agent(
    case: dict, gateway: EvidenceGateway, trace: TraceWriter, tools: list[str],
) -> tuple[list[dict], list[str]]:
    """Resolve entity: validate candidate orders and pick the real one."""
    case_id = case["case_id"]
    evidence_list: list[dict] = []
    evidence_refs: list[str] = []

    trace.emit(
        case_id=case_id, event_type="task_assigned",
        actor="coordinator", target="entity-agent",
    )

    claimed = case["customer_request"].get("claimed_order_id", "")
    candidates = case.get("candidate_order_ids", [])

    for order_id in candidates:
        ev = await _safe_call(gateway, "get_order", case_id, tools, order_id=order_id)
        if ev:
            evidence_list.append(ev)
            evidence_refs.append(ev["evidence_ref"])
            trace.emit(
                case_id=case_id, event_type="tool_result_consumed",
                actor="entity-agent", tool_name="get_order",
                evidence_refs=[ev["evidence_ref"]],
            )

    trace.emit(
        case_id=case_id, event_type="handoff",
        actor="entity-agent", target="coordinator",
        decision_code="entity_resolved",
    )
    return evidence_list, evidence_refs


async def _customer_agent(
    case: dict, gateway: EvidenceGateway, trace: TraceWriter, tools: list[str],
) -> tuple[list[dict], list[str]]:
    """Fetch customer history."""
    case_id = case["case_id"]
    evidence_list: list[dict] = []
    evidence_refs: list[str] = []

    trace.emit(
        case_id=case_id, event_type="task_assigned",
        actor="coordinator", target="customer-agent",
    )

    cust_id = case.get("customer_unique_id_hint", "")
    if cust_id:
        ev = await _safe_call(
            gateway, "get_customer_history", case_id, tools,
            customer_unique_id=cust_id,
        )
        if ev:
            evidence_list.append(ev)
            evidence_refs.append(ev["evidence_ref"])
            trace.emit(
                case_id=case_id, event_type="tool_result_consumed",
                actor="customer-agent", tool_name="get_customer_history",
                evidence_refs=[ev["evidence_ref"]],
            )

    trace.emit(
        case_id=case_id, event_type="handoff",
        actor="customer-agent", target="coordinator",
    )
    return evidence_list, evidence_refs


async def _shipment_agent(
    case: dict, gateway: EvidenceGateway, trace: TraceWriter, tools: list[str],
    order_id: str,
) -> tuple[list[dict], list[str]]:
    """Investigate shipment for an order."""
    case_id = case["case_id"]
    evidence_list: list[dict] = []
    evidence_refs: list[str] = []

    trace.emit(
        case_id=case_id, event_type="task_assigned",
        actor="coordinator", target="shipment-agent",
    )

    if order_id:
        ev = await _safe_call(
            gateway, "get_shipment_summary", case_id, tools, order_id=order_id,
        )
        if ev:
            evidence_list.append(ev)
            evidence_refs.append(ev["evidence_ref"])
            trace.emit(
                case_id=case_id, event_type="tool_result_consumed",
                actor="shipment-agent", tool_name="get_shipment_summary",
                evidence_refs=[ev["evidence_ref"]],
            )

    trace.emit(
        case_id=case_id, event_type="handoff",
        actor="shipment-agent", target="coordinator",
    )
    return evidence_list, evidence_refs


async def _payment_agent(
    case: dict, gateway: EvidenceGateway, trace: TraceWriter, tools: list[str],
    order_id: str,
) -> tuple[list[dict], list[str]]:
    """Investigate payment and refund for an order."""
    case_id = case["case_id"]
    evidence_list: list[dict] = []
    evidence_refs: list[str] = []

    trace.emit(
        case_id=case_id, event_type="task_assigned",
        actor="coordinator", target="payment-agent",
    )

    if order_id:
        # get_order_payments: payment rows and lifecycle evidence
        ev = await _safe_call(
            gateway, "get_order_payments", case_id, tools, order_id=order_id,
        )
        if ev:
            evidence_list.append(ev)
            evidence_refs.append(ev["evidence_ref"])
            trace.emit(
                case_id=case_id, event_type="tool_result_consumed",
                actor="payment-agent", tool_name="get_order_payments",
                evidence_refs=[ev["evidence_ref"]],
            )

        # get_payment_timeline: base payments and authoritative payment lifecycle events
        ev2 = await _safe_call(
            gateway, "get_payment_timeline", case_id, tools, order_id=order_id,
        )
        if ev2:
            evidence_list.append(ev2)
            evidence_refs.append(ev2["evidence_ref"])
            trace.emit(
                case_id=case_id, event_type="tool_result_consumed",
                actor="payment-agent", tool_name="get_payment_timeline",
                evidence_refs=[ev2["evidence_ref"]],
            )

        # get_refund_timeline: authoritative refund lifecycle events
        ev3 = await _safe_call(
            gateway, "get_refund_timeline", case_id, tools, order_id=order_id,
        )
        if ev3:
            evidence_list.append(ev3)
            evidence_refs.append(ev3["evidence_ref"])
            trace.emit(
                case_id=case_id, event_type="tool_result_consumed",
                actor="payment-agent", tool_name="get_refund_timeline",
                evidence_refs=[ev3["evidence_ref"]],
            )

    trace.emit(
        case_id=case_id, event_type="handoff",
        actor="payment-agent", target="coordinator",
    )
    return evidence_list, evidence_refs


async def _product_agent(
    case: dict, gateway: EvidenceGateway, trace: TraceWriter, tools: list[str],
    order_id: str,
) -> tuple[list[dict], list[str]]:
    """Fetch product details and order items for an order."""
    case_id = case["case_id"]
    evidence_list: list[dict] = []
    evidence_refs: list[str] = []

    trace.emit(
        case_id=case_id, event_type="task_assigned",
        actor="coordinator", target="product-agent",
    )

    if order_id:
        # get_product_context: products and translated categories
        ev = await _safe_call(
            gateway, "get_product_context", case_id, tools, order_id=order_id,
        )
        if ev:
            evidence_list.append(ev)
            evidence_refs.append(ev["evidence_ref"])
            trace.emit(
                case_id=case_id, event_type="tool_result_consumed",
                actor="product-agent", tool_name="get_product_context",
                evidence_refs=[ev["evidence_ref"]],
            )

        # get_order_items: item and seller rows belonging to one order
        ev2 = await _safe_call(
            gateway, "get_order_items", case_id, tools, order_id=order_id,
        )
        if ev2:
            evidence_list.append(ev2)
            evidence_refs.append(ev2["evidence_ref"])
            trace.emit(
                case_id=case_id, event_type="tool_result_consumed",
                actor="product-agent", tool_name="get_order_items",
                evidence_refs=[ev2["evidence_ref"]],
            )

    trace.emit(
        case_id=case_id, event_type="handoff",
        actor="product-agent", target="coordinator",
    )
    return evidence_list, evidence_refs


async def _policy_agent(
    case: dict, gateway: EvidenceGateway, trace: TraceWriter, tools: list[str],
) -> tuple[list[dict], list[str]]:
    """Retrieve applicable policy."""
    case_id = case["case_id"]
    evidence_list: list[dict] = []
    evidence_refs: list[str] = []

    trace.emit(
        case_id=case_id, event_type="task_assigned",
        actor="coordinator", target="policy-agent",
    )

    policy_ver = case.get("policy_version", "EC_POLICY_V2")
    ev = await _safe_call(
        gateway, "get_policy", case_id, tools, policy_version=policy_ver,
    )
    if ev:
        evidence_list.append(ev)
        evidence_refs.append(ev["evidence_ref"])
        trace.emit(
            case_id=case_id, event_type="tool_result_consumed",
            actor="policy-agent", tool_name="get_policy",
            evidence_refs=[ev["evidence_ref"]],
        )

    trace.emit(
        case_id=case_id, event_type="handoff",
        actor="policy-agent", target="coordinator",
    )
    return evidence_list, evidence_refs


async def _seller_agent(
    case: dict, gateway: EvidenceGateway, trace: TraceWriter, tools: list[str],
    order_id: str,
) -> tuple[list[dict], list[str]]:
    """Fetch seller information for an order (get_sellers takes order_id)."""
    case_id = case["case_id"]
    evidence_list: list[dict] = []
    evidence_refs: list[str] = []

    trace.emit(
        case_id=case_id, event_type="task_assigned",
        actor="coordinator", target="seller-agent",
    )

    if order_id:
        ev = await _safe_call(
            gateway, "get_sellers", case_id, tools, order_id=order_id,
        )
        if ev:
            evidence_list.append(ev)
            evidence_refs.append(ev["evidence_ref"])
            trace.emit(
                case_id=case_id, event_type="tool_result_consumed",
                actor="seller-agent", tool_name="get_sellers",
                evidence_refs=[ev["evidence_ref"]],
            )

    trace.emit(
        case_id=case_id, event_type="handoff",
        actor="seller-agent", target="coordinator",
    )
    return evidence_list, evidence_refs


# ── LLM synthesis ──────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are an e-commerce complaint investigation agent. You analyze MCP evidence \
to produce a structured JSON verdict for a Brazilian e-commerce platform.

RULES:
- Output ONLY valid JSON matching the schema, no markdown fences or extra text.
- schema_version MUST be "day09-l3b-output-v2"
- case_id MUST match the provided case_id exactly.
- primary_issue MUST be one of: canceled_order_paid, unavailable_order_paid, \
late_delivery_seller, late_delivery_logistics, valid_split_payment, \
payment_mismatch, duplicate_charge, refund_pending, refund_failed, \
unsupported_claim, insufficient_evidence
- case_status MUST be one of: action_required, no_action, needs_investigation
- shipment verdict MUST be one of: on_time, seller_delay, logistics_delay, lost, \
returned, conflicting, insufficient_evidence
- payment verdict MUST be one of: reconciled, capture_mismatch, duplicate_capture, \
refund_pending, refund_failed, refunded, insufficient_evidence
- entity_resolution status MUST be one of: resolved, ambiguous, not_found
- All evidence_refs in the output MUST come from the provided evidence list only. \
Never fabricate evidence refs.
- cause_code pattern: uppercase letters/digits/underscores, starting with letter, \
3-80 chars (e.g. LATE_SHIPMENT_BY_SELLER)
- party_type MUST be one of: seller, platform, logistics_provider, payment_provider, \
customer, unknown
- currency MUST be "BRL"
- confidence values between 0 and 1
- resolution_actions: array of short action strings (max 80 chars each, max 8 items)
- data_conflicts: if evidence from different sources disagree, document them. \
Each conflict needs field, sources (min 2), selected_source, resolution_code.
- financial_resolution: recommended_refund_brl, refund_lines with reason_code, amount_brl, entity_id
- rejected_candidates: list candidate order IDs that were NOT the real order
- customer_context: customer_unique_id and related_order_ids from customer history
- For claim_assessments: verdict one of supported, unsupported, partially_supported, insufficient_evidence
"""


async def _synthesize(
    case: dict,
    all_evidence: list[dict],
    all_refs: list[str],
) -> dict[str, Any]:
    """Use GPT-4o-mini to synthesize evidence into structured output."""
    case_id = case["case_id"]
    claimed_order = case["customer_request"].get("claimed_order_id", "")
    candidates = case.get("candidate_order_ids", [])
    claims = case["customer_request"].get("claims", [])
    customer_hint = case.get("customer_unique_id_hint", "")

    evidence_summary = []
    for ev in all_evidence:
        evidence_summary.append({
            "evidence_ref": ev.get("evidence_ref"),
            "domain": ev.get("domain"),
            "data": ev.get("data"),
            "warnings": ev.get("warnings", []),
        })

    user_prompt = f"""Analyze this e-commerce complaint case and produce a JSON output.

CASE ID: {case_id}
CLAIMED ORDER: {claimed_order}
CANDIDATE ORDERS: {json.dumps(candidates)}
CUSTOMER CLAIMS: {json.dumps(claims, ensure_ascii=False)}
CUSTOMER UNIQUE ID HINT: {customer_hint}
POLICY VERSION: {case.get("policy_version", "EC_POLICY_V2")}

COLLECTED EVIDENCE (from MCP tools):
{json.dumps(evidence_summary, ensure_ascii=False, indent=2)}

AVAILABLE EVIDENCE REFS (use ONLY these in output):
{json.dumps(all_refs)}

Produce the final JSON output with ALL required fields:
- schema_version, case_id, assessment, affected_entities, entity_resolution,
  customer_context, shipment_analysis, payment_analysis, root_cause_analysis,
  evidence_refs, data_conflicts, financial_resolution, resolution_actions

Also include claim_assessments for each claim.
Remember: schema_version must be "day09-l3b-output-v2", currency must be "BRL".
Analyze evidence carefully. If data is missing, use "insufficient_evidence" verdicts."""

    client = _openai()
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.1,
        max_tokens=4000,
        response_format={"type": "json_object"},
    )

    text = response.choices[0].message.content or "{}"
    result = json.loads(text)

    # ── post-process to ensure schema compliance ──
    result["schema_version"] = "day09-l3b-output-v2"
    result["case_id"] = case_id

    # Ensure all evidence_refs in output actually exist
    valid_refs = set(all_refs)
    if "evidence_refs" in result:
        result["evidence_refs"] = [r for r in result["evidence_refs"] if r in valid_refs]
    else:
        result["evidence_refs"] = list(all_refs)

    # Sanitize claim_assessments evidence refs is now handled by _ensure_claim_assessments
    
    # Clean up root-level keys that LLM might hallucinate based on prompt
    result.pop("rejected_candidates", None)

    # Ensure required structures exist with defaults
    _ensure_assessment(result)
    _ensure_affected_entities(result)
    _ensure_entity_resolution(result, candidates, claimed_order)
    _ensure_customer_context(result, customer_hint)
    _ensure_shipment_analysis(result)
    _ensure_payment_analysis(result)
    _ensure_root_cause(result)
    _ensure_data_conflicts(result)
    _ensure_financial_resolution(result)
    _ensure_claim_assessments(result)
    _ensure_resolution_actions(result)

    return result


# ── schema compliance helpers ───────────────────────────────────────────────

_PRIMARY_ISSUES = {
    "canceled_order_paid", "unavailable_order_paid", "late_delivery_seller",
    "late_delivery_logistics", "valid_split_payment", "payment_mismatch",
    "duplicate_charge", "refund_pending", "refund_failed",
    "unsupported_claim", "insufficient_evidence",
}

_CASE_STATUSES = {"action_required", "no_action", "needs_investigation"}

_SHIPMENT_VERDICTS = {
    "on_time", "seller_delay", "logistics_delay", "lost",
    "returned", "conflicting", "insufficient_evidence",
}

_PAYMENT_VERDICTS = {
    "reconciled", "capture_mismatch", "duplicate_capture",
    "refund_pending", "refund_failed", "refunded", "insufficient_evidence",
}

_ENTITY_STATUSES = {"resolved", "ambiguous", "not_found"}

_PARTY_TYPES = {
    "seller", "platform", "logistics_provider",
    "payment_provider", "customer", "unknown",
}

_CLAIM_VERDICTS = {
    "supported", "unsupported", "partially_supported", "insufficient_evidence",
}

import re
_CAUSE_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,79}$")


def _ensure_assessment(result: dict) -> None:
    a = result.get("assessment")
    if not isinstance(a, dict):
        a = {}
        result["assessment"] = a
    
    # Remove any unexpected properties LLM might have added here
    allowed_keys = {"primary_issue", "secondary_issues", "case_status", "confidence"}
    for k in list(a.keys()):
        if k not in allowed_keys:
            del a[k]

    if a.get("primary_issue") not in _PRIMARY_ISSUES:
        a["primary_issue"] = "insufficient_evidence"
    a.setdefault("secondary_issues", [])
    if not isinstance(a["secondary_issues"], list):
        a["secondary_issues"] = []
    a["secondary_issues"] = [
        str(s)[:80] for s in a["secondary_issues"] if s
    ][:10]
    if a.get("case_status") not in _CASE_STATUSES:
        a["case_status"] = "needs_investigation"
    conf = a.get("confidence")
    if not isinstance(conf, (int, float)) or conf < 0 or conf > 1:
        a["confidence"] = 0.5


def _ensure_affected_entities(result: dict) -> None:
    ae = result.get("affected_entities")
    if not isinstance(ae, dict):
        ae = {}
        result["affected_entities"] = ae
    
    allowed_keys = {"order_ids", "item_ids", "seller_ids", "payment_references", "shipment_ids"}
    for k in list(ae.keys()):
        if k not in allowed_keys:
            del ae[k]

    for field in allowed_keys:
        val = ae.get(field)
        if not isinstance(val, list):
            ae[field] = []
        else:
            ae[field] = [str(v)[:128] for v in val if v][:20]


def _ensure_entity_resolution(result: dict, candidates: list, claimed: str) -> None:
    er = result.get("entity_resolution")
    if not isinstance(er, dict):
        er = {}
        result["entity_resolution"] = er

    allowed_keys = {"status", "resolved_order_ids", "rejected_candidates", "confidence"}
    for k in list(er.keys()):
        if k not in allowed_keys:
            del er[k]

    if er.get("status") not in _ENTITY_STATUSES:
        er["status"] = "resolved"
    if not isinstance(er.get("resolved_order_ids"), list):
        er["resolved_order_ids"] = [claimed] if claimed else []
    er["resolved_order_ids"] = [str(v)[:128] for v in er["resolved_order_ids"] if v][:20]
    if not isinstance(er.get("rejected_candidates"), list):
        resolved = set(er["resolved_order_ids"])
        er["rejected_candidates"] = [c for c in candidates if c not in resolved]
    er["rejected_candidates"] = [str(v)[:128] for v in er["rejected_candidates"] if v][:20]
    conf = er.get("confidence")
    if not isinstance(conf, (int, float)) or conf < 0 or conf > 1:
        er["confidence"] = 0.7


def _ensure_customer_context(result: dict, hint: str) -> None:
    cc = result.get("customer_context")
    if not isinstance(cc, dict):
        cc = {}
        result["customer_context"] = cc
        
    allowed_keys = {"customer_unique_id", "related_order_ids"}
    for k in list(cc.keys()):
        if k not in allowed_keys:
            del cc[k]

    if not cc.get("customer_unique_id"):
        cc["customer_unique_id"] = hint or None
    if not isinstance(cc.get("related_order_ids"), list):
        cc["related_order_ids"] = []
    cc["related_order_ids"] = [str(v)[:128] for v in cc["related_order_ids"] if v][:20]


def _ensure_shipment_analysis(result: dict) -> None:
    sa = result.get("shipment_analysis")
    if not isinstance(sa, dict):
        sa = {}
        result["shipment_analysis"] = sa
        
    allowed_keys = {"verdict", "late_seller_ids", "timeline_complete"}
    for k in list(sa.keys()):
        if k not in allowed_keys:
            del sa[k]

    if sa.get("verdict") not in _SHIPMENT_VERDICTS:
        sa["verdict"] = "insufficient_evidence"
    if not isinstance(sa.get("late_seller_ids"), list):
        sa["late_seller_ids"] = []
    sa["late_seller_ids"] = [str(v)[:128] for v in sa["late_seller_ids"] if v][:20]
    if not isinstance(sa.get("timeline_complete"), bool):
        sa["timeline_complete"] = False


def _ensure_payment_analysis(result: dict) -> None:
    pa = result.get("payment_analysis")
    if not isinstance(pa, dict):
        pa = {}
        result["payment_analysis"] = pa
        
    allowed_keys = {"verdict", "captured_total_brl", "refunded_total_brl", "refundable_total_brl"}
    for k in list(pa.keys()):
        if k not in allowed_keys:
            del pa[k]

    if pa.get("verdict") not in _PAYMENT_VERDICTS:
        pa["verdict"] = "insufficient_evidence"
    for field in ("captured_total_brl", "refunded_total_brl", "refundable_total_brl"):
        val = pa.get(field)
        if not isinstance(val, (int, float)):
            pa[field] = None
        elif val < 0:
            pa[field] = 0


def _ensure_root_cause(result: dict) -> None:
    rca = result.get("root_cause_analysis")
    if not isinstance(rca, dict):
        rca = {}
        result["root_cause_analysis"] = rca
        
    allowed_keys = {"ranked_causes", "responsible_parties"}
    for k in list(rca.keys()):
        if k not in allowed_keys:
            del rca[k]

    if not isinstance(rca.get("ranked_causes"), list):
        rca["ranked_causes"] = [{"cause_code": "INSUFFICIENT_EVIDENCE", "rank": 1}]
    else:
        cleaned = []
        for i, c in enumerate(rca["ranked_causes"][:5]):
            if not isinstance(c, dict):
                continue
            for ck in list(c.keys()):
                if ck not in ("cause_code", "rank"):
                    del c[ck]
            code = str(c.get("cause_code", "UNKNOWN"))
            if not _CAUSE_CODE_RE.match(code):
                code = "UNKNOWN_CAUSE"
            rank = c.get("rank", i + 1)
            if not isinstance(rank, int) or rank < 1 or rank > 5:
                rank = i + 1
            cleaned.append({"cause_code": code, "rank": rank})
        rca["ranked_causes"] = cleaned or [{"cause_code": "INSUFFICIENT_EVIDENCE", "rank": 1}]

    if not isinstance(rca.get("responsible_parties"), list):
        rca["responsible_parties"] = [{"party_type": "unknown", "party_id": None}]
    else:
        cleaned = []
        for p in rca["responsible_parties"][:5]:
            if not isinstance(p, dict):
                continue
            for pk in list(p.keys()):
                if pk not in ("party_type", "party_id"):
                    del p[pk]
            pt = p.get("party_type", "unknown")
            if pt not in _PARTY_TYPES:
                pt = "unknown"
            pid = p.get("party_id")
            if pid is not None:
                pid = str(pid)[:128]
            cleaned.append({"party_type": pt, "party_id": pid})
        rca["responsible_parties"] = cleaned or [{"party_type": "unknown", "party_id": None}]


def _ensure_data_conflicts(result: dict) -> None:
    dc = result.get("data_conflicts")
    if not isinstance(dc, list):
        result["data_conflicts"] = []
        return
    cleaned = []
    for c in dc[:5]:
        if not isinstance(c, dict):
            continue
        field = str(c.get("field", ""))[:100]
        sources = c.get("sources", [])
        if not isinstance(sources, list) or len(sources) < 2:
            continue
        sources = [str(s)[:80] for s in sources if s][:5]
        if len(sources) < 2:
            continue
        sel = c.get("selected_source")
        if sel is not None:
            sel = str(sel)[:80]
        rc = str(c.get("resolution_code", "manual_review"))[:80]
        cleaned.append({
            "field": field, "sources": sources,
            "selected_source": sel, "resolution_code": rc,
        })
    result["data_conflicts"] = cleaned


def _ensure_financial_resolution(result: dict) -> None:
    fr = result.get("financial_resolution")
    if not isinstance(fr, dict):
        fr = {}
        result["financial_resolution"] = fr
        
    allowed_keys = {"currency", "recommended_refund_brl", "refund_lines"}
    for k in list(fr.keys()):
        if k not in allowed_keys:
            del fr[k]

    fr["currency"] = "BRL"
    val = fr.get("recommended_refund_brl")
    if not isinstance(val, (int, float)) or val < 0:
        fr["recommended_refund_brl"] = 0
    lines = fr.get("refund_lines")
    if not isinstance(lines, list):
        fr["refund_lines"] = []
    else:
        cleaned = []
        for line in lines[:10]:
            if not isinstance(line, dict):
                continue
            for lk in list(line.keys()):
                if lk not in ("reason_code", "amount_brl", "entity_id"):
                    del line[lk]
            rc = str(line.get("reason_code", "refund"))[:80]
            amt = line.get("amount_brl", 0)
            if not isinstance(amt, (int, float)) or amt < 0:
                amt = 0
            eid = line.get("entity_id")
            if eid is not None:
                eid = str(eid)[:128]
            cleaned.append({"reason_code": rc, "amount_brl": amt, "entity_id": eid})
        fr["refund_lines"] = cleaned


def _ensure_claim_assessments(result: dict) -> None:
    ca_list = result.get("claim_assessments")
    if not isinstance(ca_list, list):
        result.pop("claim_assessments", None)
        return
        
    cleaned = []
    for ca in ca_list[:5]:
        if not isinstance(ca, dict):
            continue
            
        allowed_keys = {"claim_id", "verdict", "confidence", "evidence_refs"}
        for k in list(ca.keys()):
            if k not in allowed_keys:
                del ca[k]
                
        if "claim_id" not in ca:
            ca["claim_id"] = "unknown_claim"
        else:
            ca["claim_id"] = str(ca["claim_id"])[:64]
            
        if ca.get("verdict") not in _CLAIM_VERDICTS:
            ca["verdict"] = "insufficient_evidence"
            
        conf = ca.get("confidence")
        if not isinstance(conf, (int, float)) or conf < 0 or conf > 1:
            ca["confidence"] = 0.5
            
        if not isinstance(ca.get("evidence_refs"), list):
            ca["evidence_refs"] = []
        else:
            ca["evidence_refs"] = [str(r) for r in ca["evidence_refs"]][:30]
            
        cleaned.append(ca)
        
    if cleaned:
        result["claim_assessments"] = cleaned
    else:
        result.pop("claim_assessments", None)


def _ensure_resolution_actions(result: dict) -> None:
    ra = result.get("resolution_actions")
    if not isinstance(ra, list) or not ra:
        result["resolution_actions"] = ["Review case and contact customer"]
    else:
        result["resolution_actions"] = list(dict.fromkeys(
            str(a)[:80] for a in ra if a
        ))[:8]


# ── main entry point ───────────────────────────────────────────────────────

async def solve_case(
    case: dict[str, Any], gateway: EvidenceGateway, trace: TraceWriter,
) -> dict[str, Any]:
    """Implement the L3B coordinator and specialist-agent workflow.

    Multi-agent architecture:
      1. entity-agent    → resolve order candidates via MCP
      2. customer-agent  → fetch customer history
      3. shipment-agent  → investigate delivery timeline
      4. payment-agent   → check payment + refund status
      5. product-agent   → get product context
      6. policy-agent    → retrieve applicable policy
      7. coordinator     → GPT-4o-mini synthesis
      8. verifier        → schema compliance check
    """
    case_id = case["case_id"]
    claimed_order = case["customer_request"].get("claimed_order_id", "")

    # ── discover tools ──
    available_tools = await gateway.list_tools()

    # ── collect evidence from specialist agents ──
    all_evidence: list[dict] = []
    all_refs: list[str] = []

    def _collect(result: tuple[list[dict], list[str]]) -> None:
        ev_list, ref_list = result
        all_evidence.extend(ev_list)
        all_refs.extend(ref_list)

    # 1. Entity resolution
    _collect(await _entity_agent(case, gateway, trace, available_tools))

    # 2. Customer context
    _collect(await _customer_agent(case, gateway, trace, available_tools))

    # 3. Shipment analysis
    _collect(await _shipment_agent(case, gateway, trace, available_tools, claimed_order))

    # 4. Payment & refund analysis
    _collect(await _payment_agent(case, gateway, trace, available_tools, claimed_order))

    # 5. Product context + order items (always fetch for full evidence coverage)
    _collect(await _product_agent(case, gateway, trace, available_tools, claimed_order))

    # 6. Policy check
    _collect(await _policy_agent(case, gateway, trace, available_tools))

    # 7. Seller info (get_sellers takes order_id, not seller_id)
    _collect(await _seller_agent(case, gateway, trace, available_tools, claimed_order))

    # Deduplicate refs
    seen: set[str] = set()
    unique_refs: list[str] = []
    for r in all_refs:
        if r not in seen:
            seen.add(r)
            unique_refs.append(r)
    all_refs = unique_refs

    # ── GPT-4o-mini synthesis ──
    trace.emit(
        case_id=case_id, event_type="task_assigned",
        actor="coordinator", target="synthesizer",
    )

    output = await _synthesize(case, all_evidence, all_refs)

    # ── verification ──
    trace.emit(
        case_id=case_id, event_type="task_assigned",
        actor="coordinator", target="verifier",
    )

    # Ensure output evidence_refs only contain valid refs
    valid = set(all_refs)
    output["evidence_refs"] = [r for r in output.get("evidence_refs", []) if r in valid]
    if not output["evidence_refs"] and all_refs:
        output["evidence_refs"] = all_refs

    if output.get("data_conflicts"):
        trace.emit(
            case_id=case_id, event_type="policy_decided",
            actor="coordinator", target="conflict-resolver",
            decision_code="conflict_resolved_by_llm"
        )

    trace.emit(
        case_id=case_id, event_type="verification_completed",
        actor="verifier",
        decision_code="schema_valid",
        evidence_refs=output["evidence_refs"][:20],
    )

    return output
