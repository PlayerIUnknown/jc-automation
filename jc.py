#!/usr/bin/env python3
import os
import sys
import argparse
import asyncio
from typing import Any, Dict

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


JC_MCP_URL = os.getenv("JC_MCP_URL", "https://mcp.jumpcloud.com/v1")
JC_API_KEY = os.getenv("JC_API_KEY")


# ----------------- shared helpers ----------------- #

def require_env():
    if not JC_API_KEY:
        print("ERROR: JC_API_KEY env var is not set", file=sys.stderr)
        sys.exit(1)
    if not JC_MCP_URL:
        print("ERROR: JC_MCP_URL env var is not set", file=sys.stderr)
        sys.exit(1)


def print_result(result: Any) -> None:
    """
    Best-effort pretty-print for MCP call_tool results.
    CallToolResult is a Pydantic model → model_dump_json works.
    """
    try:
        # For MCP Python SDK v1.9+, all models have model_dump_json
        print(result.model_dump_json(indent=2))
    except Exception:
        print(result)


async def with_session(run):
    """
    Open a JumpCloud MCP session, run the given coroutine with it, then close.
    """
    require_env()
    headers = {"Authorization": f"Bearer {JC_API_KEY}"}

    async with streamablehttp_client(JC_MCP_URL, headers=headers) as (read, write, *_):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await run(session)


# ----------------- commands (viewer-only tools) ----------------- #

async def cmd_tools(args: argparse.Namespace) -> None:
    async def inner(session: ClientSession):
        tools_resp = await session.list_tools()
        print("Available tools:")
        for tool in tools_resp.tools:
            line = f"- {tool.name}"
            if tool.description:
                line += f": {tool.description}"
            print(line)
    await with_session(inner)


# --- admins_list --- #

async def cmd_admins(args: argparse.Namespace) -> None:
    async def inner(session: ClientSession):
        arguments: Dict[str, Any] = {
            "limit": args.limit,
            "skip": args.skip,
            "search": args.search or "",
        }
        result = await session.call_tool("admins_list", arguments=arguments)
        print_result(result)
    await with_session(inner)


# --- users_list / user_get --- #

async def cmd_users(args: argparse.Namespace) -> None:
    async def inner(session: ClientSession):
        arguments: Dict[str, Any] = {
            "limit": args.limit,
            "skip": args.skip,
            "searchTerm": args.searchTerm or "",
        }
        result = await session.call_tool("users_list", arguments=arguments)
        print_result(result)
    await with_session(inner)


async def cmd_user_get(args: argparse.Namespace) -> None:
    async def inner(session: ClientSession):
        # schema: { "id": "user_id" }
        result = await session.call_tool("user_get", arguments={"id": args.id})
        print_result(result)
    await with_session(inner)


# --- user_groups_list / user_group_membership --- #

async def cmd_user_groups(args: argparse.Namespace) -> None:
    """
    Lists all user groups (not groups-for-user, but org-wide user groups).
    """
    async def inner(session: ClientSession):
        arguments: Dict[str, Any] = {
            "limit": args.limit,
            "skip": args.skip,
            "search": args.search or "",
            "disabled": args.disabled,
        }
        result = await session.call_tool("user_groups_list", arguments=arguments)
        print_result(result)
    await with_session(inner)


async def cmd_user_group_members(args: argparse.Namespace) -> None:
    """
    Lists users in a specific user group.
    """
    async def inner(session: ClientSession):
        arguments: Dict[str, Any] = {
            "group_id": args.group_id,
            "limit": args.limit,
            "skip": args.skip,
        }
        result = await session.call_tool("user_group_membership", arguments=arguments)
        print_result(result)
    await with_session(inner)


# --- applications_list / application_get --- #

async def cmd_apps(args: argparse.Namespace) -> None:
    async def inner(session: ClientSession):
        arguments: Dict[str, Any] = {
            "limit": args.limit,
            "skip": args.skip,
            "search": args.search or "",
        }
        result = await session.call_tool("applications_list", arguments=arguments)
        print_result(result)
    await with_session(inner)


async def cmd_app_get(args: argparse.Namespace) -> None:
    async def inner(session: ClientSession):
        result = await session.call_tool("application_get", arguments={"id": args.id})
        print_result(result)
    await with_session(inner)


