# 🔍 AIRA AI — Autonomous Research Agent

> **An autonomous AI research assistant that performs real-time web retrieval, dense semantic passage ranking with neural embeddings, and streaming answer synthesis. Built with multi-stage search modes, interactive follow-up reasoning, side-by-side topic comparison, voice dictation, and secure multi-user JWT authentication with token revocation.**

---

## ⚡ Features

- **Autonomous Multi-Source Search:** Automatically queries, scrapes, and parses relevant web resources in real time.
- **Dense Semantic Ranking:** Leverages sentence-transformers/all-MiniLM-L6-v2 for cosine-similarity passage scoring.
- **Real-Time SSE Streaming:** Live non-blocking multi-stage progress tracking (Scrape → Parse → Rank → Synthesize).
- **Speech-to-Text Voice Dictation:** Browser-native voice input via the Web Speech API with real-time transcription.
- **Side-by-Side Topic Comparison:** Comparative dual-perspective analysis for contrasting subjects.
- **Interactive Follow-Up Threads:** Context-aware Q&A reasoning directly attached to research sessions.
- **Secure Multi-User Auth:** Token-based JWT authentication with persistent user isolation and stateful token blacklisting.
- **Multi-Format Exports:** Export reports directly to formatted PDF and Markdown, or bulk-export all research history as a structured ZIP archive.
- **Adaptive Themes:** Three tailored aesthetic modes: **Dark**, **Light**, and **OLED Pure Black**.

---

## 🛠️ Tech Stack

- **Backend:** Python 3.10+, Flask, PyJWT, SQLite (WAL mode)
- **NLP / Embeddings:** PyTorch, Sentence-Transformers (ll-MiniLM-L6-v2)
- **Scraping & Parsing:** BeautifulSoup4, Requests
- **Document Export:** fpdf2, zipfile
- **Frontend:** Vanilla JS (ES6+), Vanilla CSS (Custom tokens), HTML5, Web Speech API

---

## 🚀 Quick Start

### 1. Clone the repository
`ash
git clone https://github.com/harinaath7777/AIRA-AI.git
cd AIRA-AI
`

### 2. Install dependencies
`ash
pip install -r requirements.txt
`

### 3. Run the application
`ash
python server.py
`

### 4. Access the web interface
Open [http://localhost:5000](http://localhost:5000) in your web browser. Create an account on the **Create Account** tab and start researching.

---

## 🔒 Security & Privacy

- All user data and search histories are strictly scoped by user_id.
- Access tokens expire after 8 hours; token revocations upon sign-out are tracked in a persistent blacklist.
- Local SQLite databases (uth.db and esearch.db) are excluded from git version control.

---

## 📄 License

This project is licensed under the MIT License.
