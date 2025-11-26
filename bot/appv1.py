#!/usr/bin/env python3
import os
import asyncio
import json
from typing import Any, Dict, List

from dotenv import load_dotenv

from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
from flask import Flask, request

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

# ----------------- Env & config ----------------- #

load_dotenv()

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")

JC_MCP_URL = os.getenv("JC_MCP_URL", "https://mcp.jumpcloud.com/v1")
JC_API_KEY = os.getenv("JC_API_KEY")

if not SLACK_BOT_TOKEN or not SLACK_SIGNING_SECRET:
    raise RuntimeError("SLACK_BOT_TOKEN and SLACK_SIGNING_SECRET must be set")

if not JC_API_KEY:
    raise RuntimeError("JC_API_KEY (JumpCloud jca_ key) must be set")

# Comma-separated Slack user IDs
ADMIN_USER_IDS = {
    uid.strip()
    for uid in (os.getenv("ADMIN_USER_IDS") or "").split(",")
    if uid.strip()
}
if not ADMIN_USER_IDS:
    print("WARNING: ADMIN_USER_IDS is empty. Nobody will be authorized to use /jc.")

# ----------------- Slack app & Flask wiring ----------------- #

app = App(token=SLACK_BOT_TOKEN, signing_secret=SLACK_SIGNING_SECRET)
flask_app = Flask(__name__)
handler = SlackRequestHandler(app)


# ----------------- MCP helper (search_api only) ----------------- #

async def _mcp_search_api(query: str) -> Any:
    """
    Call JumpCloud MCP search_api tool with the given natural-language query.
    """
    headers = {
        "Authorization": f"Bearer {JC_API_KEY}",
    }

    async with streamablehttp_client(JC_MCP_URL, headers=headers) as (read, write, *_):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("search_api", arguments={"query": query})
            return result


def mcp_search_api_sync(query: str) -> Any:
    """
    Synchronous wrapper returning the raw CallToolResult object.
    """
    return asyncio.run(_mcp_search_api(query))


def is_admin(slack_user_id: str) -> bool:
    return slack_user_id in ADMIN_USER_IDS


# ----------------- Formatting helpers ----------------- #

def _extract_inner_json_from_search_api_result(result: Any) -> Dict[str, Any] | None:
    """
    Your search_api result currently looks like:

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

    This tries to grab that inner JSON string and parse it.
    """
    # 1) Try structuredContent first (future-proof)
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        return structured

    # 2) Fall back to content[].text
    content = getattr(result, "content", None)
    if not content:
        return None

    for item in content:
        text_val = getattr(item, "text", None)
        if isinstance(text_val, str):
            # The text itself is a JSON string
            try:
                inner = json.loads(text_val)
                if isinstance(inner, dict):
                    return inner
            except Exception:
                # not JSON, ignore and continue
                continue

    return None


