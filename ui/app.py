import os
import sys
import subprocess
import socket
import time
import streamlit as st
import requests
import uuid
import logfire
from dotenv import load_dotenv


def is_port_open(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0


# Start FastAPI backend in the background if it is not already running on port 8000
if not is_port_open(8000):
    try:
        print("🚀 Starting FastAPI backend in the background...")
        # Run uvicorn using the exact same virtual environment python binary
        subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
        )
        time.sleep(6)  # Wait for uvicorn to initialize
    except Exception as e:
        print(f"Failed to start backend in background: {e}")


# Load environment variables explicitly from the root directory
env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
load_dotenv(dotenv_path=env_path)


# Initialize Logfire
try:
    token = os.getenv("LOGFIRE_TOKEN")
    if not token:
        print("ERROR: LOGFIRE_TOKEN is empty or None!")
    logfire.configure(token=token)
    # logfire.instrument_requests() # Disabled due to OpenTelemetry bug on Windows: MeterProvider.get_meter() got multiple values for argument 'version'
    LOGFIRE_STATUS = "Connected & Tracing"
except Exception as e:
    print(f"Logfire Init Error in UI: {e}")
    LOGFIRE_STATUS = f"Standby (Error: {e})"
    

import json
SESSIONS_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "sessions.json"))

def load_saved_sessions():
    sessions = {}
    if os.path.exists(SESSIONS_FILE):
        try:
            with open(SESSIONS_FILE, "r") as f:
                sessions = json.load(f)
        except Exception:
            sessions = {}
            
    # Sync with active backend threads to remove stale (wiped) sessions
    try:
        base_url = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")
        response = requests.get(f"{base_url}/active_threads", timeout=2)
        if response.status_code == 200:
            data = response.json()
            active_threads = set(data.get("active_threads", []))
            
            # Filter sessions to only keep active ones
            filtered_sessions = {k: v for k, v in sessions.items() if k in active_threads}
            
            # If some sessions were removed, update sessions.json
            if len(filtered_sessions) != len(sessions):
                with open(SESSIONS_FILE, "w") as f:
                    json.dump(filtered_sessions, f, indent=2)
                sessions = filtered_sessions
    except Exception as e:
        # Silently fall back to raw sessions if backend is unreachable or starting up
        pass
        
    return sessions

def save_session_metadata(session_id, first_message):
    sessions = load_saved_sessions()
    if session_id not in sessions:
        title = first_message[:30] + "..." if len(first_message) > 30 else first_message
        timestamp = time.strftime("%b %d, %H:%M")
        sessions[session_id] = {
            "title": f"{timestamp} - {title}",
            "timestamp": timestamp
        }
        try:
            with open(SESSIONS_FILE, "w") as f:
                json.dump(sessions, f, indent=2)
        except Exception as e:
            print(f"Failed to write sessions.json: {e}")


# --- PAGE CONFIG ---
st.set_page_config(
    page_title="Enterprise Agentic RAG",
    page_icon="🤖",
    layout="wide",
)

# --- AVATARS ---
AI_AVATAR = "🤖"
USER_AVATAR = "👤"


# --- SESSION MANAGEMENT ---
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
    logfire.info(f"✨ New User Session Created: {st.session_state.session_id}")

if "messages" not in st.session_state:
    st.session_state.messages = []


