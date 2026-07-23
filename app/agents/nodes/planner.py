from app.agents.state import AgentState
from app.gateway import get_langchain_llm
import logfire

# Portkey-backed LLM: fallback + cache + retry — same .invoke() interface as ChatGroq
llm = get_langchain_llm(feature="planner")

def planner_node(state: AgentState):
    """
    The Planner determines if a search is needed based on the ENTIRE conversation.
    """
    # Get the conversation history (excluding the latest message)
    history = ""
    for msg in state["messages"][:-1]:
        role = "User" if msg["role"] == "user" else "Assistant"
        history += f"{role}: {msg['content']}\n"
    
    user_message = state["messages"][-1]["content"] if state["messages"] else ""
    
    prompt = f"""
    You are an intelligent router classifying user queries.
    Analyze the conversation history and the latest user message.
    
    CONVERSATION HISTORY:
    {history}
    
    LATEST MESSAGE:
    "{user_message}"
    
    Classification Rules:
    - CONVERSATIONAL: The user's message is conversational in nature (such as greetings, introductions, statements of personal facts or preferences they expect the assistant to remember, or follow-up questions relying strictly on previous conversation memory).
    - TECHNICAL: The user's message is an engineering query (such as technical questions, code generation requests, programming concept explanations, database schema designs, or topics directly related to software development in Python and FastAPI).
    
    Output format: Output ONLY the raw string "CONVERSATIONAL" or "TECHNICAL". No markdown, no quotes, no extra text.
    """
    
    with logfire.span("🧠 Planner Decision"):
        decision = llm.invoke(prompt).content.strip()
        logfire.info(f"Intent identified: {decision}")
    
    if decision == "CONVERSATIONAL":
        return {
            "current_query": "CONVERSATIONAL",
            "status": "Handling conversationally (using memory)...",
            "plan": ["Intent: Conversational/Memory", "Retrieval: Skipped"]
        }
    
    return {
        "current_query": user_message,
        "status": f"Technical research needed. Searching for: {user_message}",
        "plan": ["Intent: Technical", f"Search Term: {user_message}"]
    }