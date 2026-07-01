"""Self-hosted Apollo.io MCP server.

Exposes Apollo.io sales-intelligence endpoints (people/company search and
enrichment, hiring signals) as Model Context Protocol tools over stdio.

Authentication uses an Apollo API key supplied via the ``APOLLO_API_KEY``
environment variable and sent on the ``X-Api-Key`` header, per
https://docs.apollo.io/reference/authentication. Create a key in Apollo under
Settings > Integrations > API.

Run directly::

    APOLLO_API_KEY=... python -m apollo_mcp.server

or wire it into an MCP client (Claude Code, Cursor, ...) via ``.mcp.json``.
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

APOLLO_BASE_URL = "https://api.apollo.io/api/v1"
DEFAULT_TIMEOUT = 30.0
MAX_PER_PAGE = 100

mcp = FastMCP("apollo-io")


def _api_key() -> str:
    """Return the Apollo API key or raise a clear, actionable error."""
    key = os.environ.get("APOLLO_API_KEY")
    if not key:
        raise RuntimeError(
            "APOLLO_API_KEY is not set. Create an API key in Apollo "
            "(Settings > Integrations > API) and export it before calling any tool."
        )
    return key


def _request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Call the Apollo REST API and return the parsed JSON response."""
    headers = {
        "X-Api-Key": _api_key(),
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
        "accept": "application/json",
    }
    url = f"{APOLLO_BASE_URL}{path}"
    with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
        resp = client.request(
            method, url, headers=headers, params=params, json=json_body
        )
    if resp.status_code >= 400:
        # Surface a compact, actionable error the model can reason about.
        detail = resp.text[:500]
        raise RuntimeError(f"Apollo API {resp.status_code} on {path}: {detail}")
    return resp.json()


def _location(record: dict[str, Any]) -> str | None:
    parts = [record.get("city"), record.get("state"), record.get("country")]
    joined = ", ".join(p for p in parts if p)
    return joined or None


def _slim_person(person: dict[str, Any] | None) -> dict[str, Any] | None:
    """Trim a verbose Apollo person record to the fields sales work needs."""
    if not person:
        return None
    org = person.get("organization") or {}
    return {
        "id": person.get("id"),
        "name": person.get("name"),
        "title": person.get("title"),
        "seniority": person.get("seniority"),
        "email": person.get("email"),
        "email_status": person.get("email_status"),
        "linkedin_url": person.get("linkedin_url"),
        "location": _location(person),
        "organization": {
            "id": org.get("id"),
            "name": org.get("name"),
            "domain": org.get("primary_domain") or org.get("website_url"),
            "industry": org.get("industry"),
        },
    }


def _slim_org(org: dict[str, Any] | None) -> dict[str, Any] | None:
    """Trim a verbose Apollo organization record to the useful fields."""
    if not org:
        return None
    return {
        "id": org.get("id"),
        "name": org.get("name"),
        "domain": org.get("primary_domain") or org.get("website_url"),
        "industry": org.get("industry"),
        "employees": org.get("estimated_num_employees"),
        "location": _location(org),
        "linkedin_url": org.get("linkedin_url"),
        "short_description": org.get("short_description"),
    }


def _clamp_per_page(per_page: int) -> int:
    return max(1, min(per_page, MAX_PER_PAGE))


@mcp.tool()
def search_people(
    person_titles: list[str] | None = None,
    person_seniorities: list[str] | None = None,
    organization_domains: list[str] | None = None,
    person_locations: list[str] | None = None,
    organization_locations: list[str] | None = None,
    keywords: str | None = None,
    email_status: list[str] | None = None,
    page: int = 1,
    per_page: int = 10,
) -> str:
    """Search Apollo's database for people (prospects) matching an ICP.

    Use this to build a lead list. Combine filters to narrow results.

    Args:
        person_titles: Job titles to match, e.g. ["VP of Sales", "Head of Growth"].
        person_seniorities: Seniority tiers. Valid values: owner, founder,
            c_suite, partner, vp, head, director, manager, senior, entry, intern.
        organization_domains: Employer domains, e.g. ["stripe.com", "figma.com"].
        person_locations: Where the person is based, e.g. ["California, US"].
        organization_locations: Company HQ locations, e.g. ["United States"].
        keywords: Free-text keyword filter.
        email_status: Filter by email deliverability, e.g. ["verified"].
        page: 1-based page number.
        per_page: Results per page (max 100).

    Returns:
        JSON string with a trimmed "people" list and "pagination" metadata.
    """
    body: dict[str, Any] = {"page": page, "per_page": _clamp_per_page(per_page)}
    if person_titles:
        body["person_titles"] = person_titles
    if person_seniorities:
        body["person_seniorities"] = person_seniorities
    if organization_domains:
        body["q_organization_domains_list"] = organization_domains
    if person_locations:
        body["person_locations"] = person_locations
    if organization_locations:
        body["organization_locations"] = organization_locations
    if keywords:
        body["q_keywords"] = keywords
    if email_status:
        body["contact_email_status"] = email_status

    data = _request("POST", "/mixed_people/search", json_body=body)
    people = [_slim_person(p) for p in data.get("people", [])]
    return json.dumps(
        {"people": people, "pagination": data.get("pagination", {})}, indent=2
    )


