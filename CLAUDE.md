# OPS-AGENT Project Conventions

## Tech Stack & Architecture
- **Language:** Python 3.10+[cite: 1]
- **Orchestration:** LangGraph (State management, error handling, handoffs)[cite: 1]
- **LLM Integration:** Gemini API (primary) with Ollama local fallback[cite: 1]
- **Vector Store:** FAISS or ChromaDB[cite: 1]
- **Backend API:** FastAPI[cite: 1]

## Core Development Rules
- **State Management:** Use typed dictionaries for LangGraph state. Ensure the `confidence_score` and `escalation_flag` are clearly defined in the state object.
- **RAG Implementation:** The Retrieval Agent must use semantic similarity search[cite: 1]. Never allow the Resolution Agent to generate answers without grounding them in retrieved context.
- **Modularity:** Keep each agent (Intake, Retrieval, Resolution, Governance) in its own dedicated Python module to allow for independent testing and prompt tuning[cite: 1].
- **No Early Optimization:** For the Week 5-7 milestone, raw confidence scores are acceptable. Do not implement Temperature Scaling or Split-Conformal Prediction until explicitly instructed.
- **Testing:** Write unit tests using `pytest` for each agent's node execution before testing the full LangGraph compile.