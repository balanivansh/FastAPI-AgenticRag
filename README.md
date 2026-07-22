# 🤖 Enterprise Agentic RAG Assistant (FastAPI & LangGraph)

A production-grade, highly-secured Agentic Retrieval-Augmented Generation (RAG) assistant trained on custom-scraped FastAPI documentation. The system features a self-healing Streamlit user interface, NVIDIA NeMo Guardrails, a LangGraph state machine planner, a Portkey LLM gateway with built-in caching, and Logfire distributed tracing.

---

## 🏗️ System Architecture & Workflow

```
               +----------------------------------------+
               |        Streamlit Web Interface         |
               +-------------------+--------------------+
                                   |
                       POST /query | (JSON Payload)
                                   v
               +-------------------+--------------------+
               |           FastAPI Gateway              |
               +-------------------+--------------------+
                                   |
                    [Layer 1]      v
               +-------------------+--------------------+
               |       NVIDIA NeMo Guardrails Gate      |
               +---------+--------------------+---------+
                         |                    |
             Fired (Block)                    | Passed (RAG)
                         v                    v
               +---------+---------+   +------+-----------------+
               |  Direct refusal   |   |   LangGraph Pipeline   |
               |  returned to UI   |   +------+-----------------+
               +-------------------+          |
                                              | 1. Planner Node (Intent)
                                              v
                                       [Conversational] or [Technical RAG]
                                              |                 |
                       +----------------------+                 v
                       |                               2. Retriever Node (Qdrant)
                       v                                        |
               3. Responder Node (LLM)                          v
                       |                               3. FlashRank Reranker
                       |                                        |
                       v                                        v
               +-------+-------------------+           4. Responder Node (LLM)
               |  Portkey Gateway Router   |                    |
               +-------+-------------------+           v
                       |                        Returns generated response
         [Simple Cache]|
                       +=======> HIT  ===> Returns cached response
                       |
                       +=======> MISS ===> Routes to Groq (Llama 8B/70B)
```

### Key Modules:
1. **Frontend Dashboard (`ui/`):** Streamlit-based chat interface. Features dynamic thought-step visualization, markdown code blocks rendering, source citation expanders, and a **self-healing session manager** that automatically synchronizes/cleans stale sessions when the backend restarts.
2. **Backend Server (`app/main.py`):** FastAPI web server exposing `/query` for execution, `/history/{thread_id}` for session restoration, and `/active_threads` to list live sessions.
3. **Guardrails Firewall (`app/guardrails/`):** Layer 1 NVIDIA NeMo Guardrails intercepting jailbreaks and off-topic questions.
4. **Agent Orchestrator (`app/agents/`):** LangGraph execution plan:
   * **Planner Node:** A few-shot routed Llama 8B engine that classifies query intent into `CONVERSATIONAL` or `TECHNICAL`.
   * **Retriever Node:** Queries Qdrant vector database using Google Gemini embeddings and reranks using **FlashRank** local ONNX engines.
   * **Responder Node:** Layer 2 Guardrails focus constraint LLM synthesizing the final, cite-supported response.
5. **Gateway Client (`app/gateway/`):** Portkey Client integration providing request retries, automatic LLM fallbacks, and global simple response caching.

---

## ⚙️ Project Setup & Installation

### 1. Prerequisites
Ensure you have Python 3.10+ installed.

### 2. Install dependencies
Initialize your virtual environment and install the required libraries:
```bash
# Create a virtual environment
python -m venv fastapiRag

# Activate the virtual environment
source fastapiRag/bin/activate

# Install requirements
pip install -r requirements.txt
```

### 3. Environment Configuration (`.env`)
Create a `.env` file in the root directory. Add the following keys:
```env
GROQ_API_KEY = "your-groq-api-key"
GROQ_FALLBACK_API_KEY = "your-backup-groq-key"

QDRANT_CLUSTER_ENDPOINT = "https://your-qdrant-cluster.io" 
QDRANT_API_KEY = "your-qdrant-api-key"

GEMINI_API_KEY = "your-gemini-api-key"

PORTKEY_API_KEY = "your-portkey-api-key"
PORTKEY_CONFIG_ID = "your-portkey-config-id"

LOGFIRE_TOKEN = "your-logfire-write-token"
```

> [!WARNING]
> Do **NOT** commit your `.env` or `.logfire/` credential folders to GitHub. They are already listed in the `.gitignore` to prevent secret leaks.

---

## 🚀 Running the Application Localy

### 1. Start the Backend API Server
```bash
uvicorn app.main:app --port 8000 --reload
```
The backend API documentation will be available at `http://localhost:8000/docs`.

### 2. Start the Frontend Dashboard
```bash
streamlit run ui/app.py
```
Open your browser at `http://localhost:8501` to chat!

---

## ☁️ Production Deployment on Hugging Face Spaces

Deploying on **Hugging Face Spaces** is the recommended route because it provides **16GB of RAM** for free. This runs NeMo Guardrails and FlashRank models comfortably without any out-of-memory errors.

### Steps to Deploy:
1. Create a free account at [huggingface.co](https://huggingface.co) and create a **New Space**.
2. Name your space, select **Docker** as the Space SDK, and choose the **Blank** template.
3. Add your environment variables (from your `.env` file) as **Variables and Secrets** in the Space settings tab.
4. Clone the space repository locally or link it as a remote, then push this codebase. Hugging Face will build the container and deploy your backend securely.