# --- SIDEBAR ---
with st.sidebar:
    st.title("🧠 Agent OS")
    st.markdown("---")
    st.success(f"Logfire: {LOGFIRE_STATUS}")
    
    st.write("📋 **Active Memory ID**")
    st.code(st.session_state.session_id)
    
    st.markdown("---")
    
    st.subheader("📚 Recent Chats")
    saved_sessions = load_saved_sessions()
    if saved_sessions:
        session_options = list(saved_sessions.keys())
        selected_to_load = st.selectbox(
            "Choose a past session",
            options=[""] + session_options,
            format_func=lambda x: saved_sessions[x]["title"] if x in saved_sessions else "Select a chat..."
        )
        if selected_to_load and selected_to_load != st.session_state.session_id:
            if st.button("🔄 Switch Chat", use_container_width=True):
                try:
                    base_url = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")
                    response = requests.get(f"{base_url}/history/{selected_to_load}", timeout=10)
                    data = response.json()
                    if data.get("status") == "success" and data.get("messages"):
                        raw_msgs = data.get("messages", [])
                        formatted_msgs = []
                        for m in raw_msgs:
                            content = m.get("content", "")
                            msg_type = m.get("type", "")
                            role = "user" if msg_type == "human" else "assistant" if msg_type == "ai" else m.get("role", "user")
                            formatted_msgs.append({"role": role, "content": content})
                        
                        st.session_state.messages = formatted_msgs
                        st.session_state.session_id = selected_to_load
                        st.success("Session loaded successfully!")
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error("No past history found for this session. (The backend memory may have been reset due to a server restart).")
                except Exception as e:
                    st.error(f"Failed to load chat: {e}")
    else:
        st.info("No recent chats found.")
        
    st.markdown("---")
    
    st.subheader("🔄 Resume Past Chat")
    load_id = st.text_input("Enter Past Memory ID", placeholder="Paste UUID here...")
    if st.button("Sync & Load History", use_container_width=True):
        if load_id.strip():
            try:
                base_url = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")
                response = requests.get(f"{base_url}/history/{load_id.strip()}", timeout=10)
                data = response.json()
                if data.get("status") == "success" and data.get("messages"):
                    raw_msgs = data.get("messages", [])
                    formatted_msgs = []
                    for m in raw_msgs:
                        content = m.get("content", "")
                        # Handle LangChain message classes serialization
                        msg_type = m.get("type", "")
                        if msg_type == "human":
                            role = "user"
                        elif msg_type == "ai":
                            role = "assistant"
                        else:
                            role = m.get("role", "user")
                        formatted_msgs.append({"role": role, "content": content})
                    
                    st.session_state.messages = formatted_msgs
                    st.session_state.session_id = load_id.strip()
                    st.success("Session synchronized successfully!")
                    time.sleep(0.8)
                    st.rerun()
                else:
                    st.error("No past history found for this Memory ID.")
            except Exception as e:
                st.error(f"Failed to fetch history: {e}")
        else:
            st.warning("Please enter a valid Memory ID.")
            
    st.markdown("---")
    
    if st.button("🗑️ Clear History & Memory", use_container_width=True, type="primary"):
        logfire.warn(f"🗑️ Memory Wipe Triggered for session: {st.session_state.session_id}")
        st.session_state.messages = []
        st.session_state.session_id = str(uuid.uuid4())
        st.rerun()

# --- MAIN CHAT ---
st.title("🤖 Enterprise Agentic Assistant")


# Display history
for message in st.session_state.messages:
    avatar = AI_AVATAR if message["role"] == "assistant" else USER_AVATAR
    with st.chat_message(message["role"], avatar=avatar):
        # If this is an assistant message and contains thought steps, show them!
        if message["role"] == "assistant" and "steps" in message and message["steps"]:
            with st.status("✅ Answer Synthesized", state="complete", expanded=True):
                for step in message["steps"]:
                    st.write(f"⚙️ {step}")
        st.markdown(message["content"])

# Chat Input
if prompt := st.chat_input("Ask about your documentation..."):
    # Save session metadata if this is the first interaction of the session
    if not st.session_state.messages:
        save_session_metadata(st.session_state.session_id, prompt)

    # START TRACE: User Interaction
    with logfire.span("💬 User Chat Interaction", user_query=prompt, session_id=st.session_state.session_id):
        
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user", avatar=USER_AVATAR):
            st.markdown(prompt)

        # Assistant Response
        with st.chat_message("assistant", avatar=AI_AVATAR):
            steps = []
            with st.status("🔍 Agent is thinking...", expanded=True) as status:
                try:
                    # DISTRIBUTED TRACE: Calling Backend
                    with logfire.span("📡 Calling RAG Backend"):
                        # Get backend URL from env, or default to local if not set
                        base_url = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")
                        url = f"{base_url}/query"
                        payload = {"q": prompt, "thread_id": st.session_state.session_id}
                        response = requests.post(url, json=payload, timeout=60)
                        data = response.json()
                    
                    # Show Reasoning Steps from Backend
                    steps = data.get("thought_process", [])
                    for step in steps:
                        st.write(f"⚙️ {step}")
                    
                    status.update(label="✅ Answer Synthesized", state="complete", expanded=True)
                    
                    # --- SHOW SOURCES (NESTED EXPANDABLES) ---
                    sources = data.get("sources", [])
                    if sources:
                        with st.expander("📄 View Retrieved Context (Sources)"):
                            for i, source in enumerate(sources):
                                # Create a preview title for each chunk
                                preview = source[:100].replace("\n", " ") + "..."
                                with st.expander(f"Chunk {i+1}: {preview}"):
                                    st.info(source)
                except Exception as e:
                    logfire.error(f"❌ UI-Backend Connection Failed: {e}")
                    status.update(label="❌ Connection Failed", state="error")
                    st.error("Backend Offline.")
                    st.stop()

            # Final Answer Streaming
            answer_placeholder = st.empty()
            full_answer = data.get("answer", "No response.")
            
            curr_text = ""
            for char in full_answer:
                curr_text += char
                answer_placeholder.markdown(curr_text + "▌")
                time.sleep(0.005)
            
            answer_placeholder.markdown(full_answer)
            st.session_state.messages.append({"role": "assistant", "content": full_answer, "steps": steps})
            logfire.info("✅ Chat cycle completed successfully.")
            st.rerun()