def _format_search_api_results(inner: Dict[str, Any]) -> str:
    """
    Takes the parsed inner JSON from search_api and produces friendly Slack markdown.

    Expected shape (from your sample):

    {
      "explanation": "...",
      "query_result": {
        "metadata": { "queryTime": ..., "schema": [...] },
        "results": [
          {
            "fields": [
              {"field": "user.first_name", "value": "Akash"},
              ...
            ],
            "itemnum": 1
          }
        ]
      },
      "rationale": "...",
      "search_query": {...},
      "type": "dsl"
    }
    """
    explanation = inner.get("explanation")
    rationale = inner.get("rationale")
    query_result = inner.get("query_result", {}) or {}
    metadata = query_result.get("metadata", {}) or {}
    results: List[Dict[str, Any]] = query_result.get("results", []) or []

    lines: List[str] = []

    if explanation:
        lines.append(f"*Explanation:*\n{explanation}\n")

    if rationale:
        lines.append(f"*Why this query:* {rationale}\n")

    # Small metadata bits
    qt = metadata.get("queryTime")
    if qt is not None:
        lines.append(f"_Query time_: `{qt}`\n")

    if not results:
        lines.append("_No results found._")
        return "\n".join(lines)

    lines.append(f"*Results* (showing up to {min(len(results), 20)}):")

    # Limit to first N to avoid huge Slack messages
    MAX_ROWS = 20
    for row in results[:MAX_ROWS]:
        fields_list = row.get("fields", []) or []
        # Turn [{"field": "...", "value": "..."}] into dict
        field_map: Dict[str, Any] = {}
        for f in fields_list:
            fname = f.get("field")
            fval = f.get("value")
            if fname:
                field_map[fname] = fval

        # Try to special-case user-type rows for nicer display
        fname = field_map.get("user.first_name", "")
        lname = field_map.get("user.last_name", "")
        email = field_map.get("user.email")
        username = field_map.get("user.username")
        uid = field_map.get("user.id")

        if username or email or uid:
            # Pretty user line
            pretty_name = (fname + " " + lname).strip()
            parts = []
            if username:
                parts.append(f"`{username}`")
            if pretty_name:
                parts.append(pretty_name)
            if email:
                parts.append(f"<{email}>")
            if uid:
                parts.append(f"_id: `{uid}`_")

            lines.append("• " + " – ".join(parts))
        else:
            # Generic: show all fields for this row
            field_parts = [
                f"*{k}*: `{v}`"
                for k, v in field_map.items()
            ]
            lines.append("• " + "; ".join(field_parts))

    # If there are more results than MAX_ROWS, hint about truncation
    if len(results) > MAX_ROWS:
        lines.append(f"\n_… plus {len(results) - MAX_ROWS} more results_")

    return "\n".join(lines)


def format_search_api_slack_message(user_query: str, result_obj: Any) -> str:
    """
    Build the final Slack markdown for a given user query + MCP result.
    Tries to parse inner JSON and present nicely; falls back to JSON dump if needed.
    """
    inner = _extract_inner_json_from_search_api_result(result_obj)

    if inner is None:
        # Hard fallback: dump the whole MCP CallToolResult JSON
        try:
            raw = result_obj.model_dump_json(indent=2)
        except Exception:
            raw = str(result_obj)
        return (
            f"*Query:* `{user_query}`\n"
            f"Could not parse structured search_api result, showing raw data:\n"
            f"```json\n{raw[:2700]}\n```"
        )

    formatted = _format_search_api_results(inner)
    return f"*Query:* `{user_query}`\n\n{formatted}"


# ----------------- Slack command: /jc ----------------- #

@app.command("/jc")
def handle_jc_command(ack, body, respond):
    """
    /jc <any JumpCloud question>

    Example:
    /jc show users starting with akash
    /jc how many macos devices are not encrypted
    """
    # Immediately acknowledge to avoid Slack timeout
    ack()

    user_id = body.get("user_id")
    if not user_id or not is_admin(user_id):
        respond(":no_entry: You are not authorized to use this JumpCloud search bot.")
        return

    text = (body.get("text") or "").strip()
    if not text:
        respond("Please provide a question, e.g. `/jc count users by group`.")
        return

    # Send quick "working" message so user sees something immediately
    respond(f"⏳ Working on your JumpCloud query: `{text}` …")

    try:
        # Call JumpCloud MCP search_api
        result_obj = mcp_search_api_sync(text)

        msg = format_search_api_slack_message(text, result_obj)

        # Send the final, formatted response
        respond(msg)

    except Exception as e:
        respond(f":warning: Error while calling JumpCloud MCP `search_api`: `{e}`")


# ----------------- Flask route for Slack events ----------------- #

@flask_app.route("/slack/events", methods=["POST"])
def slack_events():
    return handler.handle(request)


if __name__ == "__main__":
    flask_app.run(host="0.0.0.0", port=int(os.getenv("PORT", "3000")), debug=True)
