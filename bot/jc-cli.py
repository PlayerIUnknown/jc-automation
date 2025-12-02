#!/usr/bin/env python3
import os
import sys
import json
import asyncio
from typing import Any, Dict, List

from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

# ---------- env ---------- #

load_dotenv()

JC_MCP_URL = os.getenv("JC_MCP_URL", "https://mcp.jumpcloud.com/v1")
JC_API_KEY = os.getenv("JC_API_KEY")


def require_env():
    if not JC_API_KEY:
        print("ERROR: JC_API_KEY env var is not set", file=sys.stderr)
        sys.exit(1)
    if not JC_MCP_URL:
        print("ERROR: JC_MCP_URL env var is not set", file=sys.stderr)
        sys.exit(1)


# ---------- MCP call (search_api) ---------- #

async def _mcp_search_api(query: str) -> Any:
    headers = {
        "Authorization": f"Bearer {JC_API_KEY}",
    }

    async with streamablehttp_client(JC_MCP_URL, headers=headers) as (read, write, *_):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("search_api", arguments={"query": query})
            return result


def mcp_search_api_sync(query: str) -> Any:
    require_env()
    return asyncio.run(_mcp_search_api(query))


# ---------- formatting helpers (same logic as in Slack bot) ---------- #

def _extract_inner_json_from_search_api_result(result: Any) -> Dict[str, Any] | None:
    """
    Expected shape from search_api (your example):

    {
      "meta": null,
      "content": [
        {
          "type": "text",
          "text": "<JSON STRING HERE>",
          ...
        }
      ],
      "isError": false
    }
    """
    # 1) structuredContent, if present
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        return structured

    # 2) fall back to content[].text (JSON string)
    content = getattr(result, "content", None)
    if not content:
        return None

    for item in content:
        text_val = getattr(item, "text", None)
        if isinstance(text_val, str):
            try:
                inner = json.loads(text_val)
                if isinstance(inner, dict):
                    return inner
            except Exception:
                continue

    return None


def _format_search_api_results(inner: Dict[str, Any]) -> str:
    explanation = inner.get("explanation")
    rationale = inner.get("rationale")
    query_result = inner.get("query_result", {}) or {}
    metadata = query_result.get("metadata", {}) or {}
    results: List[Dict[str, Any]] = query_result.get("results", []) or []

    lines: List[str] = []

    if explanation:
        lines.append("Explanation:")
        lines.append(explanation)
        lines.append("")

    if rationale:
        lines.append(f"Why this query: {rationale}")
        lines.append("")

    qt = metadata.get("queryTime")
    if qt is not None:
        lines.append(f"Query time: {qt}")
        lines.append("")

    if not results:
        lines.append("No results found.")
        return "\n".join(lines)

    lines.append(f"Results (showing up to {min(len(results), 20)}):")
    MAX_ROWS = 20

    for row in results[:MAX_ROWS]:
        fields_list = row.get("fields", []) or []
        field_map: Dict[str, Any] = {}
        for f in fields_list:
            fname = f.get("field")
            fval = f.get("value")
            if fname:
                field_map[fname] = fval

        # Special-case user-type rows
        fname = field_map.get("user.first_name", "")
        lname = field_map.get("user.last_name", "")
        email = field_map.get("user.email")
        username = field_map.get("user.username")
        uid = field_map.get("user.id")

        if username or email or uid:
            pretty_name = (fname + " " + lname).strip()
            parts = []
            if username:
                parts.append(f"{username}")
            if pretty_name:
                parts.append(pretty_name)
            if email:
                parts.append(f"<{email}>")
            if uid:
                parts.append(f"id={uid}")
            lines.append(" - " + " | ".join(parts))
        else:
            # Generic row: print all fields
            field_parts = [f"{k}={v}" for k, v in field_map.items()]
            lines.append(" - " + "; ".join(field_parts))

    if len(results) > MAX_ROWS:
        lines.append(f"... plus {len(results) - MAX_ROWS} more")

    return "\n".join(lines)


def format_for_cli(user_query: str, result_obj: Any) -> str:
    inner = _extract_inner_json_from_search_api_result(result_obj)

    if inner is None:
        # Hard fallback: dump full JSON
        try:
            raw = result_obj.model_dump_json(indent=2)
        except Exception:
            raw = str(result_obj)
        return f"Query: {user_query}\n\nRaw search_api result:\n{raw}"

    body = _format_search_api_results(inner)
    return f"Query: {user_query}\n\n{body}"


# ---------- main ---------- #

def main():
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
    else:
        # interactive prompt
        print("Enter JumpCloud search_api query (Ctrl+C to exit):")
        query = input("> ").strip()
        if not query:
            print("No query provided.")
            return

    print(f"Running search_api for: {query!r} ...\n")
    result_obj = mcp_search_api_sync(query)
    msg = format_for_cli(query, result_obj)
    print(msg)


if __name__ == "__main__":
    main()
