"""
==============================================================================
Module: agents.action_agent
Role in Architecture: MCP Tool Selection & Execution Agent
==============================================================================
Empowers the assistant to take real-world actions via the Model Context Protocol (MCP).

Key Architectural Capabilities:
1. Dynamic Tool Discovery:
   Does NOT hardcode tool definitions. It calls `MCPClientController.get_tool_definitions()`
   at runtime, discovering all tools exposed by connected FastMCP servers.
2. Argument Validation:
   Translates student instructions into strictly typed arguments matching the tool schema.
3. Execution & Receipt Capture:
   Executes tools and returns clear action receipts (e.g. "Action performed: Reminder set for ...").
"""

from __future__ import annotations
import json
from typing import Any, Dict, List, Optional
from llm import get_llm_client, LLMResponse, ToolCall
from mcp_servers.client import get_mcp_client, MCPClientController

ACTION_SYSTEM_PROMPT = """You are the Action Agent for an AI personal assistant.
Your job is to select and execute the exact MCP tool that fulfills the user's action command.

Rules:
1. Inspect the provided tools carefully and call the single best tool for the user's request.
2. Formulate valid, required arguments (dates in YYYY-MM-DD HH:MM:SS format, valid emails, clean titles).
3. Always make a tool call when commanded to set a reminder, schedule an event, send an email, or generate a PDF."""


class ActionAgent:
    """Discovers MCP tools dynamically and executes them on behalf of the user."""

    def __init__(self, mcp_client: Optional[MCPClientController] = None, llm_client=None):
        self.mcp_client = mcp_client or get_mcp_client()
        self.llm = llm_client or get_llm_client()

    def run(
        self,
        user_message: str,
        user_preferences: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Executes a single-action command via MCP.
        """
        user_prefs = user_preferences or {}
        tools = self.mcp_client.get_tool_definitions()

        context_hint = (
            f"User Profile: Name={user_prefs.get('name', 'Alex')}, "
            f"Email={user_prefs.get('email', 'alex.student@ktu.edu.in')}, "
            f"Default Reminder Lead Time={user_prefs.get('default_reminder_lead_hours', '24')}h."
        )

        messages = [
            {"role": "system", "content": f"{ACTION_SYSTEM_PROMPT}\n{context_hint}"},
            {"role": "user", "content": user_message},
        ]

        # Call LLM with dynamically discovered MCP tools
        resp: LLMResponse = self.llm.generate(messages, tools=tools, temperature=0.1)

        executed_actions: List[Dict[str, Any]] = []

        if resp.has_tool_calls:
            for tc in resp.tool_calls:
                print(f"[ACTION AGENT] Calling MCP tool '{tc.name}' with args: {tc.arguments}")
                receipt = self.mcp_client.execute_tool(tc.name, tc.arguments)
                executed_actions.append({
                    "tool_name": tc.name,
                    "arguments": tc.arguments,
                    "receipt": receipt,
                })
        else:
            # Fallback: check if the LLM attempted to write out a tool call in text or JSON
            clean_text = resp.content.strip()
            print(f"[ACTION AGENT] Model returned text without structured tool call: {clean_text[:100]}...")

        # Compose user-facing confirmation
        if executed_actions:
            receipt = executed_actions[0]["receipt"]
            tool_name = executed_actions[0]["tool_name"]
            
            if receipt.get("status") == "success":
                raw_res = receipt.get("result")
                if isinstance(raw_res, dict):
                    inner_msg = raw_res.get("message") or raw_res.get("title") or f"Tool '{tool_name}' completed successfully."
                elif isinstance(raw_res, list):
                    if raw_res:
                        items_desc = []
                        for item in raw_res:
                            if isinstance(item, dict):
                                title = item.get("title") or item.get("name") or f"Item #{item.get('id', '')}"
                                time_info = f" (Time: {item.get('due_datetime') or item.get('start')})" if (item.get("due_datetime") or item.get("start")) else ""
                                items_desc.append(f"• {title}{time_info}")
                            else:
                                items_desc.append(f"• {item}")
                        inner_msg = f"Found {len(raw_res)} record(s):\n" + "\n".join(items_desc)
                    else:
                        inner_msg = "No scheduled records found."
                else:
                    inner_msg = str(raw_res) if raw_res else f"Tool '{tool_name}' completed successfully."
                action_summary = f"Action performed:\n{inner_msg}"
            else:
                action_summary = f"Action attempted ({tool_name}), but encountered an issue: {receipt.get('message')}"
        else:
            action_summary = "I understood your request, but could not determine which action tool to execute."

        return {
            "summary": action_summary,
            "actions": executed_actions,
            "raw_response": resp.content,
        }


# Global action agent singleton
_action_agent_instance = None


def get_action_agent() -> ActionAgent:
    global _action_agent_instance
    if _action_agent_instance is None:
        _action_agent_instance = ActionAgent()
    return _action_agent_instance


if __name__ == "__main__":
    agent = get_action_agent()
    print("Testing ActionAgent with 'Set a reminder tomorrow at 6 PM to revise OS'...")
    res = agent.run("Set a reminder tomorrow at 6 PM to revise OS")
    print(res["summary"])
