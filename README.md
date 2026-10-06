# AIRA AI: Autonomous Information Retrieval and Research Assistant

An autonomous, end-to-end research intelligence system designed for real-time web retrieval, dense semantic passage reranking, and multi-stage answer synthesis. Built on an event-driven architecture utilizing Server-Sent Events (SSE), neural sentence embeddings, and stateless JSON Web Token (JWT) authentication with database-backed token revocation.

---

## Architectural Overview

AIRA AI decouples the information retrieval lifecycle into deterministic, verifiable stages:

1. **Acquisition Layer:** Executes concurrent, multi-query web searches and extracts unstructured HTML payloads from authoritative endpoints.
2. **Preprocessing and Parsing:** Strips extraneous boilerplate, isolates canonical text segments, and decomposes documents into discrete passage chunks.
3. **Dense Semantic Embedding and Reranking:** Computes dense vector representations via a local bi-encoder (`sentence-transformers/all-MiniLM-L6-v2`) and scores passage relevance against the target query using cosine similarity metric spaces.
4. **Synthesis Engine:** Aggregates top-k scoring passages, structures contextual references, and performs multi-mode extractive summarization.
5. **Streaming Telemetry Transport:** Pushes continuous stage transitions and partial synthesis frames to the client via Server-Sent Events (SSE).
6. **Persistence and Data Isolation:** Scopes all analytical sessions, comparative evaluations, and follow-up threads strictly by authenticated tenant (`user_id`) using an asynchronous SQLite engine operating in Write-Ahead Logging (WAL) mode.

---

## Technical Specifications

### Core Engine Modes
- **Quick Mode:** Low-latency search prioritizing latency-critical overview summaries and primary sources.
- **Normal Mode:** Balanced depth incorporating comprehensive passage extraction across diversified web domains.
- **Deep Mode:** High-recall exploration aggregating extensive corpora, deep text parsing, and rigorous cosine-similarity thresholds.

### Advanced Analytical Modules
- **Context-Aware Follow-Up Engine:** Maintains session conversational state, enabling recursive deep dives into specific source segments.
- **Dual-Perspective Comparative Synthesis:** Executes parallel research pipelines on contrasting topics and renders structured comparison metrics.
- **Voice Transcription Interface:** Real-time client-side speech-to-text dictation utilizing browser-native Web Speech API.
- **Document Serialization:** Single-click generation of formatted PDF reports, Markdown exports, and full-history hierarchical ZIP archives.

---

## Project Structure

```
AIRA-AI/
|-- auth.py              # Cryptographic authentication, password hashing, JWT governance
|-- database.py          # Relational schemas, migrations, and tenant-scoped query execution
|-- exporter.py          # PDF generation engine, Markdown serialisation, character sanitisation
|-- research_agent.py    # Autonomous agent lifecycle, iterative loop, fallback pipelines
|-- research_engine.py   # Web scraping routines, sentence transformer embeddings, reranking
|-- server.py            # Flask WSGI application, routing layer, SSE streaming endpoints
|-- requirements.txt     # Locked production dependencies
|-- static/
|   |-- app.js           # Client application logic, state manager, SSE handler
|   |-- style.css        # Responsive design system, tokens, theme definitions
|   +-- aira_icon.jpg    # Application branding asset
+-- templates/
    |-- index.html       # Primary research application interface
    +-- login.html       # Authentication portal (Sign In / Registration)
```

---

## Prerequisites

- Python 3.10 or higher
- PyTorch runtime compatible with host architecture (CPU or CUDA-enabled GPU)

---

## Installation and Setup

### 1. Repository Acquisition

```bash
git clone https://github.com/harinaath7777/AIRA-AI.git
cd AIRA-AI
```

### 2. Environment Configuration

Initialize an isolated virtual environment:

```bash
python -m venv venv
```

Activate the virtual environment:

- Windows:
```cmd
venv\Scripts\activate
```
- Linux / macOS:
```bash
source venv/bin/activate
```

### 3. Dependency Installation

```bash
pip install -r requirements.txt
```

### 4. Running the Application

```bash
python server.py
```

Upon initial startup, neural embedding weights (`sentence-transformers/all-MiniLM-L6-v2`) are fetched and cached locally. Access the application interface at `http://localhost:5000`.

---

## API Specification

### Authentication Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | /api/auth/register | Registers a new user account with hashed password storage |
| POST | /api/auth/login | Validates credentials and returns signed access and refresh JWTs |
| POST | /api/auth/logout | Revokes active token by appending JTI to blacklist |
| GET | /api/auth/me | Validates active session token and returns authenticated principal |

### Research and Streaming Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | /api/research/stream | Server-Sent Events stream executing multi-stage research workflows |
| GET | /api/followup/stream | SSE endpoint executing contextual follow-up reasoning |
| POST | /api/compare | Parallel execution pipeline for comparative topic analysis |
| GET | /api/stages | Returns enumeration of research progression milestones |

### Data and Export Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | /api/history | Returns paginated research history scoped to caller |
| GET | /api/history/export-zip | Generates a compressed ZIP archive containing all session reports |
| GET | /api/export/pdf/<id> | Compiles and streams a formatted PDF report for a given session |
| GET | /api/export/markdown/<id> | Returns a structured Markdown document representing session results |

---

## Security and Data Isolation

- **Token Governance:** Stateless JSON Web Tokens signed with HMAC-SHA256 (`HS256`) and persistent secret key configuration.
- **Token Blacklisting:** Explicit sign-out commits token identifiers (`jti`) to an indexed blacklist table in `auth.db`.
- **Password Hashing:** Passwords hashed with PBKDF2 and SHA-256 via Werkzeug security primitives.
- **Tenant Scoping:** All database transactions enforce parameterized queries scoped to the authenticated caller identifier (`user_id`).

---

## License

This project is distributed under the terms of the MIT License.
