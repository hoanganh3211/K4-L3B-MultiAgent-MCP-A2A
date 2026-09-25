# L3B Architecture Record

Team phải cập nhật tài liệu này cùng source. Mục tiêu là mô tả quyết định có thể kiểm chứng, không ghi prompt bí mật hoặc chain-of-thought.

## 1. System overview

Hệ thống multi-agent lightweight sử dụng GPT-4o-mini làm reasoning engine, kết hợp deterministic MCP tool selection để thu thập bằng chứng.

```text
Input → Entity Resolver → Coordinator → Specialists → Conflict Resolver → Verifier → Output
            │                              │                  │             │
            └──────────────────────────── MCP ────────────────┴──────────── Trace
```

Luồng xử lý:
1. Coordinator nhận case, phân tích candidate_order_ids
2. Entity-agent gọi MCP `get_order_details` cho mỗi candidate để resolve
3. Customer-agent gọi `get_customer_history` theo `customer_unique_id_hint`
4. Shipment-agent gọi `get_shipment_details` cho resolved order
5. Payment-agent gọi `get_payment_details` + `get_refund_status`
6. Product-agent gọi `get_product_details` (nếu scope yêu cầu)
7. Policy-agent gọi `get_policy` với policy_version
8. Seller-agent gọi `get_seller_info` cho seller_id phát hiện từ order
9. Coordinator tổng hợp evidence, gửi đến GPT-4o-mini để phân tích
10. Verifier kiểm tra schema compliance, sanitize evidence_refs

## 2. Agent ownership

| Actor | Input | Trách nhiệm | Tool permission | Output/handoff |
| --- | --- | --- | --- | --- |
| Entity/customer | case, candidate_order_ids | Resolve đúng order từ candidates, reject fake candidates | get_order_details, get_customer_history | resolved_order_id, customer_context → coordinator |
| Coordinator | case + all evidence | Điều phối workflow, tổng hợp evidence, gọi LLM | N/A (orchestration only) | Final output |
| Order/product | order_id | Lấy chi tiết order và product | get_order_details, get_product_details | order_data, product_data → coordinator |
| Shipment | order_id | Kiểm tra timeline giao hàng | get_shipment_details | shipment_analysis → coordinator |
| Payment/refund | order_id | Kiểm tra payment, refund status | get_payment_details, get_refund_status | payment_analysis → coordinator |
| Policy | policy_version | Lấy policy áp dụng | get_policy | policy_data → coordinator |
| Seller | seller_id | Lấy thông tin seller | get_seller_info | seller_data → coordinator |
| Conflict resolver | all evidence | Phát hiện mâu thuẫn giữa sources | N/A | data_conflicts (handled by LLM) |
| Verifier | draft output | Schema compliance, evidence ref validation | N/A | validated output |

Áp dụng least privilege; mỗi agent chỉ gọi tool thuộc domain của mình.

## 3. Entity resolution và A2A protocol

- Xếp hạng candidate: Gọi `get_order_details` cho mỗi candidate_order_id.
  Candidate trả về valid order data = accepted; trả về error/null = rejected.
- Confidence threshold: resolved = 0.8+, ambiguous = 0.4-0.8, not_found < 0.4
- Message envelope: Mỗi agent nhận case_id + relevant data, trả tuple (evidence_list, evidence_refs)
- Correlation: Tất cả MCP calls đều truyền đúng case_id
- Handoff: Mỗi agent emit `task_assigned` khi bắt đầu, `handoff` khi hoàn thành
- Timeout: Dùng _safe_call wrapper, exception = None (skip)
- Tránh vòng lặp: Mỗi agent gọi tool tối đa 1-2 lần, không retry vô hạn

## 4. Evidence và conflict lifecycle

- Validate MCP response: Gateway tự validate theo mcp-evidence-response-v1 schema
- Lưu `evidence_ref`: Mỗi MCP response trả về evidence_ref, lưu vào all_refs list
- Chọn source: LLM phân tích conflict giữa sources, chọn source có authority cao nhất
- Unresolved conflict: Ghi vào data_conflicts với resolution_code = "manual_review"
- Map evidence → claim: LLM link evidence_refs với từng claim_assessment
- Emit `tool_result_consumed`: Ngay sau mỗi successful MCP call
- Evidence không tái sử dụng giữa các case (all_evidence reset mỗi case)

## 5. Failure and efficiency policy

| Failure | Retry budget | Fallback | Trace event/code |
| --- | ---: | --- | --- |
| MCP timeout | 0 (fail fast) | Return None, continue | tool_result_consumed not emitted |
| Entity not found/ambiguous | 0 | Use claimed_order_id as resolved | entity_resolved |
| Source conflict | 0 | Document in data_conflicts | policy_decided |
| Invalid specialist result | 0 | Use insufficient_evidence verdict | verification_completed |

Query budget: ~7-10 MCP calls per case (1-2 per agent).
Cache strategy: Evidence cached within case scope via all_evidence list.
No cross-case caching. No speculative/exploratory queries.

## 6. Verification invariants

Kiểm tra trước finalize:
- [ ] schema_version = "day09-l3b-output-v2"
- [ ] case_id matches input
- [ ] All evidence_refs exist in MCP responses (not fabricated)
- [ ] Entity resolution: rejected_candidates ∪ resolved_order_ids = candidate_order_ids
- [ ] evidence_refs in claim_assessments ⊆ output evidence_refs
- [ ] payment totals ≥ 0
- [ ] confidence ∈ [0, 1]
- [ ] primary_issue ∈ allowed enum values
- [ ] resolution_actions non-empty
- [ ] No API keys in output
- [ ] financial_resolution.currency = "BRL"

## 7. Reproducibility

- Model: OpenAI GPT-4o-mini, temperature=0.1
- Dependencies: openai>=3, httpx2>=2, mcp>=2, jsonschema>=4.25, python-dotenv>=1.1
- Concurrency: Sequential (1 case at a time)
- Random seed: N/A (deterministic MCP calls + near-deterministic LLM with temp=0.1)
- Lệnh chạy: `day09 run`
- Giới hạn: ~7-10 MCP calls/case, 1 LLM call/case (~4000 max_tokens)
- API key: OPENAI_API_KEY trong .env (không commit)