# --- devices_list / device_get / device_groups_list / device_group_membership --- #

async def cmd_devices(args: argparse.Namespace) -> None:
    async def inner(session: ClientSession):
        arguments: Dict[str, Any] = {
            "limit": args.limit,
            "skip": args.skip,
            "search": args.search or "",
        }
        result = await session.call_tool("devices_list", arguments=arguments)
        print_result(result)
    await with_session(inner)


async def cmd_device_get(args: argparse.Namespace) -> None:
    async def inner(session: ClientSession):
        result = await session.call_tool("device_get", arguments={"id": args.id})
        print_result(result)
    await with_session(inner)


async def cmd_device_groups(args: argparse.Namespace) -> None:
    async def inner(session: ClientSession):
        arguments: Dict[str, Any] = {
            "limit": args.limit,
            "skip": args.skip,
            "search": args.search or "",
            "disabled": args.disabled,
        }
        result = await session.call_tool("device_groups_list", arguments=arguments)
        print_result(result)
    await with_session(inner)


async def cmd_device_group_members(args: argparse.Namespace) -> None:
    async def inner(session: ClientSession):
        arguments: Dict[str, Any] = {
            "group_id": args.group_id,
            "limit": args.limit,
            "skip": args.skip,
        }
        result = await session.call_tool("device_group_membership", arguments=arguments)
        print_result(result)
    await with_session(inner)


# --- commands & results --- #

async def cmd_commands(args: argparse.Namespace) -> None:
    async def inner(session: ClientSession):
        arguments: Dict[str, Any] = {
            "limit": args.limit,
            "skip": args.skip,
        }
        result = await session.call_tool("commands_list", arguments=arguments)
        print_result(result)
    await with_session(inner)


async def cmd_command_get(args: argparse.Namespace) -> None:
    async def inner(session: ClientSession):
        result = await session.call_tool("command_get", arguments={"id": args.id})
        print_result(result)
    await with_session(inner)


async def cmd_command_devices(args: argparse.Namespace) -> None:
    async def inner(session: ClientSession):
        arguments: Dict[str, Any] = {
            "id": args.id,
            "limit": args.limit,
            "skip": args.skip,
        }
        result = await session.call_tool("command_devices_list", arguments=arguments)
        print_result(result)
    await with_session(inner)


async def cmd_command_device_groups(args: argparse.Namespace) -> None:
    async def inner(session: ClientSession):
        arguments: Dict[str, Any] = {
            "id": args.id,
            "limit": args.limit,
            "skip": args.skip,
        }
        result = await session.call_tool("command_device_groups_list", arguments=arguments)
        print_result(result)
    await with_session(inner)


async def cmd_command_results(args: argparse.Namespace) -> None:
    async def inner(session: ClientSession):
        arguments: Dict[str, Any] = {
            "id": args.id,
            "limit": args.limit,
            "skip": args.skip,
        }
        result = await session.call_tool("command_result_list", arguments=arguments)
        print_result(result)
    await with_session(inner)


async def cmd_commandresults(args: argparse.Namespace) -> None:
    async def inner(session: ClientSession):
        arguments: Dict[str, Any] = {
            "limit": args.limit,
            "skip": args.skip,
        }
        result = await session.call_tool("commandresults_list", arguments=arguments)
        print_result(result)
    await with_session(inner)


# --- policies & software --- #

async def cmd_policies(args: argparse.Namespace) -> None:
    async def inner(session: ClientSession):
        arguments: Dict[str, Any] = {
            "limit": args.limit,
            "skip": args.skip,
            "search": args.search or "",
        }
        result = await session.call_tool("policies_list", arguments=arguments)
        print_result(result)
    await with_session(inner)


async def cmd_policy_get(args: argparse.Namespace) -> None:
    async def inner(session: ClientSession):
        result = await session.call_tool("policy_get", arguments={"id": args.id})
        print_result(result)
    await with_session(inner)


async def cmd_software(args: argparse.Namespace) -> None:
    async def inner(session: ClientSession):
        arguments: Dict[str, Any] = {
            "limit": args.limit,
            "skip": args.skip,
        }
        result = await session.call_tool("softwareapp_list", arguments=arguments)
        print_result(result)
    await with_session(inner)


