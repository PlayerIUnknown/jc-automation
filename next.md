Nice, now we’re in the fun zone 😄
You already have MCP working from CLI, so wiring a **Slack bot that just pipes IT admin questions → `search_api`** is straightforward.

We’ll:

1. Set expectations (what this bot does / doesn’t do)
2. Set up the Slack app
3. Configure env + deps
4. Drop in a complete `app.py` that:

   * checks IT admin’s Slack user ID
   * takes whatever text they type
   * calls `search_api` on JumpCloud MCP
   * posts the result back to Slack
5. Show how to run it locally with ngrok

---

## 1. What this bot will do

* Slash command: `/jc`

* IT admin types **any natural-language JumpCloud question**, e.g.:

  * `count users by group`
  * `show users created in last 7 days with AWS access`
  * `how do I create a policy for screen lock timeout`
  * `how many macOS devices are not encrypted`

* Bot will:

  * Check the caller is an allowed Slack user (IT admin).

  * Call **JumpCloud MCP `search_api`** with:

    ```json
    { "query": "<whatever they typed>" }
    ```

  * Return the raw structured result (pretty-printed JSON) inside Slack.

**No other tools** are used – just MCP `search_api` with your **viewer-level API key**.

---

## 2. Slack app setup

### 2.1 Create app

1. Go to Slack API → “Create New App → From scratch”.
2. Name it, e.g. `jc-search-bot`.
3. Choose your workspace.

### 2.2 Bot token scopes

In **OAuth & Permissions → Bot Token Scopes**, add:

* `commands` – to handle slash commands
* `chat:write` – to send replies

(You don’t *need* `users:read` since we’ll just use the Slack user ID from the command payload.)

Install the app to your workspace. Note:

* **Bot token** → `SLACK_BOT_TOKEN= xoxb-...`
* **Signing secret** → `SLACK_SIGNING_SECRET= ...`

### 2.3 Slash command

In **Slash Commands**:

* Command: `/jc`
* Request URL: `https://<your-host>/slack/events`
  (will be ngrok URL locally)
* Short description: `JumpCloud MCP search`
* Usage hint: `Ask any JumpCloud question`

Save.

---

## 3. Project structure & environment

Create a folder:

```text
jc-slack-search-bot/
  app.py
  requirements.txt
  .env            # local dev only
```

### 3.1 `requirements.txt`

```text
slack_bolt==1.22.0
slack_sdk==3.33.0
Flask==3.0.3
python-dotenv==1.0.1
mcp[cli]==1.9.4
```

Install:

```bash
cd jc-slack-search-bot
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3.2 `.env`

```env
# Slack
SLACK_BOT_TOKEN=xoxb-...
SLACK_SIGNING_SECRET=...

# JumpCloud MCP
JC_MCP_URL=https://mcp.jumpcloud.com/v1
JC_API_KEY=jca_xxxxxxxxxxxxxxxxx

# Only these Slack user IDs are allowed to use /jc
# (comma separated, no spaces)
ADMIN_USER_IDS=U012ABCDEF,U098ZYXWVU
```

To find your Slack user ID: in Slack → your profile → ⋯ → “Copy member ID”.

---

## 4. Full Slack bot code (`app.py`)

This:

* sets up Slack Bolt + Flask
* connects to MCP via Streamable HTTP
* defines `mcp_search_api_sync(query)` → calls `search_api`
* locks `/jc` to `ADMIN_USER_IDS`
* formats result as JSON inside a code block (truncated to avoid Slack length issues)

````python
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
````

---

## 5. Run locally with ngrok

1. Start the bot:

```bash
cd jc-slack-search-bot
source .venv/bin/activate
python app.py
# Flask is now on http://localhost:3000
```

2. Expose with ngrok:

```bash
ngrok http 3000
```

You’ll see something like:

```text
Forwarding  https://abc123.ngrok.io -> http://localhost:3000
```

3. In your Slack app config → **Slash Commands → /jc**:

* Set Request URL to:
  `https://abc123.ngrok.io/slack/events`
* Save.

4. In Slack, in a channel or DM where the app is installed:

```text
/jc count users by state (active, suspended, locked)
/jc show users created in the last 7 days with aws access
/jc how do I create a jumpcloud policy to enforce disk encryption on macos?
/jc show devices that have not checked in for more than 7 days
```

If your Slack user ID is in `ADMIN_USER_IDS`, you’ll see a JSON blob from `search_api` in response. If not, you’ll get the “not authorized” message.

---

## 6. Next steps you can add later

* Post-process the `search_api` JSON into **prettier Slack blocks** (tables, bullets).
* Log queries & responses (for audit).
* Add a second command `/jc-di` that wraps `di_events_get` directly.
* Eventually, reuse the **same MCP helper** in a web UI or CLI so everything shares one integration.

If you share an example `search_api` response JSON later, I can help you turn that into a nice Slack layout (e.g., counts, top-N items, summaries) instead of raw JSON.
