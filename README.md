# AI-Powered Customer Support Chatbot

[![Project Status: Complete](https://img.shields.io/badge/Project%20Status-Complete%20%26%20Working-brightgreen.svg)](README.md)
[![Backend Tests: 307 Passed](https://img.shields.io/badge/Backend%20Tests-307%20Passed%20%7C%200%20Failed-success.svg)](backend/tests/)
[![Frontend Build: Successful](https://img.shields.io/badge/Frontend%20Build-Successful%20(Vite)-blue.svg)](frontend/)
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI%200.115+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/Frontend-React%2019-61DAFB.svg?logo=react&logoColor=black)](https://react.dev)
[![Google Gemini](https://img.shields.io/badge/AI%20Model-Gemini%203.5%20Flash--Lite-4285F4.svg?logo=google&logoColor=white)](https://ai.google.dev)
[![Python](https://img.shields.io/badge/Python-3.12%20%7C%203.14-3776AB.svg?logo=python&logoColor=white)](https://www.python.org)

An enterprise-ready, hybrid customer support chatbot platform designed to deliver instant, accurate, and cost-effective customer assistance. Built with a **FAQ-first routing architecture**, the system resolves common customer queries directly from a curated knowledge base with zero LLM token costs, while seamlessly falling back to **Google Gemini (3.5 Flash-Lite)** with multi-turn conversational memory, entity extraction, grounded business context, and response reliability validation.

---

## Table of Contents

- [1. Project Overview](#1-project-overview)
- [2. Project Architecture](#2-project-architecture)
- [3. Step-by-Step Implementation](#3-step-by-step-implementation)
  - [Phase 1 — Project Foundation](#phase-1--project-foundation)
  - [Phase 2 — Database and Conversation Management](#phase-2--database-and-conversation-management)
  - [Phase 3 — API Development](#phase-3--api-development)
  - [Phase 4 — NLP Processing](#phase-4--nlp-processing)
  - [Phase 5 — FAQ-First Response System](#phase-5--faq-first-response-system)
  - [Phase 6 — Gemini Integration and Context-Aware Responses](#phase-6--gemini-integration-and-context-aware-responses)
  - [Phase 7 — Conversation Memory and State](#phase-7--conversation-memory-and-state)
  - [Phase 8 — Response Quality and Reliability](#phase-8--response-quality-and-reliability)
  - [Phase 9 — Frontend Implementation](#phase-9--frontend-implementation)
  - [Phase 10 — Security and Performance](#phase-10--security-and-performance)
- [4. Complete Request Flow](#4-complete-request-flow)
- [5. Installation and Setup](#5-installation-and-setup)
- [6. How to Test the Project](#6-how-to-test-the-project)
  - [Manual Testing](#manual-testing)
  - [Automated Testing](#automated-testing)
- [7. API Documentation](#7-api-documentation)
- [8. Project Structure](#8-project-structure)
- [9. Testing and Verification Results](#9-testing-and-verification-results)
- [10. Security and Production Considerations](#10-security-and-production-considerations)
- [11. Final Project Status](#11-final-project-status)

---

## 1. Project Overview

### What the Chatbot Does
The **AI-Powered Customer Support Chatbot** serves as an automated first-line customer service representative for e-commerce and retail operations. It processes user queries in natural language, resolves standard inquiries (shipping, refunds, tracking, return policies, account security) instantly using a deterministic FAQ engine, and routes complex or multi-turn inquiries to Google Gemini augmented with real-time business facts (order details, shipping records, product catalog, store policies).

### Problem Statement
Traditional customer support operations face three major bottlenecks:
1. **High Volume of Repetitive Inquiries:** Support teams spend up to 70% of their time answering repetitive questions about order tracking, return windows, and payment methods.
2. **Excessive LLM Operating Costs & Latency:** Routing every customer message directly to commercial LLMs incurs high API costs, rate-limit bottlenecks, and unnecessary token usage for answers that are already known and static.
3. **Hallucinations & Ungrounded Claims:** Unguarded generative models risk fabricating order statuses, cancellation promises, or non-existent discounts, leading to customer disputes and liability.

### Solution
This project solves these issues via a **hybrid tiered response architecture**:
- **Deterministic FAQ Matching:** Queries with high relevance (score >= 0.35) against verified company knowledge receive instantaneous answers with zero LLM API calls.
- **Context-Augmented Fallback:** Unmatched inquiries trigger entity resolution and ground prompt construction with actual database records before querying Gemini.
- **Pre-Delivery Response Validation:** Candidate AI replies are scored across 6 quality dimensions and vetted against strict anti-hallucination rules before transmission to the user.

### Technology Stack

| Layer | Technologies & Tools |
|---|---|
| **Backend Framework** | Python 3.12 / 3.14, FastAPI 0.115+, Uvicorn (ASGI) |
| **Data & Persistence** | SQLite 3, SQLAlchemy 2.0 (ORM), Declarative Base |
| **Data Validation** | Pydantic v2 with strict whitespace stripping and boundary constraints |
| **AI & LLM** | Google Gemini API (`gemini-3.5-flash-lite`) via official `google-genai` SDK |
| **NLP Engine** | Custom rule-based NLP pipeline: contraction expansion, regex tokenizers, stop-word filters, pattern-based entity extractors |
| **Frontend UI** | React 19, Vite 7, Pure CSS (Responsive mobile/tablet/desktop layout) |
| **Testing & Quality** | Pytest 9+, FastAPI TestClient, HTTPX, AnyIO |

### Key Capabilities
- **FAQ-First Response Routing:** Instantaneous deterministic answers for common customer questions.
- **Grounded Gemini Fallback:** Context-aware generation utilizing historical dialog and business database facts.
- **Multi-Turn Slot Memory:** Cross-turn order ID and tracking number carry-forward with topic shift detection and conflicting entity disambiguation.
- **Input Hardening:** Strict whitespace rejection, boundary length validation, and path parameter sanitization.
- **Anti-Hallucination Guardrails:** Automated validation suppressing fabricated order statuses and unauthorized cancellations.
- **Zero Session Contamination:** Strict session isolation preventing data leaks between distinct conversation threads.

---

## 2. Project Architecture

The system follows a clean modular pipeline where every incoming message progresses through a sequential decision tree:

```mermaid
flowchart TD
    User([Customer / Web Browser]) -->|User Message| Frontend[React 19 + Vite Frontend]
    Frontend -->|POST /api/v1/conversations/:id/reply| Backend[FastAPI Backend]

    subgraph Backend Pipeline
        Backend --> InputVal{Input & Session<br/>Validation}
        InputVal -->|Invalid / Whitespace| Err422[HTTP 422 / 404]
        InputVal -->|Valid| SaveUserMsg[(Save User Message<br/>to SQLite)]

        SaveUserMsg --> NLP[NLP Preprocessing &<br/>Entity Extraction]
        NLP --> SlotMemory[Load & Resolve State<br/>Slot Memory Carry-Forward]
        
        SlotMemory --> AmbiguousCheck{Multiple Conflicting<br/>Identifiers?}
        AmbiguousCheck -->|Yes| Clarification[Generate Clarification Reply]
        AmbiguousCheck -->|No| FAQSearch[FAQ Knowledge Base Search<br/>Jaccard + Keyword Coverage]

        FAQSearch --> ScoreCheck{Relevance Score<br/>>= 0.35?}
        ScoreCheck -->|Yes (FAQ Hit)| FAQAnswer[Verified FAQ Response<br/>answer_source = 'faq']
        
        ScoreCheck -->|No (Fallback)| BizRetrieval[Business Data Lookup<br/>Orders, Shipments, Policies]
        BizRetrieval --> AssemblePrompt[Augment System Prompt<br/>+ Context + Format Guidance]
        AssemblePrompt --> FetchHistory[(Fetch History Slice<br/>Up to 10 Messages)]
        FetchHistory --> CallGemini[Call Google Gemini API<br/>Model: gemini-3.5-flash-lite]
        CallGemini --> QualityValidator{Response Quality<br/>& Grounding Check}
        QualityValidator -->|Valid| GeminiAnswer[Grounded AI Response<br/>answer_source = 'gemini']
        QualityValidator -->|Invalid / Hallucinated| SafeFallback[Safe Deterministic Fallback]

        FAQAnswer --> CommitDB[(Atomic DB Commit<br/>Assistant Message + State)]
        Clarification --> CommitDB
        GeminiAnswer --> CommitDB
        SafeFallback --> CommitDB
    end

    CommitDB --> ReturnReply[Return ReplyResponse JSON]
    ReturnReply --> Frontend
    Frontend --> Display([Render Bot Bubble in UI])
```

---

## 3. Step-by-Step Implementation

The project was developed across 30 structured development days, organized into 10 logical engineering phases:

### Phase 1 — Project Foundation
- Initialized the repository structure separating `backend/` and `frontend/`.
- Configured FastAPI with ASGI lifespan events (`@asynccontextmanager`) ensuring automatic table initialization on application startup.
- Established React 19 single-page application configured with Vite 7.
- Set up SQLite database connection via SQLAlchemy engine with thread-safe connection arguments (`check_same_thread=False`).
- Configured secure environment variable management via `python-dotenv` with `.env.example` templates and strict `.gitignore` rules.

### Phase 2 — Database and Conversation Management
- **`Conversation` Model:** Represents an isolated conversation session indexed by unique UUID `session_id` and UTC creation timestamp.
- **`Message` Model:** Represents individual dialog turns linked by foreign key (`conversation_id`), tracking sender `role` (`user` or `assistant`), text `content`, and UTC timestamp.
- **`ConversationState` Model:** Dedicated single-row-per-session slot-filling table tracking `active_intent`, `active_order_id`, `active_tracking_number`, and `pending_clarification`.
- **Session Management:** Encapsulated database sessions within FastAPI's `get_db` dependency yielding a session and ensuring clean closure in `finally` blocks. Database write operations include explicit `db.rollback()` on exception.

### Phase 3 — API Development
Implemented 11 RESTful endpoints adhering to REST principles and OpenAPI standards:

| Method | Endpoint | Description | Request Schema | Response Schema |
|---|---|---|---|---|
| `GET` | `/health` | Service health check | None | `{"status": "ok", "service": "..."}` |
| `POST` | `/api/v1/validate-message` | Validates message length and content | `MessageRequest` | `MessageValidationResponse` |
| `POST` | `/api/v1/conversations` | Initializes a new conversation session | None | `ConversationResponse` |
| `POST` | `/api/v1/conversations/{session_id}/messages` | Persists a customer message | `MessageRequest` | `MessageResponse` |
| `GET` | `/api/v1/conversations/{session_id}/messages` | Retrieves session history in chronological order | None | `list[MessageResponse]` |
| `POST` | `/api/v1/conversations/{session_id}/reply` | Primary context-aware conversational reply pipeline | `MessageRequest` | `ReplyResponse` |
| `POST` | `/ai/reply` | Standalone single-turn Gemini generation | `AIReplyRequest` | `AIReplyResponse` |
| `POST` | `/api/v1/faqs/search` | Standalone search across FAQ dataset | `FAQSearchRequest` | `FAQSearchResponse` |
| `POST` | `/api/v1/nlp/intent` | Standalone customer intent classification | `NLPRequest` | `IntentResponse` |
| `POST` | `/api/v1/nlp/entities` | Standalone domain entity extraction | `NLPRequest` | `EntityResponse` |
| `POST` | `/api/v1/nlp/analyze` | Complete NLP pipeline diagnostic analysis | `NLPRequest` | `MessageAnalysisResponse` |

### Phase 4 — NLP Processing
Built a deterministic Natural Language Processing pipeline in `backend/app/nlp/`:
- **Preprocessing (`preprocessing.py`):**
  - Lowercase normalization and excess whitespace compression.
  - Contraction expansion (`"can't"` -> `"cannot"`, `"where's"` -> `"where is"`, `"won't"` -> `"will not"`).
  - Punctuation-safe tokenization with specialized stop-word filtering that eliminates single-character contraction stems (`'t'`, `'s'`) to prevent false-positive matching on follow-up questions.
- **Intent Recognition (`intent.py`):**
  Classifies input into one of 13 customer-support intents with confidence scoring:
  1. `order_status`
  2. `shipping`
  3. `cancel_order`
  4. `return`
  5. `refund`
  6. `payment`
  7. `account`
  8. `product_info`
  9. `greeting`
  10. `complaint`
  11. `human_agent`
  12. `technical_issue`
  13. `unknown`
- **Entity Extraction (`entities.py`):**
  Extracts structured business entities using regex and keyword boundary matching:
  - **Order IDs:** Prefixed patterns (`ORD-12345`) and 6-digit order numbers.
  - **Tracking Numbers:** Carrier formats (`TRK-98765`, alphanumeric shipment codes).
  - **Email Addresses:** Standard RFC-compliant customer emails.
  - **Monetary Amounts:** Currency patterns (`$49.99`, `$120`).
  - **Product Mentions:** Catalog matching against known merchandise.

### Phase 5 — FAQ-First Response System
Implemented a deterministic FAQ search engine in `backend/app/services/faq_search.py` backed by `data/faq.json` (25 curated customer support FAQs):
1. Incoming customer query is tokenized and stripped of stop words.
2. Candidate FAQs are scored using a weighted formula:
   $$\text{Score} = (0.75 \times \text{Keyword Coverage}) + (0.25 \times \text{Jaccard Similarity})$$
3. Whole-word phrase bonuses are applied for exact keyword sequences.
4. Candidates are filtered by `FAQ_RELEVANCE_THRESHOLD = 0.35`.
5. When a match meets the threshold:
   - The verified answer is returned immediately.
   - `answer_source` is flagged as `"faq"`.
   - **Gemini is completely bypassed**, eliminating token consumption and API latency.
   - Conversation history loading is skipped.
6. When no match meets the threshold, the pipeline automatically falls back to Gemini.

### Phase 6 — Gemini Integration and Context-Aware Responses
- **SDK Integration:** Built using the official `google.genai` SDK with model `gemini-3.5-flash-lite`.
- **System Prompt:** Comprehensive instruction set in `backend/app/services/prompts.py` enforcing a helpful, professional customer service persona, empathy rules, anti-hallucination constraints, and instruction resistance.
- **Context Augmentation:** For order and shipment intents, `backend/app/services/retrieval.py` fetches factual records from `data/sample_business_data.json` and injects them as verified facts into the prompt.
- **History Slicing:** The 10 most recent prior messages (`HISTORY_LIMIT = 10`) are fetched, sorted chronologically (oldest-first), converted to Gemini's role format (`user` and `model`), and passed as conversational context. The current in-flight message is excluded from the history slice to prevent duplicate turns.
- **Resilience & Retries:** Transient API errors (HTTP 429, 500, 502, 503, 504) trigger exponential back-off retries (up to 3 attempts). Unrecoverable failures return a clean HTTP 502 Bad Gateway without leaking internal details.

### Phase 7 — Conversation Memory and State
- **Slot Carry-Forward:** Managed via `backend/app/services/conversation_state.py`. If a customer asks *"Where is my order?"* and provides `ORD-12345`, followed by a pronoun query (*"When was it shipped?"*), the state tracker carries forward `ORD-12345` into the second turn without requiring the customer to repeat the identifier.
- **Ambiguity Detection:** If a user submits multiple conflicting order IDs in a single message, the system detects the conflict and immediately returns a clarification request rather than guessing.
- **Topic Shift Clearing:** Conversational topic changes (e.g., transitioning from an order inquiry to an account login or general complaint) automatically wipe stored order/tracking slots.
- **Session Isolation:** SQL queries partition messages strictly by `conversation_id`, preventing any data leakage across distinct browser sessions.

### Phase 8 — Response Quality and Reliability
- **Formatting Guidance (`response_formatter.py`):** Injects dynamic formatting instructions based on detected intent (e.g., bulleted return steps, itemized order status cards).
- **Tone Control:** Enforces concise answers, limits redundant corporate apologies to at most one per reply, and eliminates filler language.
- **Deterministic Response Validator (`response_validator.py`):** Evaluates candidate Gemini replies before delivery:
  - Rejects empty or malformed outputs.
  - Verifies identifier consistency (prevents Gemini from hallucinating order numbers not present in context).
  - Blocks unverified operational claims (e.g., falsely claiming a refund has been issued when the business context indicates it is pending).
  - Substitutes a safe deterministic fallback (`SAFE_FALLBACK_GEMINI_ERROR`) if validation fails.

### Phase 9 — Frontend Implementation
React 19 single-page application structured in `frontend/src/`:
- **`App.jsx`:** Central state machine coordinating messages, active session ID, loading indicators, and error banners.
- **Component Architecture:**
  - `ChatHeader.jsx`: Bot identity avatar, online status indicator, and conversation reset ("Clear") button.
  - `MessageList.jsx`: Renders message bubbles with auto-scrolling to the latest turn via `scrollIntoView`.
  - `MessageBubble.jsx`: Differentiated user vs. bot bubbles, timestamp formatting, and clean plain-text rendering (XSS-safe).
  - `ChatInput.jsx`: Controlled text input with character limit counter (2,000 max), Enter-to-send support, and disabled state while awaiting responses.
  - `LoadingIndicator.jsx`: Animated three-dot typing indicator labeled *"AI is thinking..."*.
  - `FAQSuggestions.jsx`: Clickable quick-prompt buttons displayed on empty chat states.
  - `ErrorMessage.jsx`: Alert banner displaying user-friendly error details with an interactive "Retry" button.
  - `EmptyChat.jsx`: Empty state placeholder prompt.
- **Session Persistence:** Stores `chat_session_id` in `localStorage`. Automatically restores full message history on page refresh via `GET /api/v1/conversations/{session_id}/messages`. Handles stale session cleanup on HTTP 404.
- **Duplicate Send Prevention:** Employs a synchronous `useRef(isSendingRef)` alongside reactive `isLoading` state to completely block rapid double-clicks and repeated Enter presses.

### Phase 10 — Security and Performance
- **Security Hardening:**
  - Zero hardcoded credentials; `GEMINI_API_KEY` is loaded from `.env`.
  - `.env` and `.env.*` excluded from source control.
  - `ConfigDict(str_strip_whitespace=True)` on all Pydantic request models.
  - Path parameter length validation (`_validate_session_id`) returning clean 404s for malformed or oversized IDs.
  - CORS middleware explicitly restricted to authorized Vite dev origins (`http://localhost:5173`, `http://127.0.0.1:5173`) with allowed methods `["GET", "POST"]`.
  - Full SQL injection prevention via parameterized SQLAlchemy queries.
  - Internal exceptions caught and normalized into standard HTTP error responses.
- **Performance Optimizations:**
  - FAQ hits skip Gemini network calls and bypass conversation history database reads entirely.
  - History retrieval is bounded by database-level `.limit(HISTORY_LIMIT)`.
  - Assistant message persistence and conversation state upserts are committed in a single atomic database transaction.
  - Frontend synchronous request deduplication eliminates duplicate in-flight requests.

---

## 4. Complete Request Flow

Here is the exact step-by-step lifecycle of a message sent through the chatbot:

```
 1. Customer enters a message in the React interface and clicks Send (or presses Enter).
 2. Frontend trims input, checks isSendingRef, disables the input, displays an optimistic user bubble, and sends POST to /api/v1/conversations/{session_id}/reply.
 3. Backend validates session_id format and checks existence in SQLite (returns 404 if unknown).
 4. Backend validates message payload via MessageRequest (strips whitespace; rejects empty or >2000 chars with 422).
 5. User message is committed immediately to SQLite (ensuring an audit trail even if downstream processing fails).
 6. NLP pipeline executes: normalizes text, expands contractions, tokenizes, classifies intent, and extracts entities.
 7. Multi-turn conversation state loads from SQLite; slot carry-forward resolves active order IDs or tracking numbers.
 8. If conflicting identifiers are detected, an immediate clarification reply is generated and the pipeline skips to persistence.
 9. FAQ search runs against data/faq.json using keyword coverage and Jaccard similarity.
10. If an FAQ score meets the threshold (>= 0.35):
    - FAQ answer is selected directly.
    - answer_source is set to "faq".
    - Gemini API call and history retrieval are completely skipped.
11. If no FAQ meets the threshold:
    - Business data retrieval fetches relevant orders, shipments, or store policies.
    - Up to 10 recent messages are queried from SQLite in chronological order (excluding the current turn).
    - Augmented system prompt is assembled with intent guidance and tone reminders.
    - Google Gemini generates candidate reply.
    - Response validator verifies quality, entity consistency, and grounding (applying safe fallback if needed).
    - answer_source is set to "gemini".
12. Assistant message and updated conversation state are committed to SQLite in an atomic transaction.
13. Backend returns HTTP 201 Created with ReplyResponse JSON.
14. Frontend receives response, clears loading state, renders the bot response bubble, and scrolls to bottom.
```

---

## 5. Installation and Setup

### Prerequisites
- **Python:** Version 3.10, 3.11, 3.12, or 3.14
- **Node.js:** Version 18.0 or higher (with npm)
- **Git:** Version 2.30 or higher
- **Google Gemini API Key:** An active key from [Google AI Studio](https://aistudio.google.com/)

### 1. Clone the Repository
```bash
git clone https://github.com/nishantrs0404/AI-Powered-Customer-Support-Chatbot.git
cd AI-Powered-Customer-Support-Chatbot
```

### 2. Backend Setup
1. Create and activate a Python virtual environment:
   ```bash
   # Windows (PowerShell)
   python -m venv .venv
   .venv\Scripts\Activate.ps1

   # Linux / macOS
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. Install Python dependencies:
   ```bash
   pip install -r backend/requirements.txt
   ```

3. Configure environment variables:
   Copy the example environment file to the project root:
   ```bash
   cp .env.example .env
   ```
   Open `.env` and add your Gemini API key:
   ```env
   GEMINI_API_KEY=your_actual_gemini_api_key_here
   ```

4. Start the FastAPI backend server:
   ```bash
   # From the repository root:
   uvicorn app.main:app --reload --port 8000 --app-dir backend
   ```
   The backend will start at `http://127.0.0.1:8000`. SQLite tables are created automatically on startup.

### 3. Frontend Setup
1. In a new terminal, navigate to the `frontend` directory:
   ```bash
   cd frontend
   ```

2. Install npm dependencies:
   ```bash
   npm install
   ```

3. Verify the frontend environment file:
   Ensure `frontend/.env` contains the backend URL:
   ```env
   VITE_API_BASE_URL=http://localhost:8000
   ```

4. Start the Vite development server:
   ```bash
   npm run dev
   ```
   The frontend will be available at `http://localhost:5173`.

---

## 6. How to Test the Project

### Manual Testing Guide

Follow these steps to verify all major conversational features in your browser at `http://localhost:5173`:

1. **Test FAQ-First Matching:**
   - Type: `"Where is my package?"` or click the **📦 Order status** suggestion.
   - **Expected Result:** Instant answer from FAQ (*"Check your delivery location..."*). Gemini is not called.
2. **Test Gemini Fallback with Business Data:**
   - Type: `"What is the status of order ORD-12345?"`
   - **Expected Result:** Bot retrieves order `ORD-12345` from sample data and provides an informed, professional response detailing items and transit status.
3. **Test Multi-Turn Slot Carry-Forward:**
   - Follow up with: `"When will it arrive?"`
   - **Expected Result:** Bot remembers `ORD-12345` without re-prompting and answers using the stored shipment context.
4. **Test Conflicting Identifier Clarification:**
   - Type: `"Please check ORD-11111 and ORD-22222 for me."`
   - **Expected Result:** Bot detects multiple distinct IDs and asks you to clarify which order you would like to inspect.
5. **Test Input Validation:**
   - Try submitting a blank message or spaces.
   - **Expected Result:** Send button remains disabled; empty messages cannot be sent.
6. **Test Conversation Reset:**
   - Click the **Clear** button in the header.
   - **Expected Result:** Messages are cleared, localStorage session ID is reset, and a clean conversation session is initialized.

### Automated Testing

#### Run Backend Pytest Suite
From the repository root with the virtual environment activated:
```bash
# Run full test suite with summary
python -m pytest backend/tests -v

# Run without verbose output
python -m pytest backend/tests -q
```

#### Run Frontend Production Build
From the `frontend` directory:
```bash
npm run build
```
Confirms clean compilation, JSX validation, asset bundling, and gzip size calculation.

---

## 7. API Documentation

### Available Endpoints

| HTTP Method | Route | Description |
|---|---|---|
| `GET` | `/health` | Service health status |
| `POST` | `/api/v1/validate-message` | Validates customer message length and character count |
| `POST` | `/api/v1/conversations` | Creates a new conversation thread and returns unique session ID |
| `POST` | `/api/v1/conversations/{session_id}/messages` | Saves a customer message to conversation history |
| `GET` | `/api/v1/conversations/{session_id}/messages` | Retrieves message history for session in chronological order |
| `POST` | `/api/v1/conversations/{session_id}/reply` | Primary context-aware reply pipeline (FAQ -> Gemini -> Validation) |
| `POST` | `/ai/reply` | Standalone single-turn Gemini completion (no history) |
| `POST` | `/api/v1/faqs/search` | Search FAQ dataset with keyword scoring |
| `POST` | `/api/v1/nlp/intent` | Classify customer intent across 13 categories |
| `POST` | `/api/v1/nlp/entities` | Extract domain entities (orders, emails, tracking, amounts) |
| `POST` | `/api/v1/nlp/analyze` | Full NLP diagnostics (tokens, normalized text, intent, entities) |

### Interactive Documentation
When the FastAPI backend is running, complete interactive API documentation with live testing is available at:
- **Swagger UI:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **ReDoc:** [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

---

## 8. Project Structure

```
AI-Powered-Customer-Support-Chatbot/
├── .env.example                     # Environment template for Gemini API key
├── .gitignore                       # Git exclusion rules (.env, node_modules, .venv, *.db)
├── LICENSE                          # Project license
├── README.md                        # Master project documentation
│
├── backend/                         # FastAPI Backend Application
│   ├── requirements.txt             # Python dependencies (FastAPI, SQLAlchemy, google-genai, etc.)
│   ├── pytest.ini                   # Pytest configuration
│   ├── chatbot.db                   # SQLite database (auto-generated)
│   ├── app/
│   │   ├── main.py                  # FastAPI application entrypoint, CORS, routes & pipeline
│   │   ├── database.py              # SQLAlchemy engine, session maker, get_db dependency
│   │   ├── models.py                # Database models: Conversation, Message, ConversationState
│   │   ├── faq_data.py              # In-memory FAQ dataset loader
│   │   ├── nlp/                     # Natural Language Processing Engine
│   │   │   ├── preprocessing.py     # Contraction expansion, normalization, tokenization
│   │   │   ├── intent.py            # 13-class intent classifier with confidence scoring
│   │   │   └── entities.py          # Entity extraction (order IDs, tracking, emails, amounts)
│   │   ├── schemas/                 # Pydantic v2 Request & Response Schemas
│   │   │   ├── message.py           # MessageRequest, MessageResponse, ReplyResponse
│   │   │   ├── conversation.py      # ConversationResponse
│   │   │   ├── faq.py               # FAQSearchRequest, FAQSearchResponse
│   │   │   └── nlp.py               # NLPRequest, IntentResponse, EntityResponse
│   │   └── services/                # Core Business & AI Services
│   │       ├── gemini.py            # Gemini API client, retries, context-aware reply generator
│   │       ├── prompts.py           # System prompts, tone instructions, thresholds, history limits
│   │       ├── faq_search.py        # FAQ search engine, scoring (keyword coverage + Jaccard)
│   │       ├── faq_service.py       # FAQ dataset loader and ID query functions
│   │       ├── conversation_state.py# Multi-turn slot tracking, ambiguity detection, topic shifts
│   │       ├── business_data.py     # Sample business facts (orders, shipments, products, policies)
│   │       ├── context_builder.py   # Grounded prompt context builder and formatter
│   │       ├── response_formatter.py# Dynamic formatting guidance per intent
│   │       ├── response_quality.py  # 6-dimension response quality scoring engine
│   │       └── response_validator.py# Candidate response validator & safe fallback generator
│   └── tests/                       # Automated Test Suite (307 Tests)
│       ├── conftest.py              # Pytest fixtures and TestClient initialization
│       ├── test_main.py             # Basic health & validation endpoint tests
│       ├── test_conversations.py    # Conversation creation and history tests
│       ├── test_database.py         # SQLAlchemy SQLite persistence tests
│       ├── test_faq_data.py         # FAQ dataset integrity tests
│       ├── test_faq_search.py       # FAQ search relevance scoring tests
│       ├── test_context_reply.py    # Context-aware reply & history tests
│       ├── test_faq_first_reply.py  # FAQ-first routing and Gemini bypass tests
│       ├── test_gemini.py           # Gemini service & error handling tests
│       ├── test_nlp.py              # NLP text cleaning & tokenization tests
│       ├── test_intent.py           # Intent recognition accuracy tests
│       ├── test_retrieval.py        # Business data retrieval & context injection tests
│       ├── test_conversation_state.py # Multi-turn slot memory & carry-forward tests
│       ├── test_day22_23.py         # Response quality, formatting, & validator tests
│       ├── test_response_reliability.py # Reliability, contractions, & edge-case tests
│       ├── test_day27_reliability.py # Day 27 edge-case hardening & boundary tests
│       └── test_day28_day29_validation.py # Day 28 & 29 security, performance, & scenario tests
│
├── data/                            # Static Knowledge Base & Mock Data
│   ├── faq.json                     # Curated 25-item customer support FAQ database
│   └── sample_business_data.json    # Business facts for orders, shipments, products, policies
│
└── frontend/                        # React 19 + Vite Frontend Application
    ├── package.json                 # npm dependencies and build scripts
    ├── vite.config.js               # Vite build configuration
    ├── index.html                   # HTML5 application shell
    └── src/
        ├── main.jsx                 # React root renderer
        ├── App.jsx                  # Main state container & conversation coordinator
        ├── services/
        │   └── api.js               # Backend REST API client with error handling
        ├── components/              # Modular UI Components
        │   ├── ChatHeader.jsx       # Header with bot title, avatar, and Clear button
        │   ├── MessageList.jsx      # Message feed with auto-scroll anchor
        │   ├── MessageBubble.jsx    # User/bot bubble styling and timestamps
        │   ├── ChatInput.jsx        # Text input, character counter, send button
        │   ├── LoadingIndicator.jsx # Three-dot typing animation
        │   ├── FAQSuggestions.jsx   # Quick prompt suggestion pills
        │   ├── ErrorMessage.jsx     # Error banner with retry button
        │   └── EmptyChat.jsx        # Empty state prompt
        └── styles/
            └── global.css           # Complete responsive stylesheet (mobile/tablet/desktop)
```

---

## 9. Testing and Verification Results

The complete application was verified in **Day 30 Final Project Verification & Completion Audit**:

### Backend Regression Test Suite
```
============================= test session starts =============================
platform win32 -- Python 3.14.8, pytest-9.1.1, pluggy-1.7.0
rootdir: backend
configfile: pytest.ini
plugins: anyio-4.15.1
collected 307 items

307 passed, 2 warnings in 10.27s
====================== 307 passed, 2 warnings in 10.27s =======================
```
- **Total Tests Collected:** 307
- **Total Tests Passed:** 307
- **Total Test Failures:** 0
- **Regression Count:** 0

### Frontend Production Build
```
> vite build
vite v7.3.7 building client environment for production...
transforming...
✓ 37 modules transformed.
rendering chunks...
computing gzip size...
dist/index.html                   0.43 kB │ gzip:  0.29 kB
dist/assets/index-DvhyHpRW.css    6.32 kB │ gzip:  1.75 kB
dist/assets/index-uSwoaXXm.js   228.83 kB │ gzip: 71.64 kB
✓ built in 2.08s
```
- **Build Status:** Successful (Exit code 0)
- **Compilation Errors:** 0
- **Compilation Warnings:** 0

### Core End-to-End Scenarios Verified
1. **FAQ Response Flow (PASSED):** Verified that FAQ-matching questions (*"Where is my package?"*) return verified answers directly with `answer_source="faq"`, bypass Gemini completely (0 LLM calls), and persist in SQLite.
2. **Gemini Fallback Flow (PASSED):** Verified that non-FAQ queries (*"Check status of order ORD-12345"*) fall back to Gemini, receive injected business facts, validate candidate replies, and persist with `answer_source="gemini"`.
3. **Multi-Turn Conversation Flow (PASSED):** Verified that 7-turn conversations maintain slot memory, observe the `HISTORY_LIMIT = 10` cap, maintain chronological order, and remain strictly isolated between distinct sessions.
4. **Error & Recovery Flow (PASSED):** Verified that invalid inputs (whitespace, oversized text) and simulated 502 Gemini outages reject cleanly without corrupting SQLite records or breaking subsequent conversational turns.

---

## 10. Security and Production Considerations

When transitioning from local development to production, observe the following architectural recommendations:

1. **API Keys and Secrets:** Always supply `GEMINI_API_KEY` via encrypted environment secret managers (e.g., AWS Secrets Manager, GCP Secret Manager, or Docker secrets). Never commit `.env` files to source repositories.
2. **CORS Origins:** The application currently allows `http://localhost:5173` and `http://127.0.0.1:5173` for Vite local development. For production deployments, specify your public production domain in `main.py` or load allowed origins from an environment variable (`CORS_ALLOWED_ORIGINS`).
3. **Database Scalability:** SQLite is optimal for single-instance, embedded development and testing. For multi-container horizontal scaling, switch the SQLAlchemy connection string in `database.py` to an enterprise database such as PostgreSQL or Google Cloud SQL.
4. **Semantic FAQ Search:** The current FAQ engine uses keyword coverage and Jaccard similarity. For broader vocabulary coverage and multilingual support, consider integrating a vector embedding database (such as ChromaDB or pgvector) in future iterations.

---

## 11. Final Project Status

### Project Status: Complete and Working

- **All 30 Days of Planned Development Completed:** The full end-to-end curriculum has been realized.
- **Architectural Integration Verified:** Frontend UI, FastAPI backend, SQLite database, NLP intent/entity modules, FAQ retrieval engine, Gemini AI fallback, and pre-delivery validation layers work together seamlessly.
- **Automated Test Suite Verified:** All **307 backend tests pass with 0 failures**.
- **Frontend Production Build Verified:** The Vite frontend compiles with **0 errors and 0 warnings**.
- **Production-Ready Standards:** Verified adherence to input validation, secure credential isolation, error resilience, and database transaction integrity.
