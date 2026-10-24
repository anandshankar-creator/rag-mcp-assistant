# How to Add a New MCP Server in Under 10 Lines

One of the core academic claims of our architecture is that the personal assistant is **modular and tool-agnostic**. You can create a completely new capability without touching the core agent orchestration logic.

---

### Step 1: Create a New Server File (`mcp_servers/calculator_server.py`)

Create a python file with your tools decorated by `@mcp.tool()`:

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("calculator_server")

@mcp.tool()
def calculate_grade_pointer(marks: list[float], credits: list[int]) -> dict:
    """Calculates KTU SGPA from a list of course marks and credit weights."""
    total_credits = sum(credits)
    weighted_score = sum(m * c for m, c in zip(marks, credits))
    sgpa = round(weighted_score / total_credits / 10.0, 2)
    return {"sgpa": sgpa, "total_credits": total_credits}

if __name__ == "__main__":
    mcp.run()
```

*(That is only 8 lines of code!)*

---

### Step 2: Register the Server in `mcp_servers/client.py`

Open [`mcp_servers/client.py`](file:///D:/rag-mcp-assistant/mcp_servers/client.py) and append your new server name to `DEFAULT_SERVERS`:

```python
    DEFAULT_SERVERS = [
        "mcp_servers.reminder_server",
        "mcp_servers.calendar_server",
        "mcp_servers.email_server",
        "mcp_servers.pdf_server",
        "mcp_servers.calculator_server",  # <-- Added here
    ]
```

---

### That's It!
The **MCP Client Controller** automatically:
1. Detects `calculator_server` via dynamic reflection.
2. Extracts the function docstrings and typing hints into JSON Schemas.
3. Injects the new tool definition into Gemini/Claude's system context.
4. Routes incoming `calculate_grade_pointer` requests straight to your function.
