# sales_agent

A B2B sales agent wired to a **self-hosted Apollo.io MCP server**.

Two pieces, both in this repo:

1. **`apollo_mcp/`** — a self-hosted [Model Context Protocol](https://modelcontextprotocol.io)
   server that wraps the [Apollo.io](https://apollo.io) REST API (people/company
   search, enrichment, and hiring signals). It authenticates with your own
   Apollo API key, so nothing runs through a third party.
2. **`agent/`** — a sales agent that connects to that MCP server and drives
   **Claude Opus 4.8** through a tool-use loop to find and enrich leads from a
   natural-language request.

The same MCP server is also registered in **`.mcp.json`**, so you can use the
Apollo tools interactively inside Claude Code (or any MCP client) without the
agent.

## What the Apollo MCP server exposes

| Tool | Apollo endpoint | Purpose |
| --- | --- | --- |
| `search_people` | `POST /mixed_people/api_search` | Find net-new prospects by title, seniority, location, employer domain (free previews) |
| `enrich_person` | `POST /people/match` | Verified contact + firmographics for one person |
| `search_organizations` | `POST /mixed_companies/search` | Find accounts by domain, location, headcount |
| `enrich_organization` | `GET /organizations/enrich` | Firmographics for one company by domain |
| `organization_job_postings` | `GET /organizations/{id}/job_postings` | Active job postings (a hiring/buying signal) |

Auth is via the `X-Api-Key` header (Apollo's scheme), read from `APOLLO_API_KEY`.

### People Search: use the API endpoint + a master key

Apollo exposes two people-search paths, and picking the wrong one looks like a
plan limitation when it isn't. The server uses the official API endpoint
**`POST /mixed_people/api_search`** — *not* `/mixed_people/search`, which is
Apollo's internal web-app endpoint and returns `403 API_INACCESSIBLE` even on
paid plans. People Search works on the **Basic** plan, with two things to know:

- It requires a **master API key** — create one under **Apollo > Settings >
  Integrations > API** (a non-master key returns `403 API_INACCESSIBLE`, which
  the server surfaces as an explanatory error rather than a raw HTTP dump).
- Results are **free previews** (no credits): first name, obfuscated last name,
  title, employer, and email/phone availability flags. Reveal a prospect's real
  email and full name by passing their id (or name + domain) to `enrich_person`,
  which **does** consume credits.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in APOLLO_API_KEY (and ANTHROPIC_API_KEY)
```

- **`APOLLO_API_KEY`** — create one in Apollo under **Settings > Integrations > API**.
- **`ANTHROPIC_API_KEY`** — for the agent. Or run `ant auth login` and leave it unset.

Export the vars (for example `set -a; source .env; set +a`) before running.

## Run the sales agent

```bash
python -m agent.sales_agent "Find 5 heads of RevOps at US Series B SaaS companies"
```

Claude plans the Apollo calls, gathers the data, and prints a concise lead list.
Tool calls are logged to stderr so you can see what it queried.

## Use the Apollo tools inside Claude Code

`.mcp.json` registers the server for this project. With `APOLLO_API_KEY` exported
in the environment where you launch Claude Code (the `${APOLLO_API_KEY}`
placeholder expands from it), run `/mcp` to see the `apollo` server, approve it,
then ask things like *"search Apollo for VPs of Engineering at fintechs in NYC."*

> The server is launched as `python -m apollo_mcp.server` from the project root,
> so make sure your virtualenv (with `requirements.txt` installed) is active in
> that shell. If `python` isn't your venv interpreter, point `command` at it.

## Run the MCP server on its own

Useful for a quick smoke test or wiring into another MCP client:

```bash
APOLLO_API_KEY=... python -m apollo_mcp.server
```

It speaks MCP over stdio and waits for a client to connect.

## Notes

- `.env` is gitignored — keep your keys out of version control.
- Apollo search/enrich endpoints consume Apollo credits when they return data.
- Phone-number reveal (`enrich_person(reveal_phone_number=True)`) is processed
  asynchronously by Apollo and may require a configured webhook.

## Layout

```
sales_agent/
├── apollo_mcp/
│   └── server.py          # self-hosted Apollo MCP server (FastMCP, stdio)
├── agent/
│   └── sales_agent.py     # Claude Opus 4.8 agent that uses the MCP server
├── .mcp.json              # registers the Apollo server for MCP clients
├── requirements.txt
├── .env.example
└── README.md
```