# --- DI events --- #

async def cmd_di_events(args: argparse.Namespace) -> None:
    async def inner(session: ClientSession):
        arguments: Dict[str, Any] = {
            "limit": args.limit,
            "service": args.service,
            "event_type": args.event_type or "",
            "initiator_id": args.initiator_id or "",
            "query": args.query or "",
            "exact_match": args.exact_match or "",
            "start_time": args.start_time,
        }
        result = await session.call_tool("di_events_get", arguments=arguments)
        print_result(result)
    await with_session(inner)


# --- search_api (natural language) --- #

async def cmd_search_api(args: argparse.Namespace) -> None:
    async def inner(session: ClientSession):
        arguments: Dict[str, Any] = {
            "query": args.query,
        }
        result = await session.call_tool("search_api", arguments=arguments)
        print_result(result)
    await with_session(inner)


# ----------------- argparse wiring ----------------- #

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jc-mcp",
        description="JumpCloud MCP viewer-level CLI (using MCP Streamable HTTP).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # tools
    p_tools = sub.add_parser("tools", help="List MCP tools exposed by JumpCloud")
    p_tools.set_defaults(func=cmd_tools)

    # admins_list
    p_admins = sub.add_parser("admins", help="List JumpCloud console admins")
    p_admins.add_argument("--limit", type=int, default=10)
    p_admins.add_argument("--skip", type=int, default=0)
    p_admins.add_argument("--search", type=str, default="")
    p_admins.set_defaults(func=cmd_admins)

    # users_list
    p_users = sub.add_parser("users", help="List JumpCloud users")
    p_users.add_argument("--limit", type=int, default=10)
    p_users.add_argument("--skip", type=int, default=0)
    p_users.add_argument("--searchTerm", type=str, default="")
    p_users.set_defaults(func=cmd_users)

    # user_get
    p_user_get = sub.add_parser("user-get", help="Get a specific user by ID")
    p_user_get.add_argument("--id", required=True)
    p_user_get.set_defaults(func=cmd_user_get)

    # user_groups_list
    p_user_groups = sub.add_parser("user-groups", help="List all user groups")
    p_user_groups.add_argument("--limit", type=int, default=10)
    p_user_groups.add_argument("--skip", type=int, default=0)
    p_user_groups.add_argument("--search", type=str, default="")
    p_user_groups.add_argument("--disabled", action="store_true")
    p_user_groups.set_defaults(func=cmd_user_groups)

    # user_group_membership
    p_ugm = sub.add_parser("user-group-members", help="List members of a user group")
    p_ugm.add_argument("--group-id", required=True)
    p_ugm.add_argument("--limit", type=int, default=10)
    p_ugm.add_argument("--skip", type=int, default=0)
    p_ugm.set_defaults(func=cmd_user_group_members)

    # applications_list / application_get
    p_apps = sub.add_parser("apps", help="List SSO applications")
    p_apps.add_argument("--limit", type=int, default=10)
    p_apps.add_argument("--skip", type=int, default=0)
    p_apps.add_argument("--search", type=str, default="")
    p_apps.set_defaults(func=cmd_apps)

    p_app_get = sub.add_parser("app-get", help="Get a specific application by ID")
    p_app_get.add_argument("--id", required=True)
    p_app_get.set_defaults(func=cmd_app_get)

    # devices & device groups
    p_devices = sub.add_parser("devices", help="List devices")
    p_devices.add_argument("--limit", type=int, default=10)
    p_devices.add_argument("--skip", type=int, default=0)
    p_devices.add_argument("--search", type=str, default="")
    p_devices.set_defaults(func=cmd_devices)

    p_device_get = sub.add_parser("device-get", help="Get a device by ID")
    p_device_get.add_argument("--id", required=True)
    p_device_get.set_defaults(func=cmd_device_get)

    p_dgroups = sub.add_parser("device-groups", help="List device groups")
    p_dgroups.add_argument("--limit", type=int, default=10)
    p_dgroups.add_argument("--skip", type=int, default=0)
    p_dgroups.add_argument("--search", type=str, default="")
    p_dgroups.add_argument("--disabled", action="store_true")
    p_dgroups.set_defaults(func=cmd_device_groups)

    p_dgm = sub.add_parser("device-group-members", help="List members of a device group")
    p_dgm.add_argument("--group-id", required=True)
    p_dgm.add_argument("--limit", type=int, default=10)
    p_dgm.add_argument("--skip", type=int, default=0)
    p_dgm.set_defaults(func=cmd_device_group_members)

    # commands & results
    p_cmds = sub.add_parser("commands", help="List commands (scripts)")
    p_cmds.add_argument("--limit", type=int, default=10)
    p_cmds.add_argument("--skip", type=int, default=0)
    p_cmds.set_defaults(func=cmd_commands)

    p_cmd_get = sub.add_parser("command-get", help="Get a specific command by ID")
    p_cmd_get.add_argument("--id", required=True)
    p_cmd_get.set_defaults(func=cmd_command_get)

    p_cmd_dev = sub.add_parser("command-devices", help="List devices a command runs on")
    p_cmd_dev.add_argument("--id", required=True, help="Command ID")
    p_cmd_dev.add_argument("--limit", type=int, default=10)
    p_cmd_dev.add_argument("--skip", type=int, default=0)
    p_cmd_dev.set_defaults(func=cmd_command_devices)

    p_cmd_dg = sub.add_parser("command-device-groups", help="List device groups for a command")
    p_cmd_dg.add_argument("--id", required=True, help="Command ID")
    p_cmd_dg.add_argument("--limit", type=int, default=10)
    p_cmd_dg.add_argument("--skip", type=int, default=0)
    p_cmd_dg.set_defaults(func=cmd_command_device_groups)

    p_cmd_res = sub.add_parser("command-results", help="List results for a specific command")
    p_cmd_res.add_argument("--id", required=True, help="Command ID")
    p_cmd_res.add_argument("--limit", type=int, default=10)
    p_cmd_res.add_argument("--skip", type=int, default=0)
    p_cmd_res.set_defaults(func=cmd_command_results)

    p_cmdresults = sub.add_parser("commandresults", help="List recent command results across all commands")
    p_cmdresults.add_argument("--limit", type=int, default=10)
    p_cmdresults.add_argument("--skip", type=int, default=0)
    p_cmdresults.set_defaults(func=cmd_commandresults)

    # policies & software
    p_policies = sub.add_parser("policies", help="List security/configuration policies")
    p_policies.add_argument("--limit", type=int, default=10)
    p_policies.add_argument("--skip", type=int, default=0)
    p_policies.add_argument("--search", type=str, default="")
    p_policies.set_defaults(func=cmd_policies)

    p_policy_get = sub.add_parser("policy-get", help="Get a specific policy by ID")
    p_policy_get.add_argument("--id", required=True)
    p_policy_get.set_defaults(func=cmd_policy_get)

    p_software = sub.add_parser("software", help="List managed software applications")
    p_software.add_argument("--limit", type=int, default=10)
    p_software.add_argument("--skip", type=int, default=0)
    p_software.set_defaults(func=cmd_software)

    # DI events
    p_di = sub.add_parser("di-events", help="Fetch Directory Insights events (audit logs)")
    p_di.add_argument("--service", type=str, default="all",
                      help="Service (asset_management, sso, systems, all, etc.)")
    p_di.add_argument("--event-type", type=str, default="")
    p_di.add_argument("--initiator-id", type=str, default="")
    p_di.add_argument("--query", type=str, default="")
    p_di.add_argument("--exact-match", type=str, default="")
    p_di.add_argument("--start-time", type=str, default="7d",
                      help="Duration (e.g., 7d) or ISO8601 start time")
    p_di.add_argument("--limit", type=int, default=50)
    p_di.set_defaults(func=cmd_di_events)

    # search_api (natural language search/aggregation)
    p_search = sub.add_parser("search-api", help="Use AI-powered search_api with natural language")
    p_search.add_argument("query", type=str, help="Natural-language question")
    p_search.set_defaults(func=cmd_search_api)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    try:
        asyncio.run(args.func(args))
    except KeyboardInterrupt:
        print("\nInterrupted by user", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
