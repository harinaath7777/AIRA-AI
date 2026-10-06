AIRA AI: Autonomous Information Retrieval and Research Assistant
An autonomous, end-to-end research intelligence system designed for real-time web retrieval, dense semantic passage reranking, and multi-stage answer synthesis. Built on an event-driven architecture utilizing Server-Sent Events (SSE), neural sentence embeddings, and stateless JSON Web Token (JWT) authentication with database-backed token revocation.

Architectural Overview
AIRA AI decouples the information retrieval lifecycle into deterministic, verifiable stages:

Acquisition Layer: Executes concurrent, multi-query web searches and extracts unstructured HTML payloads from authoritative endpoints.
Preprocessing & Parsing: Strips extraneous boilerplate, isolates canonical text segments, and decomposes documents into discrete passage chunks.
Dense Semantic Embedding & Reranking: Computes dense vector representations via a local bi-encoder (sentence-transformers/all-MiniLM-L6-v2) and scores passage relevance against the target query using cosine similarity metric spaces.
Synthesis Engine: Aggregates top-k scoring passages, structures contextual references, and performs multi-mode extractive summarization.
Streaming Telemetry Transport: Pushes continuous stage transitions and partial synthesis frames to the client via Server-Sent Events (SSE).
Persistence & Data Isolation: Scopes all analytical sessions, comparative evaluations, and follow-up threads strictly by authenticated tenant (user_id) using an asynchronous SQLite engine operating in Write-Ahead Logging (WAL) mode.
System Architecture
+-----------------------------------------------------------------------------+
|                                Client Layer                                 |
|  - Vanilla ES6+ Interface     - Web Speech API Dictation                    |
|  - SSE EventSource Consumer   - CSS Token Architecture (Dark / Light / OLED)|
+-----------------------------------------------------------------------------+
                                      |
                           HTTPS / SSE | JSON Web Tokens
                                      v
+-----------------------------------------------------------------------------+
|                            Application Layer (Flask)                        |
|  - Rate-Limiting & Validation - Auth Decorators (@require_auth)             |
|  - SSE Stream Multiplexer     - Document Exporters (PDF, Markdown, ZIP)     |
+-----------------------------------------------------------------------------+
               |                                           |
               v                                           v
+------------------------------+             +--------------------------------+
|       Research Engine        |             |       Persistence Tier         |
|  - DuckDuckGo Search API     |             |  - auth.db (Users, Blacklist)  |
|  - BeautifulSoup4 Scraper    |             |  - research.db (History, Tags) |
|  - all-MiniLM-L6-v2 Embedder |             |  - SQLite (WAL Mode, Cascades) |
|  - Cosine Distance Reranker  |             +--------------------------------+
+------------------------------+
Technical Specifications
Core Engine Modes
Quick Mode: Low-latency search prioritizing latency-critical overview summaries and primary sources.
Normal Mode: Balanced depth incorporating comprehensive passage extraction across diversified web domains.
Deep Mode: High-recall exploration aggregating extensive corpora, deep text parsing, and rigorous cosine-similarity thresholds.
Advanced Analytical Modules
Context-Aware Follow-Up Engine: Maintains session conversational state, enabling recursive deep dives into specific source segments.
Dual-Perspective Comparative Synthesis: Executes parallel research pipelines on contrasting topics and renders structured comparison metrics.
Voice Transcription Interface: Real-time client-side speech-to-text dictation utilizing browser-native Web Speech API.
Document Serialization: Single-click generation of Latin-1 compliant PDF reports (fpdf2), Markdown exports, and full-history hierarchical ZIP archives.
Directory Structure
AIRA-AI/
├── auth.py              # Cryptographic authentication, password hashing, JWT governance
├── database.py          # Relational schemas, migrations, and tenant-scoped query execution
├── exporter.py          # PDF generation engine, Markdown serialisation, unicode sanitisation
├── research_agent.py    # Autonomous agent lifecycle, iterative loop, fallback pipelines
├── research_engine.py   # Web scraping routines, sentence transformer embeddings, reranking
├── server.py            # Flask WSGI application, routing layer, SSE streaming endpoints
├── requirements.txt     # Locked production dependencies
├── static/
│   ├── app.js           # Client application logic, state manager, SSE handler
│   ├── style.css        # Responsive design system, tokens, theme definitions
│   └── aira_icon.jpg    # Application branding asset
└── templates/
    ├── index.html       # Primary research application interface
    └── login.html       # Authentication portal (Sign In / Registration)
Installation and Setup
Prerequisites
Python 3.10 or higher
PyTorch runtime compatible with the host architecture (CPU or CUDA-enabled GPU)
1. Repository Acquisition
bash
git clone https://github.com/harinaath7777/AIRA-AI.git
cd AIRA-AI
2. Environment Configuration
Initialize an isolated virtual environment:

bash
python -m venv venv
# On Linux/macOS:
source venv/bin/activate
# On Windows:
venv\Scripts\activate
3. Dependency Installation
Install required packages via pip:

bash
pip install -r requirements.txt
4. Running the Service
Launch the Flask development server:

bash
python server.py
Upon startup, the bi-encoder weights (sentence-transformers/all-MiniLM-L6-v2) are loaded into memory and cached locally. Access the application interface at http://localhost:5000.

API Specification
Authentication Endpoints
Method	Endpoint	Description
POST	/api/auth/register	Registers a new user account with hashed password storage.
POST	/api/auth/login	Validates credentials and returns signed access and refresh JWTs.
POST	/api/auth/logout	Revokes the active token by adding its unique JTI to the blacklist.
GET	/api/auth/me	Validates active session token and returns authenticated principal.
Research and Streaming Endpoints
Method	Endpoint	Description
GET	/api/research/stream	Server-Sent Events stream executing multi-stage research workflows.
GET	/api/followup/stream	SSE endpoint executing contextual follow-up reasoning on existing history.
POST	/api/compare	Parallel execution pipeline for comparative topic analysis.
GET	/api/stages	Returns enumeration of research progression milestones.
Data and Export Endpoints
Method	Endpoint	Description
GET	/api/history	Returns paginated research history scoped to the caller.
GET	/api/history/export-zip	Generates a compressed ZIP archive containing all session reports.
GET	/api/export/pdf/<id>	Compiles and streams a formatted PDF report for a given session.
GET	/api/export/markdown/<id>	Returns a structured Markdown document representing session results.
Security Architecture
Token Governance: Authentication utilizes asymmetric/HMAC signed JSON Web Tokens (HS256). Access tokens carry an 8-hour time-to-live (TTL); refresh tokens carry a 30-day lifetime.
Stateful Revocation: Token revocation relies on an append-only token blacklist table populated on sign-out, validating individual jti claims during middleware execution.
Password Hashing: Passwords are salted and hashed utilizing PBKDF2 with SHA-256 (pbkdf2:sha256) via Werkzeug security primitives.
Tenant Isolation: All database transactions execute parameterized queries filtered by the cryptographic subject identifier (sub claim), mitigating lateral privilege escalation.
License
This project is distributed under the terms of the MIT License. Refer to the LICENSE file for details.