@mcp.tool()
def enrich_person(
    first_name: str | None = None,
    last_name: str | None = None,
    name: str | None = None,
    email: str | None = None,
    domain: str | None = None,
    organization_name: str | None = None,
    linkedin_url: str | None = None,
    reveal_personal_emails: bool = False,
    reveal_phone_number: bool = False,
) -> str:
    """Enrich a single person, returning verified contact + firmographic data.

    Provide whatever identifiers you have (the more, the better the match):
    an email, a name plus a company domain, or a LinkedIn URL.

    Args:
        first_name: Person's first name.
        last_name: Person's last name.
        name: Full name (alternative to first_name/last_name).
        email: Known email address.
        domain: Employer domain, e.g. "apollo.io".
        organization_name: Employer name.
        linkedin_url: LinkedIn profile URL.
        reveal_personal_emails: Include personal emails (consumes credits).
        reveal_phone_number: Include phone numbers. Note: Apollo processes phone
            reveals asynchronously and may require a configured webhook.

    Returns:
        JSON string with the trimmed enriched person, or {"person": null}.
    """
    body: dict[str, Any] = {
        "reveal_personal_emails": reveal_personal_emails,
        "reveal_phone_number": reveal_phone_number,
    }
    candidates = {
        "first_name": first_name,
        "last_name": last_name,
        "name": name,
        "email": email,
        "domain": domain,
        "organization_name": organization_name,
        "linkedin_url": linkedin_url,
    }
    for key, value in candidates.items():
        if value:
            body[key] = value

    data = _request("POST", "/people/match", json_body=body)
    return json.dumps({"person": _slim_person(data.get("person"))}, indent=2)


@mcp.tool()
def search_organizations(
    organization_domains: list[str] | None = None,
    organization_locations: list[str] | None = None,
    num_employees_ranges: list[str] | None = None,
    keyword_tags: list[str] | None = None,
    organization_name: str | None = None,
    page: int = 1,
    per_page: int = 10,
) -> str:
    """Search Apollo for companies/accounts matching firmographic filters.

    Args:
        organization_domains: Company domains, e.g. ["stripe.com"].
        organization_locations: HQ locations, e.g. ["United States",
            "New York, US", "Illinois, US"].
        num_employees_ranges: Headcount bands, e.g. ["11,20", "21,50", "51,100"].
        keyword_tags: Company keywords; matches accounts whose industry tags or
            description contain ANY of these, e.g. ["freight", "trucking"].
        organization_name: Filter by company name.
        page: 1-based page number.
        per_page: Results per page (max 100).

    Returns:
        JSON string with a trimmed "organizations" list and "pagination".
    """
    body: dict[str, Any] = {"page": page, "per_page": _clamp_per_page(per_page)}
    if organization_domains:
        body["q_organization_domains_list"] = organization_domains
    if organization_locations:
        body["organization_locations"] = organization_locations
    if num_employees_ranges:
        body["organization_num_employees_ranges"] = num_employees_ranges
    if keyword_tags:
        body["q_organization_keyword_tags"] = keyword_tags
    if organization_name:
        body["q_organization_name"] = organization_name

    data = _request("POST", "/mixed_companies/search", json_body=body)
    orgs = [_slim_org(o) for o in data.get("organizations", [])]
    return json.dumps(
        {"organizations": orgs, "pagination": data.get("pagination", {})}, indent=2
    )


@mcp.tool()
def enrich_organization(domain: str) -> str:
    """Enrich a company by domain, returning firmographics.

    Args:
        domain: Company domain, e.g. "apollo.io".

    Returns:
        JSON string with the trimmed organization, or {"organization": null}.
    """
    data = _request("GET", "/organizations/enrich", params={"domain": domain})
    return json.dumps({"organization": _slim_org(data.get("organization"))}, indent=2)


@mcp.tool()
def organization_job_postings(organization_id: str) -> str:
    """List a company's active job postings (a hiring/buying signal).

    Args:
        organization_id: Apollo organization id (from a search/enrich result).

    Returns:
        JSON string with a "job_postings" list (title, url, location, posted_at).
    """
    data = _request("GET", f"/organizations/{organization_id}/job_postings")
    postings = [
        {
            "title": job.get("title"),
            "url": job.get("url"),
            "location": _location(job),
            "posted_at": job.get("posted_at"),
        }
        for job in data.get("organization_job_postings", [])
    ]
    return json.dumps({"job_postings": postings}, indent=2)


def main() -> None:
    """Run the server over stdio (the transport MCP clients expect)."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
