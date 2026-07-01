"""Sales agent that drives Claude with the self-hosted Apollo MCP server.

The agent launches the Apollo MCP server (``apollo_mcp/server.py``) as a stdio
subprocess, exposes its tools to Claude, and runs a tool-use loop so Claude can
search for and enrich B2B leads to satisfy a natural-language request.

Usage::

    APOLLO_API_KEY=... ANTHROPIC_API_KEY=... \\
        python -m agent.sales_agent "Find 5 heads of RevOps at US Series B SaaS companies"

Credentials:
    - APOLLO_API_KEY   used by the MCP server (Apollo REST auth).
    - ANTHROPIC_API_KEY used by this agent. Alternatively run `ant auth login`;
      the Anthropic SDK will pick up the resulting profile automatically.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from anthropic import AsyncAnthropic
from anthropic.lib.tools.mcp import async_mcp_tool
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

MODEL = "claude-opus-4-8"
REPO_ROOT = Path(__file__).resolve().parent.parent

SYSTEM_PROMPT = """You are an expert sales development representative (SDR) assistant.

You have Apollo.io tools for finding and enriching B2B leads:
- search_people / search_organizations: find prospects and accounts by ICP filters.
- enrich_person / enrich_organization: get verified contact and firmographic data.
- organization_job_postings: surface hiring signals for an account.

Given a sales goal, plan which tools to call, gather the data, then return a
concise, well-structured result: a short list or table of leads with name,
title, company, email (and status), and a one-line reason each fits the goal.

Call tools when you need data; never fabricate contacts, emails, or companies.
When you have enough to answer, stop calling tools and summarize."""


async def run(goal: str, max_tokens: int = 8192) -> None:
    """Connect to the Apollo MCP server and run the agent loop for one goal."""
    if not os.environ.get("APOLLO_API_KEY"):
        print(
            "error: APOLLO_API_KEY is not set. Export your Apollo API key first.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        # The SDK also resolves `ant auth login` profiles, so warn rather than fail.
        print(
            "warning: ANTHROPIC_API_KEY not set; relying on ambient Anthropic "
            "credentials (e.g. an `ant auth login` profile).",
            file=sys.stderr,
        )

    client = AsyncAnthropic()

    # Launch the Apollo MCP server as a stdio subprocess. Passing the full
    # environment ensures APOLLO_API_KEY reaches the server process.
    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "apollo_mcp.server"],
        cwd=str(REPO_ROOT),
        env=os.environ.copy(),
    )

    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as mcp_client:
            await mcp_client.initialize()
            tools_result = await mcp_client.list_tools()

            runner = client.beta.messages.tool_runner(
                model=MODEL,
                max_tokens=max_tokens,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": goal}],
                tools=[async_mcp_tool(t, mcp_client) for t in tools_result.tools],
            )

            async for message in runner:
                for block in message.content:
                    if block.type == "text":
                        print(block.text)
                    elif block.type == "tool_use":
                        print(f"\n[calling {block.name} {block.input}]\n", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apollo-powered sales agent (Claude Opus 4.8 + Apollo MCP)."
    )
    parser.add_argument(
        "goal",
        nargs="+",
        help='Natural-language sales goal, e.g. "Find 5 CTOs at Berlin fintechs".',
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=8192,
        help="Max output tokens per model turn (default: 8192).",
    )
    args = parser.parse_args()
    asyncio.run(run(" ".join(args.goal), max_tokens=args.max_tokens))


if __name__ == "__main__":
    main()
