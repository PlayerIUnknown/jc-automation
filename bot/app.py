#!/usr/bin/env python3
import os
import asyncio
import json
from typing import Any, Dict

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


def mcp_search_api_sync(query: str) -> str:
    """
    Synchronous wrapper so we can call MCP from Slack handler.
    Returns a pretty-printed JSON string to send back to Slack.
    """
    result = asyncio.run(_mcp_search_api(query))

    # Try to use structuredContent if present
    structured = getattr(result, "structuredContent", None)
    if structured is not None:
        return json.dumps(structured, indent=2)

    # Fallback: generic model_dump_json
    try:
        return result.model_dump_json(indent=2)
    except Exception:
        return str(result)


def is_admin(slack_user_id: str) -> bool:
    return slack_user_id in ADMIN_USER_IDS


# ----------------- Slack command: /jc ----------------- #

@app.command("/jc")
def handle_jc_command(ack, body, respond):
    """
    /jc <any JumpCloud question>

    Example:
    /jc count users by group
    /jc show users created in last 7 days with aws access
    /jc how do I create a policy to enforce screen lock?
    """
    ack()  # acknowledge immediately to avoid timeout

    user_id = body.get("user_id")
    if not user_id or not is_admin(user_id):
        respond(":no_entry: You are not authorized to use this JumpCloud search bot.")
        return

    text = (body.get("text") or "").strip()
    if not text:
        respond("Please provide a question, e.g. `/jc count users by group`.")
        return

    try:
        # Call JumpCloud MCP search_api
        raw_json = mcp_search_api_sync(text)

        # Slack has message length limits; be defensive
        MAX_LEN = 2800  # stay under 3000 to be safe
        if len(raw_json) > MAX_LEN:
            truncated = raw_json[:MAX_LEN] + "\n... (truncated)"
        else:
            truncated = raw_json

        respond(
            f"*Query:* `{text}`\n"
            f"*search_api result:*\n"
            f"```json\n{truncated}\n```"
        )

    except Exception as e:
        respond(f":warning: Error while calling JumpCloud MCP `search_api`: `{e}`")


# ----------------- Flask route for Slack events ----------------- #

@flask_app.route("/slack/events", methods=["POST"])
def slack_events():
    return handler.handle(request)


if __name__ == "__main__":
    flask_app.run(host="0.0.0.0", port=int(os.getenv("PORT", "3000")), debug=True)
