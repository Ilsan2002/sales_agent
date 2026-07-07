---
name: apollo-api
description: >-
  Apollo.io API and MCP usage for this repo — endpoint reference, credit costs,
  prospecting/enrichment workflows, rate limits, plan tiers, and the master-key
  and api_search gotchas that waste hours. Use whenever working with Apollo:
  the self-hosted apollo_mcp server (search_people, enrich_person,
  search_organizations, enrich_organization, organization_job_postings), the
  hosted Apollo connector, lead/prospect search, contact or company enrichment,
  revealing emails or phone numbers, or reasoning about Apollo credit
  consumption and cost per lead.
---

# Apollo.io API & MCP

How Apollo works in this repo: what each call does, **what it costs in credits**,
and the two gotchas that make People Search look "not included" when it is.

## Read this first — the 3 things that bite people

1. **Use `api_search`, not `search`, for People Search.** The official endpoint is
   `POST /api/v1/mixed_people/api_search`. The similarly named
   `/api/v1/mixed_people/search` is Apollo's *internal web-app* endpoint and returns
   `403 API_INACCESSIBLE` **even on paid plans**. This is the single most common
   "Apollo is broken / my plan is too low" false alarm.
2. **People Search requires a *master* API key.** A non-master key returns
   `403 API_INACCESSIBLE` on `api_search`. Create/enable one in Apollo →
   **Settings → Integrations → API** (toggle "master key"). A `401` means the key is
   wrong; a `403 API_INACCESSIBLE` means wrong endpoint or non-master key — not a plan
   limit.
3. **Search is free; reveals cost credits.** People Search returns *obfuscated
   previews* (first name, masked last name, title, employer, `has_email`/`has_phone`
   flags) for **0 credits**. You spend a credit only when you *enrich* to reveal the
   real email/name. So search wide for free, enrich only the shortlist.

## Access paths (same backend, same credits)

| Path | Auth | Where it runs | Notes |
|---|---|---|---|
| Raw REST API | API key (`X-Api-Key`) | your code | full control |
| **Self-hosted MCP** (`apollo_mcp/server.py`) | your API key (master) | this repo, stdio | 5 slim tools; use for the automated pipeline / headless workers |
| Hosted connector (`mcp.apollo.io`) | OAuth (Apollo login) | Apollo's servers | ~38 tools incl. sequences/campaigns/tasks; needs interactive auth (unreliable in cron) |

MCP is just an interface over the same API — it does **not** bypass credit costs, plan
gates, or the master-key requirement.

## Credit costs (the money table)

Credits are charged **only when qualifying data is returned** — the zero-credit rule:
**no match → 0 credits**, so you never pay for a miss.

| Operation | Endpoint | Method | Cost | This repo's tool |
|---|---|---|---|---|
| **People Search** (net-new prospects) | `/mixed_people/api_search` | POST | **FREE** (master key; previews only) | `search_people` |
| **People Enrichment** (reveal email/name) | `/people/match` | POST | **1 credit** / matched record | `enrich_person` |
| Bulk People Enrichment | `/people/bulk_match` | POST | 1 credit / record (≤10 per call) | — |
| **Organization Search** | `/mixed_companies/search` | POST | **1 credit / page** with results | `search_organizations` |
| **Organization Enrichment** | `/organizations/enrich` | GET | **1 credit** / record | `enrich_organization` |
| Bulk Org Enrichment | `/organizations/bulk_enrich` | POST | 1 credit / record (≤10 per call) | — |
| Job postings (hiring signals) | `/organizations/{id}/job_postings` | GET | consumes credits (conditional) | `organization_job_postings` |
| Manage contacts/accounts/deals/sequences/tasks/emailer | various | * | **FREE** (create/update/list) | (hosted connector) |

Key asymmetry to remember: **People search is free, Organization search is 1 credit/page.**
To just get a *count* of matching companies, one request (`per_page=1`) = **1 credit** total —
`total_entries` comes back regardless of how many match.

### Credit types (from the usage-stats endpoint)

- **`lead_credit`** — the main pool; person/org enrichment and email reveals draw here.
  Basic ≈ 2,565/month.
- **`direct_dial_credit`** — mobile/direct phone reveals (separate from lead credits).
- **`export_credit`, `conversation_credit`, `ai_credit`, `dialer`,
  `inbound_website_visitor_credit`** — feature-specific; mostly 0 on Basic.

### Phone reveal is special

Phone numbers via `/people/match` need `reveal_phone_number=true` **and** a
`webhook_url` — Apollo verifies phones **asynchronously** and POSTs results to the
webhook (can take minutes). It draws `direct_dial_credit`, not lead credits. The
*company* phone, by contrast, comes free inside a normal person/org enrichment.

## Rate limits

Fixed-window, **per endpoint**, per minute / hour / day, and they scale with your plan.
Apollo does **not** publish exact numbers — read them from response headers, from
**Settings → Integrations → API Usage**, or `GET /api/v1/usage_stats/api_usage_stats`.
Free-plan example: 50 / 200 / 600 per min/hour/day. Exceeding returns `429 Too Many
Requests` — back off and retry.

## Plans & API access

API access is on paid plans. **Basic (~$49–65/seat/mo)** already includes API
**enrichment + search** and ~2,565 lead credits/month — enough for the whole
search→enrich→send loop. Higher tiers add more credits and higher rate limits. People
Search only needs a *master key*, not a higher tier.

## Cost-smart workflows

- **Find + enrich one contact (1 credit total):** `search_people` (free) → pick a result
  with `email_available` → `enrich_person(person_id=…)` (1 credit). Sending via
  email/Gmail is 0 credits.
- **Build a list cheaply:** search (free for people) to gather candidates → enrich only
  the shortlist worth contacting; batch with the bulk endpoints (≤10/call).
- **Account brief:** `search_organizations` → `enrich_organization` → `job_postings`.
- **Need revenue? Enrich one org at a time.** `bulk_enrich` drops `annual_revenue`;
  the single `/organizations/enrich` returns it. Even then Apollo has revenue for only
  ~1/3 of private SMBs and is occasionally 10–50× off — verify revenue-gated segments.
- **Don't re-pay:** cache every enrichment in Postgres (see `ARCHITECTURE.md`) keyed by
  Apollo `id`/domain so the same contact is never enriched twice.
- **Protect deliverability:** Apollo's `email_status: "verified"` is a signal, not a
  guarantee — run a dedicated verifier (NeverBounce/MillionVerifier) before bulk sends.
- **Local SMBs:** for tiny local firms Apollo can be thin — Google Places often has
  better phone/address/review coverage; enrich the gaps in Apollo.

## This repo's tools

`apollo_mcp/server.py` exposes 5 stdio tools mapped in the table above. `enrich_person`
accepts a `person_id` so a `search_people` preview id enriches directly. The hosted
`Apollo_io` connector adds the engagement layer (sequences, campaigns, emailer, tasks),
which covers the *delivery* stage of `ARCHITECTURE.md`.

For full per-endpoint parameters, response shapes, and doc links, see
[`references/endpoints.md`](references/endpoints.md).
