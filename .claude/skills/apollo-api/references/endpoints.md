# Apollo API — endpoint reference

Base URL: `https://api.apollo.io/api/v1`. Auth header: `X-Api-Key: <key>`.
All request/response fields below are the ones this repo relies on; Apollo returns
many more. Credit rule everywhere: **0 credits if no qualifying data is returned.**

---

## People Search — `POST /mixed_people/api_search`

**Cost:** FREE. **Requires a master API key.** Returns *obfuscated previews* (no
revealed emails; last names may be masked). Enrich to reveal.

⚠️ Do **not** call `/mixed_people/search` (internal web endpoint → `403 API_INACCESSIBLE`).

Common filters (all optional, combine to narrow):
- `person_titles[]` — e.g. `["VP of Sales", "Head of Growth"]`
- `person_seniorities[]` — `owner, founder, c_suite, partner, vp, head, director, manager, senior, entry, intern`
- `person_locations[]` — where the person is based
- `organization_locations[]` — company HQ locations
- `q_organization_domains_list[]` — employer domains
- `q_organization_keyword_tags[]` — company keyword/industry tags (e.g. `["property management"]`)
- `q_keywords` — free-text
- `contact_email_status[]` — e.g. `["verified"]`
- `page`, `per_page` (max 100)

Response: `people[]` + `total_entries`. Each person: `id`, `first_name`,
`last_name_obfuscated`, `title`, `has_email`, `has_direct_phone`, `organization{...}`.
Display limit: 50,000 records (100/page × 500 pages).

---

## People Enrichment (Match) — `POST /people/match`

**Cost:** 1 credit per matched record with data (0 if not found). Reveals the real
email/name that People Search obfuscates.

Identifiers (provide any; more = better match):
- `id` (Apollo person id, e.g. from a People Search preview — most reliable)
- `email`, `hashed_email`
- `first_name` + `last_name` (or `name`) + `domain` or `organization_name`
- `linkedin_url`

Reveal flags:
- `reveal_personal_emails` (bool) — synchronous, may consume credits
- `reveal_phone_number` (bool) — **async**, **requires `webhook_url`**; results POSTed to
  the webhook after Apollo verifies (minutes). Draws `direct_dial_credit`.
- `run_waterfall_email`, `run_waterfall_phone` — cascade across Apollo's sources

Response: `person{ name, title, email, email_status, linkedin_url, city/state/country,
seniority, departments, employment_history[], organization{ ... , primary_phone } }`.
The org's main phone comes free here even without `reveal_phone_number`.

**Bulk:** `POST /people/bulk_match` — up to 10 people per call, 1 credit per enriched record.

---

## Organization Search — `POST /mixed_companies/search`

**Cost:** 1 credit per page when results are returned. (A count-only call with
`per_page=1` = 1 credit; read `total_entries`.)

Common filters:
- `q_organization_domains_list[]` — up to 1,000 domains/request
- `organization_locations[]`, `organization_not_locations[]`
- `organization_num_employees_ranges[]` — e.g. `["11,20","21,50"]`
- `revenue_range[min]`, `revenue_range[max]`
- `currently_using_any_of_technology_uids[]` — 1,500+ tech uids
- `q_organization_keyword_tags[]`, `q_organization_name`
- funding + job-posting filters
- `page`, `per_page` (max 100)

Response: `organizations[]` + `pagination`/`total_entries`. Display limit 50,000
(100/page × 500 pages). `429` on rate-limit.

---

## Organization Enrichment — `GET /organizations/enrich`

**Cost:** 1 credit per enriched record.

Params (≥1 required; more improves accuracy): `domain`, `linkedin_url`, `name`, `website`.

Returns firmographics: industry, `annual_revenue`, `estimated_num_employees`,
`founded_year`, funding rounds, `primary_phone`, location, `technology_names[]`,
`keywords[]`, headcount-growth (6/12/24-month), NAICS/SIC codes.

⚠️ **`annual_revenue` is spotty for private firms and the *bulk* call drops it.**
Measured on 11 private NY/NJ property-management firms: the single call returned
revenue for 6/11; the **bulk** call (`/organizations/bulk_enrich`) returned
`annual_revenue: null` for **all 11** even where the single call had it. When you
need revenue, enrich **one domain at a time** — don't batch. And treat the number
as a hint: two of nine populated figures were 10–50× low (a $2B-project developer
came back as `$212K`). Verify revenue-gated segments against a second source.

**Bulk:** `POST /organizations/bulk_enrich` — up to 10 companies per call. Fast for
headcount/industry/phone, but **omits `annual_revenue`** (see warning above).

---

## Job Postings — `GET /organizations/{organization_id}/job_postings`

**Cost:** consumes credits (conditional). A hiring/buying signal.
Returns `organization_job_postings[]`: `title`, `url`, `city/state/country`, `posted_at`.
Get `organization_id` from a search or enrich result.

---

## Free (non-credit) endpoints

Create/update/list/manage operations never consume credits: contacts, accounts, deals,
sequences (`emailer_campaigns`), tasks, calls, email accounts, users, custom fields.
These are how the hosted connector drives the *engagement/delivery* layer.

---

## Usage & rate limits — `GET /usage_stats/api_usage_stats`

Returns your per-endpoint rate limits (per minute/hour/day) and current usage. Rate
limits are fixed-window, per endpoint, and scale with plan; Apollo doesn't publish exact
numbers — read them here or from response headers. `429 Too Many Requests` on exceed.

Credit balances: `GET /usage_stats/credit_usage_stats` and the `users/api_profile`
endpoint (`num_credits_remaining`, per-type limits/consumed/left_over).

---

## Sources (docs.apollo.io)

- People API Search: https://docs.apollo.io/reference/people-api-search
- People Enrichment: https://docs.apollo.io/reference/people-enrichment
- Bulk People Enrichment: https://docs.apollo.io/reference/bulk-people-enrichment
- Organization Search: https://docs.apollo.io/reference/organization-search
- Organization Enrichment: https://docs.apollo.io/reference/organization-enrichment
- API pricing & credits: https://docs.apollo.io/docs/api-pricing
- Rate limits: https://docs.apollo.io/reference/rate-limits
- View API usage stats: https://docs.apollo.io/reference/view-api-usage-stats
- API FAQs: https://docs.apollo.io/docs/apollo-api-faqs

Costs marked "1 credit" reflect both Apollo's docs and this repo's own measured usage
(e.g. one `search_people` → `enrich_person` reveal = exactly 1 lead credit).
