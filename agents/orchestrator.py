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

ROUTER_SYSTEM_PROMPT = """You are the Router for an intelligent, evidence-grounded personal AI assistant.
Classify the user's latest message into exactly ONE of the following 4 categories:
1. "QA" - All factual, conceptual, technical, or knowledge inquiries (e.g. definitions, algorithms like "What is Belady's anomaly?", course questions, syllabus, exam dates, deadlines, or general knowledge questions). All knowledge questions MUST be routed to QA so local documents and verified grounding are checked first.
2. "ACTION" - The user is commanding a specific real-world tool action (e.g. create a reminder, schedule a calendar event, send an email, generate a PDF).
3. "CHAINED" - The user is asking for a multi-step composite task combining retrieval, synthesis, and actions (e.g. "Summarize my notes, make a PDF, email it to me, and remind me tomorrow").
4. "CHAT" - Pure social greetings (hello, hi, hey), personal pleasantries, or casual chit-chat that does NOT ask for factual or conceptual knowledge retrieval.

Respond ONLY with a JSON object in this exact schema:
{
  "route": "QA" | "ACTION" | "CHAINED" | "CHAT",
  "reasoning": "brief explanation"
}"""


def is_profile_query(user_msg: str) -> bool:
    """Detects inquiries about student profile, configured email, or user identity."""
    clean = user_msg.lower().strip()
    if any(w in clean for w in ["send", "write", "draft", "compose", "update", "change"]):
        return False

    email_signals = [
        "what is my email",
        "whats my email",
        "what's my email",
        "my email id",
        "my email address",
        "tell me my email",
        "which email",
        "what email do you have",
        "what email",
        "my email",
    ]
    if any(sig in clean for sig in email_signals):
        return True

    identity_signals = [
        "who am i",
        "what is my name",
        "whats my name",
        "what's my name",
        "my profile",
        "my user profile",
        "my account details",
        "my student id",
    ]
    return any(sig in clean for sig in identity_signals)


def is_action_followup_query(user_msg: str) -> bool:
    """Detects meta-inquiries about how actions were performed or whether an action completed."""
    clean = user_msg.lower().strip()
    followup_signals = [
        "how did you send",
        "how was that sent",
        "did you send the email",
        "did you actually send",
        "how did you send emails",
        "was the email sent",
        "what happened to the email",
        "how did you schedule",
        "did you schedule that",
        "what action did you take",
        "what did you just do",
        "how did you do that",
        "how was that done",
        "did it work",
    ]
    return any(sig in clean for sig in followup_signals)


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
        if is_profile_query(clean_msg):
            return {
                "route": "CHAT",
                "reasoning": "Inquiry about user profile preferences and configured email identity.",
            }

        if is_action_followup_query(clean_msg):
            return {
                "route": "CHAT",
                "reasoning": "Follow-up inquiry about previous action execution and tool results.",
            }

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
        if any(w in lower_msg for w in [
            "remind", "reminder", "alarm", "calendar", "event", "schedule",
            "send email", "email to", "make pdf", "create pdf", "create a pdf",
            "generate pdf", "generate a pdf", "compile pdf", "compile a pdf", "make a pdf"
        ]):
            return {"route": "ACTION", "reasoning": "Keyword action rule triggered."}
        elif "?" in clean_msg or any(w in lower_msg for w in [
            "what", "who", "when", "where", "why", "how", "explain", "describe", "define",
            "anomaly", "belady", "exam", "syllabus", "module", "unit", "notes", "attendance",
            "room", "venue", "submission", "deadline", "summarize", "summary", "document",
            "uploaded", "report", "overview", "points", "sections", "ktu", "b.tech",
            "python", "java", "c++", "algorithm", "code", "programming", "science",
            "difference", "compare", "kernel", "linux"
        ]):
            return {"route": "QA", "reasoning": "Knowledge question rule triggered: checking local documents first."}
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
