# Architecture

End-to-end pipeline for the B2B sales agent — from raw lead acquisition through
AI-driven research and copywriting to email delivery. Data flows top to bottom,
with **PostgreSQL** as the shared store every stage reads from and writes to.

```mermaid
flowchart TB
    subgraph DA["① Data acquisition"]
        direction LR
        LS["<b>Lead source</b><br/>Apollo · Firecrawl · Apify"]
        EN["<b>Enrichment</b><br/>fire-enrich (OSS) · PDL API"]
        WS["<b>Website scraping</b><br/>Firecrawl · Crawl4AI (OSS)"]
    end

    subgraph IA["② Intelligence agents — LangGraph + Claude Sonnet"]
        direction LR
        RE["<b>Research</b><br/>Company report"]
        SI["<b>Signals</b><br/>Hiring · reviews"]
        OP["<b>Opportunity</b><br/>Pain → solution"]
        RO["<b>ROI calc</b><br/>Savings model"]
        OF["<b>Offer</b><br/>Custom pitch"]
        OQ["<b>Outreach + QA</b><br/>Email + judge"]
    end

    subgraph OR["③ Orchestration — replaces n8n"]
        FA["<b>FastAPI</b><br/>API + webhooks"]
        CR["<b>Celery + Redis</b><br/>Async task queue"]
        PR["<b>Prefect</b><br/>Schedule + monitor"]
    end

    DB[("<b>PostgreSQL</b> — shared data store<br/>leads · enrichment · signals · copy · send status · opt-outs")]

    subgraph DE["④ Delivery"]
        direction LR
        SL["<b>Smartlead / Instantly</b><br/>Email sequences · warmup"]
        M3["<b>M365 mailboxes</b><br/>Dedicated sending domains"]
    end

    DA --> IA
    IA --> DB
    OR --> DB
    DB --> DE
    DE --> NEXT["⋯"]
    IA ~~~ OR
```

---

## ① Data acquisition

Pull prospects, enrich them into full firmographic/contact records, and scrape
each account's website for raw material the agents reason over.

| Component | Tools | Purpose |
| --- | --- | --- |
| **Lead source** | Apollo · Firecrawl · Apify | Discover prospects and accounts to target |
| **Enrichment** | fire-enrich (OSS) · PDL API | Fill in verified contact + firmographic data |
| **Website scraping** | Firecrawl · Crawl4AI (OSS) | Extract site content for downstream research |

## ② Intelligence agents

A **LangGraph** graph driving **Claude Sonnet**. Each node turns raw lead data
into a piece of the outreach: research → signals → opportunity → ROI → offer →
outreach, with a QA judge gating the final email.

| Agent | Output | Purpose |
| --- | --- | --- |
| **Research** | Company report | Synthesize a profile of the account |
| **Signals** | Hiring · reviews | Detect buying/timing signals |
| **Opportunity** | Pain → solution | Map a pain point to our solution |
| **ROI calc** | Savings model | Quantify the value / expected savings |
| **Offer** | Custom pitch | Build a tailored offer for the lead |
| **Outreach + QA** | Email + judge | Draft the email and judge it before send |

## ③ Orchestration

Replaces **n8n** with code-first orchestration — the API surface, the async work
queue, and the scheduler/monitor that keep the pipeline running.

| Component | Role | Purpose |
| --- | --- | --- |
| **FastAPI** | API + webhooks | Entry points and inbound event handling |
| **Celery + Redis** | Async task queue | Run long-running jobs off the request path |
| **Prefect** | Schedule + monitor | Schedule runs and observe pipeline health |

## PostgreSQL — shared data store

The single source of truth wired to every stage. Persists:

`leads` · `enrichment` · `signals` · `copy` · `send status` · `opt-outs`

## ④ Delivery

Send the approved copy through warmed-up inboxes on dedicated sending
infrastructure.

| Component | Role | Purpose |
| --- | --- | --- |
| **Smartlead / Instantly** | Email sequences · warmup | Run sequences and keep inboxes warm |
| **M365 mailboxes** | Dedicated sending domains | Isolated sending identities for deliverability |

---

> **(OSS)** marks open-source components. The pipeline continues past delivery
> (reply handling, analytics, feedback into the data store).
