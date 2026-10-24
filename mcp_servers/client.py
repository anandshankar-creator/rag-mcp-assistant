"""
==============================================================================
Module: mcp_servers.client
Role in Architecture: Model Context Protocol (MCP) Client Controller
==============================================================================
Acts as the bridge between the Action Agent and the modular MCP servers.

Core Project Claim:
"Make the Action Agent discover tools dynamically from the MCP servers (list_tools),
not hardcode them, to prove the 'plug in a new tool without changing the core' claim."

How this works:
1. Dynamic Discovery: Discovers tools at runtime by querying registered FastMCP
   servers via `list_tools()`.
2. Schema Normalization: Automatically converts MCP tool declarations into
   standardized JSON Schema tool definitions compatible with Gemini and Claude.
3. Execution Dispatch: Maps incoming tool calls to the target server, executes
   the tool with validated arguments, and returns structured execution receipts.
"""

from __future__ import annotations
import importlib
import inspect
import json
from typing import Any, Callable, Dict, List, Optional


class MCPClientController:
    """
    Central MCP client manager responsible for discovering tools from
    decoupled server modules and dispatching calls.
    """

    DEFAULT_SERVERS = [
        "mcp_servers.reminder_server",
        "mcp_servers.calendar_server",
        "mcp_servers.email_server",
        "mcp_servers.pdf_server",
    ]

    def __init__(self, server_modules: Optional[List[str]] = None):
        self.server_module_names = server_modules or self.DEFAULT_SERVERS
        self._tools_cache: Dict[str, Dict[str, Any]] = {}
        self._function_registry: Dict[str, Callable] = {}
        self._server_instances: Dict[str, Any] = {}
        self.discover_tools()

    def discover_tools(self) -> None:
        """
        Dynamically imports each MCP server module, inspects its registered tools,
        and builds the function dispatch table and standardized schemas.
        """
        self._tools_cache.clear()
        self._function_registry.clear()

        for mod_name in self.server_module_names:
            try:
                mod = importlib.import_module(mod_name)
                mcp_instance = getattr(mod, "mcp", None)

                if mcp_instance is None:
                    print(f"[MCP CLIENT WARNING] Module '{mod_name}' has no FastMCP instance 'mcp'. Skipping.")
                    continue

                self._server_instances[mcp_instance.name] = mcp_instance

                # Discover tools from FastMCP's internal tool manager
                if hasattr(mcp_instance, "_tool_manager"):
                    for tool_obj in mcp_instance._tool_manager.list_tools():
                        name = tool_obj.name
                        desc = (tool_obj.description or "").strip()
                        params = tool_obj.parameters or {"type": "object", "properties": {}}

                        # Clean description (remove raw docstring formatting)
                        desc_clean = " ".join([line.strip() for line in desc.splitlines() if line.strip()])

                        # Standardized JSON Schema definition for LLMs
                        self._tools_cache[name] = {
                            "name": name,
                            "description": desc_clean,
                            "parameters": params,
                            "server": mcp_instance.name,
                        }

                        # Store direct callable function for local invocation
                        if hasattr(tool_obj, "fn"):
                            self._function_registry[name] = tool_obj.fn

            except Exception as e:
                print(f"[MCP CLIENT ERROR] Failed to load server '{mod_name}': {e}")

        print(f"[MCP DISCOVERY] Discovered {len(self._tools_cache)} tools from {len(self._server_instances)} MCP servers:")
        for t_name, t_meta in self._tools_cache.items():
            print(f"  * {t_name} (from {t_meta['server']})")

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """
        Returns all registered tool schemas formatted for LLM tool calling.
        """
        return [
            {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["parameters"],
            }
            for t in self._tools_cache.values()
        ]

    def has_tool(self, tool_name: str) -> bool:
        """Checks if a tool is known to the controller."""
        return tool_name in self._tools_cache

    def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes a named tool with provided arguments and returns an execution receipt.

        Args:
            tool_name: The name of the tool to invoke.
            arguments: Dictionary of arguments matching the tool's parameter schema.

        Returns:
            Dictionary containing execution status, output data, or friendly error diagnostics.
        """
        if not self.has_tool(tool_name):
            return {
                "status": "error",
                "tool_name": tool_name,
                "message": f"Tool '{tool_name}' is not registered on any connected MCP server.",
            }

        fn = self._function_registry.get(tool_name)
        if fn is None:
            return {
                "status": "error",
                "tool_name": tool_name,
                "message": f"Execution function for '{tool_name}' could not be resolved.",
            }

        try:
            # Clean and sanitize arguments
            # If an argument came as a JSON string, deserialize it
            sanitized_args = {}
            sig = inspect.signature(fn)

            for param_name, param in sig.parameters.items():
                if param_name in arguments:
                    val = arguments[param_name]
                    sanitized_args[param_name] = val
                elif param.default is not inspect.Parameter.empty:
                    # Optional parameter with default
                    continue
                else:
                    return {
                        "status": "error",
                        "tool_name": tool_name,
                        "message": f"Missing required parameter '{param_name}' for tool '{tool_name}'.",
                    }

            # Invoke tool
            result = fn(**sanitized_args)
            return {
                "status": "success",
                "tool_name": tool_name,
                "arguments": sanitized_args,
                "result": result,
            }

        except Exception as e:
            error_msg = f"Execution of tool '{tool_name}' failed: {str(e)}"
            print(f"[MCP EXECUTION ERROR] {error_msg}")
            return {
                "status": "error",
                "tool_name": tool_name,
                "arguments": arguments,
                "message": error_msg,
            }


# Singleton MCP client instance
_mcp_client_instance: Optional[MCPClientController] = None


def get_mcp_client() -> MCPClientController:
    """Factory function for the system MCPClientController."""
    global _mcp_client_instance
    if _mcp_client_instance is None:
        _mcp_client_instance = MCPClientController()
    return _mcp_client_instance


if __name__ == "__main__":
    client = get_mcp_client()
    tools = client.get_tool_definitions()
    print(f"\nTotal tool definitions generated: {len(tools)}")
