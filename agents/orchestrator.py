"""
==============================================================================
Module: agents.orchestrator
Role in Architecture: Orchestrator & Intent Router Agent
==============================================================================
Classifies incoming student requests to select the optimal execution path
in our LangGraph state machine:
- `QA`: Knowledge retrieval grounded in uploaded documents (syllabus, notes, timetable).
- `ACTION`: Single real-world tool execution via MCP (reminder, calendar, email, PDF).
- `CHAINED`: Composite multi-step workflows requiring sequential coordination.
- `CHAT`: Open-domain conversation, chit-chat, or general knowledge (like ChatGPT/Gemini).

Academic Review Defense:
By routing intent before execution, we avoid running unnecessary RAG vector searches
on casual chatter or blind tool invocations, optimizing latency and precision.
"""

from __future__ import annotations
import json
import re
from typing import Dict, List, Optional
from llm import get_llm_client, LLMResponse

ROUTER_SYSTEM_PROMPT = """You are the Router for a personal AI assistant architecture.
Classify the user's latest message into exactly ONE of the following 4 categories:
1. "QA" - The user is asking a question about their private documents (university notes, course syllabus, internal exam timetable, lab deadlines, attendance policies, etc.).
2. "ACTION" - The user is commanding a single specific tool action (e.g. create a reminder, schedule a calendar event, send an email, generate a PDF).
3. "CHAINED" - The user is asking for a multi-step composite task that combines retrieval and actions (e.g. "Summarize my OS notes, make a PDF, email it to me, and remind me tomorrow").
4. "CHAT" - General conversation, greeting, general knowledge query, explanation of general programming concepts, or chit-chat.

Respond ONLY with a JSON object in this exact schema:
{
  "route": "QA" | "ACTION" | "CHAINED" | "CHAT",
  "reasoning": "brief explanation"
}"""


class OrchestratorRouter:
    """Classifies user intent using the configured LLM with rule-based fallback."""

    def __init__(self, llm_client=None):
        self.llm = llm_client or get_llm_client()

    def classify_intent(
        self,
        user_message: str,
        chat_history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, str]:
        """
        Determines the routing category for the user's request.
        """
        clean_msg = user_message.strip()

        # Quick heuristic pre-checks for fast routing
        lower_msg = clean_msg.lower()

        # Check for obvious chained indicators
        chained_signals = [
            ("summarize" in lower_msg or "retrieve" in lower_msg) and ("pdf" in lower_msg or "email" in lower_msg),
            ("make a pdf" in lower_msg and "remind" in lower_msg),
            ("and email it" in lower_msg and "and remind" in lower_msg),
        ]
        if any(chained_signals):
            return {
                "route": "CHAINED",
                "reasoning": "Detected multiple distinct actions combined with knowledge retrieval.",
            }

        # Prompt LLM for zero-shot intent classification
        messages = [
            {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
            {"role": "user", "content": f"User Message: {clean_msg}"},
        ]

        try:
            resp: LLMResponse = self.llm.generate(messages, temperature=0.0)
            raw = resp.content.strip()

            # Parse JSON
            match = re.search(r"\{.*?\}", raw, re.DOTALL)
            if match:
                parsed = json.loads(match.group(0))
                route = parsed.get("route", "").upper()
                if route in ("QA", "ACTION", "CHAINED", "CHAT"):
                    return {
                        "route": route,
                        "reasoning": parsed.get("reasoning", "Classified by LLM Router."),
                    }
        except Exception as e:
            print(f"[ROUTER WARNING] LLM classification fallback triggered: {e}")

        # Rule-based fallback
        if any(w in lower_msg for w in ["remind", "reminder", "alarm", "calendar", "event", "schedule", "send email", "email to", "make pdf", "create pdf"]):
            return {"route": "ACTION", "reasoning": "Keyword action rule triggered."}
        elif any(w in lower_msg for w in ["when is", "exam", "syllabus", "module", "unit", "notes", "attendance", "room", "venue", "submission"]):
            return {"route": "QA", "reasoning": "Keyword private document rule triggered."}
        else:
            return {"route": "CHAT", "reasoning": "Defaulting to general conversational assistant."}


# Global router singleton
_router_instance: Optional[OrchestratorRouter] = None


def get_router() -> OrchestratorRouter:
    global _router_instance
    if _router_instance is None:
        _router_instance = OrchestratorRouter()
    return _router_instance


if __name__ == "__main__":
    router = get_router()
    for test in [
        "What topics are covered in Unit 3 of OS?",
        "Set a reminder tomorrow at 6 PM to revise OS",
        "Summarize my OS notes, make a PDF, and email it to me",
        "Hello! How can you help me today?",
    ]:
        print(f"'{test}' -> {router.classify_intent(test)}")
