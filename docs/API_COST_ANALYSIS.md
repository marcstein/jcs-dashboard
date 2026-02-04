# Claude API Cost Analysis for LawMetrics.ai

## Document Generation Token Usage

### API Calls Per Document

A typical document generation involves these Claude API calls:

| Step | API Call | Input Tokens | Output Tokens | Notes |
|------|----------|--------------|---------------|-------|
| 1. Template Identification | `_identify_template()` | ~1,800 | ~150 | Includes DOCUMENT_TYPES list |
| 2. Variable Detection | `_analyze_template_for_variables()` | ~800 | ~400 | Skipped if using DOCUMENT_TYPES |
| 3. Value Extraction | `_extract_values_from_message()` | ~400 | ~100 | 1-2 calls typical |
| 4. Draft Generation | `_generate_draft()` | ~2,500 | ~2,000 | Main document generation |
| 5. Change Handling | `_understand_requested_changes()` | ~600 | ~200 | ~20% of documents need changes |

### Token Estimates Per Document

**Simple Document (Motion to Dismiss - General, using DOCUMENT_TYPES):**
- Input: ~4,700 tokens
- Output: ~2,250 tokens

**Complex Document (with template analysis + one revision):**
- Input: ~7,100 tokens
- Output: ~3,050 tokens

**Average Estimate:**
- Input: ~5,500 tokens per document
- Output: ~2,500 tokens per document

---

## Cost Projections

### Claude Sonnet 4 Pricing (as of 2025)
- Input: $3.00 per million tokens
- Output: $15.00 per million tokens

### JCS Law Firm (100 documents/week)

| Metric | Weekly | Monthly | Annually |
|--------|--------|---------|----------|
| Documents | 100 | 433 | 5,200 |
| Input Tokens | 550,000 | 2.38M | 28.6M |
| Output Tokens | 250,000 | 1.08M | 13.0M |
| **Input Cost** | $1.65 | $7.15 | $85.80 |
| **Output Cost** | $3.75 | $16.25 | $195.00 |
| **Total Cost** | **$5.40** | **$23.40** | **$280.80** |

### Cost Per Document
- **Average: $0.054 per document** (~5.4 cents)

---

## Scaling Projections

### By Firm Size

| Firm Size | Docs/Week | Monthly Cost | Annual Cost | Cost/Doc |
|-----------|-----------|--------------|-------------|----------|
| Solo (JCS) | 100 | $23 | $281 | $0.054 |
| Small (2-5 atty) | 300 | $70 | $843 | $0.054 |
| Medium (6-15 atty) | 750 | $176 | $2,107 | $0.054 |
| Large (16-50 atty) | 2,000 | $468 | $5,616 | $0.054 |

### Platform Scale (Multiple Firms)

| Firms | Total Docs/Week | Monthly API Cost | Annual API Cost |
|-------|-----------------|------------------|-----------------|
| 10 | 1,000 | $234 | $2,808 |
| 50 | 5,000 | $1,170 | $14,040 |
| 100 | 10,000 | $2,340 | $28,080 |
| 500 | 50,000 | $11,700 | $140,400 |

---

## Cost Optimization Strategies

### 1. Template Caching
- Cache `_identify_template()` results for common requests
- **Potential savings: 15-20%**

### 2. Use Haiku for Simple Tasks
- Template identification → Haiku ($0.25/$1.25 per M tokens)
- Value extraction → Haiku
- Keep Sonnet only for draft generation
- **Potential savings: 30-40%**

### 3. Batch Processing
- Anthropic batch API: 50% discount
- Queue non-urgent documents for batch processing
- **Potential savings: 50% on batched work**

### 4. Pre-built Templates
- Use more `DOCUMENT_TYPES` definitions
- Skip `_analyze_template_for_variables()` call
- **Potential savings: 10-15%**

---

## Optimized Cost Projections

### With Haiku for Preprocessing

| Step | Model | Input $/M | Output $/M |
|------|-------|-----------|------------|
| Template ID | Haiku | $0.25 | $1.25 |
| Variable Detection | Haiku | $0.25 | $1.25 |
| Value Extraction | Haiku | $0.25 | $1.25 |
| Draft Generation | Sonnet | $3.00 | $15.00 |

**Optimized Cost Per Document:** ~$0.035 (3.5 cents)

### With Batch API (50% discount on Sonnet)

**Batch Cost Per Document:** ~$0.027 (2.7 cents)

---

## Revenue Model Considerations

### Suggested Pricing Tiers

| Tier | Docs/Month | Price/Month | API Cost | Gross Margin |
|------|------------|-------------|----------|--------------|
| Starter | 100 | $49 | $5 | 90% |
| Professional | 500 | $149 | $27 | 82% |
| Business | 2,000 | $399 | $108 | 73% |
| Enterprise | Unlimited | Custom | Variable | 60-70% |

### Break-Even Analysis
- At $0.054/doc cost, break-even at any price > $0.06/doc
- $49/month for 100 docs = $0.49/doc → 89% margin
- $149/month for 500 docs = $0.30/doc → 82% margin

---

## Summary

| Metric | Value |
|--------|-------|
| **Cost per document (current)** | $0.054 |
| **Cost per document (optimized)** | $0.027-$0.035 |
| **JCS monthly cost** | $23.40 |
| **JCS annual cost** | $280.80 |
| **Recommended pricing** | $49-149/month |
| **Expected gross margin** | 80-90% |

The API costs are very manageable. At current pricing, the system can generate documents for approximately **5 cents each**, leaving substantial room for profitable pricing.
