/* ═══════════════════════════════════════════════════════════════
   AIRA AI — app.js
   Frontend logic: search, SSE progress, results, history,
   saved, follow-up, compare, export.
═══════════════════════════════════════════════════════════════ */

// ─────────────────────────────────────────────────────────────
// AUTH HELPERS
// ─────────────────────────────────────────────────────────────
function getToken()   { return localStorage.getItem('aira_token') || ''; }
function getUser()    { try { return JSON.parse(localStorage.getItem('aira_user') || '{}'); } catch(_) { return {}; } }
function clearAuth()  { localStorage.removeItem('aira_token'); localStorage.removeItem('aira_refresh'); localStorage.removeItem('aira_user'); }

/** Fetch with Authorization header attached automatically. */
async function authFetch(url, opts = {}) {
  const token = getToken();
  opts.headers = { ...(opts.headers || {}), 'Authorization': `Bearer ${token}` };
  const res = await fetch(url, opts);
  if (res.status === 401) {
    clearAuth();
    window.location.href = '/login';
    throw new Error('Unauthenticated');
  }
  return res;
}

/** Append token to SSE URL since EventSource cannot set headers. */
function sseUrl(path) {
  const sep = path.includes('?') ? '&' : '?';
  return `${path}${sep}token=${encodeURIComponent(getToken())}`;
}

// ─────────────────────────────────────────────────────────────
// STATE
// ─────────────────────────────────────────────────────────────
const state = {
  mode: "normal",
  compareMode: "normal",
  currentHistoryId: null,
  currentResult: null,
  stages: [],
};

// ─────────────────────────────────────────────────────────────
// INIT
// ─────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", async () => {
  // Initialize theme
  initTheme();

  // Redirect to login if no token
  if (!getToken()) {
    window.location.href = '/login';
    return;
  }

  // Show user info in sidebar
  const user = getUser();
  const userEl = document.getElementById('sidebarUser');
  if (userEl && user.username) userEl.textContent = user.username;

  // Load stage labels from backend
  try {
    const res = await authFetch("/api/stages");
    const json = await res.json();
    state.stages = json.stages || [];
  } catch (_) {
    state.stages = [
      "Searching the web...",
      "Finding relevant sources...",
      "Reading webpages...",
      "Processing information...",
      "Finding relevant passages...",
      "Creating summary...",
      "Research complete.",
    ];
  }

  // Keyboard shortcut: Enter in search box
  document.getElementById("searchInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      startResearch();
    }
  });

  // Keyboard shortcut: Enter in follow-up
  document.getElementById("followupInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      askFollowup();
    }
  });

  // Auto-resize textareas
  ["searchInput", "followupInput"].forEach((id) => {
    const el = document.getElementById(id);
    el.addEventListener("input", () => {
      el.style.height = "auto";
      el.style.height = el.scrollHeight + "px";
    });
  });

  // Sidebar toggle
  document.getElementById("sidebarToggle").addEventListener("click", () => {
    document.getElementById("sidebar").classList.toggle("collapsed");
  });

  // Sidebar history
  loadSidebarHistory();
});

// ─────────────────────────────────────────────────────────────
// LOGOUT
// ─────────────────────────────────────────────────────────────
async function logout() {
  try {
    await authFetch('/api/auth/logout', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: localStorage.getItem('aira_refresh') || '' }),
    });
  } catch (_) {/* ignore network errors on logout */}
  clearAuth();
  window.location.href = '/login';
}

// ─────────────────────────────────────────────────────────────
// PAGE NAVIGATION
// ─────────────────────────────────────────────────────────────
function showPage(name) {
  document.querySelectorAll(".page").forEach((p) => p.classList.remove("active"));
  document.querySelectorAll(".nav-btn").forEach((b) => b.classList.remove("active"));

  const pageMap = {
    home:    "pageHome",
    loading: "pageLoading",
    result:  "pageResult",
    history: "pageHistory",
    saved:   "pageSaved",
    compare: "pageCompare",
  };
  const navMap = {
    home:    "navHome",
    history: "navHistory",
    saved:   "navSaved",
    compare: "navCompare",
  };

  const pageEl = document.getElementById(pageMap[name]);
  if (pageEl) pageEl.classList.add("active");

  const navEl = document.getElementById(navMap[name]);
  if (navEl) navEl.classList.add("active");

  // Load data for list pages
  if (name === "history") loadHistoryPage();
  if (name === "saved")   loadSavedPage();

  // Scroll main to top
  document.getElementById("main").scrollTop = 0;
}

// ─────────────────────────────────────────────────────────────
// MODE SELECTION
// ─────────────────────────────────────────────────────────────
function setMode(mode) {
  state.mode = mode;
  document.querySelectorAll(".mode-tabs .mode-tab").forEach((b) => b.classList.remove("active"));
  const ids = { quick: "modeQuick", normal: "modeNormal", deep: "modeDeep" };
  const el = document.getElementById(ids[mode]);
  if (el) el.classList.add("active");
}

function setCompareMode(mode, btn) {
  state.compareMode = mode;
  if (btn) {
    const parent = btn.closest(".cmp-modes");
    if (parent) parent.querySelectorAll(".mode-tab").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
  }
}

// ─────────────────────────────────────────────────────────────
// SET EXAMPLE QUERY
// ─────────────────────────────────────────────────────────────
function setQuery(text) {
  const input = document.getElementById("searchInput");
  input.value = text;
  input.focus();
  input.style.height = "auto";
  input.style.height = input.scrollHeight + "px";
}

// ─────────────────────────────────────────────────────────────
// START RESEARCH
// ─────────────────────────────────────────────────────────────
function startResearch() {
  const query = document.getElementById("searchInput").value.trim();
  if (!query) {
    toast("Please enter a research question.", "error");
    return;
  }
  runResearch(query, state.mode);
}

function runResearch(query, mode) {
  // Reset state
  state.currentHistoryId = null;
  state.currentResult = null;

  // Show loading screen
  document.getElementById("loadingQuery").textContent = query;
  showPage("loading");
  buildProgressStages();

  const url = sseUrl(`/api/research/stream?q=${encodeURIComponent(query)}&mode=${encodeURIComponent(mode)}`);

  const evtSource = new EventSource(url);

  evtSource.onmessage = (e) => {
    const msg = JSON.parse(e.data);

    if (msg.type === "stage") {
      updateStage(msg.index);
    } else if (msg.type === "result") {
      evtSource.close();
      state.currentHistoryId = msg.id;
      state.currentResult = msg.data;
      renderResult(msg.data, msg.id);
      showPage("result");
      loadSidebarHistory();
    } else if (msg.type === "error") {
      evtSource.close();
      toast("Research error: " + msg.message, "error");
      showPage("home");
    }
  };

  evtSource.onerror = () => {
    evtSource.close();
    toast("Connection error. Is the server running?", "error");
    showPage("home");
  };
}

// ─────────────────────────────────────────────────────────────
// PROGRESS STAGES
// ─────────────────────────────────────────────────────────────
function buildProgressStages() {
  const container = document.getElementById("progressStages");
  container.innerHTML = "";

  state.stages.forEach((label, i) => {
    const item = document.createElement("div");
    item.className = "stage-item";
    item.id = `stage-${i}`;

    const icon = document.createElement("div");
    icon.className = "stage-icon pending";
    icon.innerHTML = `<div class="stage-dot"></div>`;

    const labelEl = document.createElement("div");
    labelEl.className = "stage-label";
    labelEl.textContent = label;

    item.appendChild(icon);
    item.appendChild(labelEl);
    container.appendChild(item);
  });
}

function updateStage(activeIndex) {
  state.stages.forEach((_, i) => {
    const item = document.getElementById(`stage-${i}`);
    if (!item) return;
    const icon = item.querySelector(".stage-icon");

    if (i < activeIndex) {
      item.classList.remove("active");
      item.classList.add("done");
      icon.className = "stage-icon done";
      icon.innerHTML = `<span class="stage-check">✓</span>`;
    } else if (i === activeIndex) {
      item.classList.add("active");
      icon.className = "stage-icon active";
      icon.innerHTML = `<div class="stage-dot"></div>`;
    }
  });
}

// ─────────────────────────────────────────────────────────────
// RENDER RESULT
// ─────────────────────────────────────────────────────────────
function renderResult(data, historyId) {
  // Query
  document.getElementById("resultQuery").textContent = data.query || "";

  // Meta chips
  const meta = document.getElementById("resultMeta");
  meta.innerHTML = `
    <span class="result-meta-chip">
      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
      </svg>
      ${data.time?.toFixed(1) || "?"}s
    </span>
    <span class="result-meta-chip">
      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71"/>
        <path d="M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71"/>
      </svg>
      ${data.total_sources || 0} sources
    </span>
    <span class="result-meta-chip">${(data.mode || "normal").charAt(0).toUpperCase() + (data.mode || "normal").slice(1)}</span>
  `;

  // Save button state
  const saveBtn = document.getElementById("saveBtn");
  saveBtn.classList.remove("saved");
  saveBtn.innerHTML = `
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <path d="M19 21l-7-5-7 5V5a2 2 0 012-2h10a2 2 0 012 2z"/>
    </svg>
    Save
  `;

  // Summary
  const summaryEl = document.getElementById("resultSummary");
  if (data.error && !data.summary) {
    summaryEl.textContent = data.error;
  } else if (data.summary) {
    summaryEl.textContent = data.summary;
  } else {
    summaryEl.textContent = "No summary could be generated for this query.";
  }

  // Sources
  renderSources(data.sources || []);

  // Passages
  renderPassages(data.passages || []);

  // Clear follow-up thread
  document.getElementById("followupThread").innerHTML = "";
  document.getElementById("followupInput").value = "";
}

// ─────────────────────────────────────────────────────────────
// RENDER SOURCES
// ─────────────────────────────────────────────────────────────
function renderSources(sources) {
  const container = document.getElementById("resultSources");
  container.innerHTML = "";

  if (!sources.length) {
    container.innerHTML = `<div class="empty-state"><p>No sources found.</p></div>`;
    return;
  }

  sources.forEach((s, i) => {
    const score = s.score || 0;
    const scoreClass = score >= 0.7 ? "score-high" : score >= 0.5 ? "score-mid" : "score-low";
    const title = s.title || s.domain || s.url;
    const domain = s.domain || "";

    const card = document.createElement("a");
    card.href = s.url;
    card.target = "_blank";
    card.rel = "noopener noreferrer";
    card.className = "source-card";
    card.innerHTML = `
      <div class="source-card-num">Source ${i + 1}</div>
      <div class="source-card-title">${escHtml(title)}</div>
      <div class="source-card-domain">
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/>
          <path d="M12 2a15.3 15.3 0 014 10 15.3 15.3 0 01-4 10 15.3 15.3 0 01-4-10 15.3 15.3 0 014-10z"/>
        </svg>
        ${escHtml(domain)}
      </div>
      <span class="source-card-score ${scoreClass}">${(score * 100).toFixed(0)}% relevant</span>
    `;
    container.appendChild(card);
  });
}

// ─────────────────────────────────────────────────────────────
// RENDER PASSAGES
// ─────────────────────────────────────────────────────────────
function renderPassages(passages) {
  const container = document.getElementById("resultPassages");
  container.innerHTML = "";

  if (!passages.length) {
    container.innerHTML = `<div class="empty-state"><p>No relevant passages found.</p></div>`;
    return;
  }

  passages.forEach((p, i) => {
    const score = p.score || 0;
    const scoreClass = score >= 0.7 ? "score-high" : score >= 0.5 ? "score-mid" : "score-low";
    const domain = extractDomain(p.url || "");

    const card = document.createElement("div");
    card.className = "passage-card";
    card.id = `passage-${i}`;
    card.innerHTML = `
      <div class="passage-header" onclick="togglePassage(${i})">
        <div class="passage-domain">${escHtml(domain)}</div>
        <div class="passage-meta">
          <span class="passage-score-badge ${scoreClass}">${(score * 100).toFixed(0)}% relevant</span>
          <svg class="passage-chevron" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="6 9 12 15 18 9"/>
          </svg>
        </div>
      </div>
      <div class="passage-body">
        <div class="passage-text">"${escHtml(p.passage || "")}"</div>
        <div class="passage-url">
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71"/>
            <path d="M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71"/>
          </svg>
          <a href="${escHtml(p.url || "")}" target="_blank" rel="noopener noreferrer">${escHtml(p.url || "")}</a>
        </div>
      </div>
    `;
    container.appendChild(card);
  });

  // Open first passage by default
  if (passages.length) togglePassage(0);
}

function togglePassage(i) {
  const card = document.getElementById(`passage-${i}`);
  if (card) card.classList.toggle("open");
}

// ─────────────────────────────────────────────────────────────
// SAVE RESEARCH
// ─────────────────────────────────────────────────────────────
async function saveCurrentResearch() {
  if (!state.currentHistoryId) return;
  try {
    const res = await authFetch("/api/saved", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ history_id: state.currentHistoryId }),
    });
    const json = await res.json();
    if (json.ok) {
      const saveBtn = document.getElementById("saveBtn");
      saveBtn.classList.add("saved");
      saveBtn.innerHTML = `
        <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
          <path d="M19 21l-7-5-7 5V5a2 2 0 012-2h10a2 2 0 012 2z"/>
        </svg>
        Saved
      `;
      toast("Research saved!", "success");
    }
  } catch (_) {
    toast("Failed to save.", "error");
  }
}

// ─────────────────────────────────────────────────────────────
// EXPORT
// ─────────────────────────────────────────────────────────────
async function exportMarkdown() {
  if (!state.currentHistoryId) return;
  try {
    const res = await authFetch(`/api/export/markdown/${state.currentHistoryId}`);
    if (!res.ok) {
      toast("Failed to download Markdown report", "error");
      return;
    }
    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `aira_research_${state.currentHistoryId}.md`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
    toast("Markdown exported successfully", "success");
  } catch (err) {
    toast("Export failed: " + err.message, "error");
  }
}

async function exportPDF() {
  if (!state.currentHistoryId) return;
  try {
    toast("Generating PDF report...", "info");
    const res = await authFetch(`/api/export/pdf/${state.currentHistoryId}`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      toast(err.error || "Failed to download PDF report", "error");
      return;
    }
    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `aira_research_${state.currentHistoryId}.pdf`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
    toast("PDF downloaded successfully", "success");
  } catch (err) {
    toast("Export failed: " + err.message, "error");
  }
}

// ─────────────────────────────────────────────────────────────
// EXPORT ALL HISTORY TO ZIP
// ─────────────────────────────────────────────────────────────
async function exportHistoryZip() {
  const btn = document.getElementById('exportZipBtn');
  if (btn) btn.disabled = true;

  try {
    toast("Generating research history ZIP archive...", "info");
    const res = await authFetch('/api/history/export-zip');
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      toast(err.error || "No history found or failed to export ZIP", "error");
      if (btn) btn.disabled = false;
      return;
    }

    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    const user = getUser();
    const username = user.username || 'user';
    a.download = `aira_research_history_${username}.zip`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
    toast("Full research history ZIP downloaded!", "success");
  } catch (err) {
    toast("Export failed: " + err.message, "error");
  } finally {
    if (btn) btn.disabled = false;
  }
}

// ─────────────────────────────────────────────────────────────
// THEME SWITCHER (Dark / Light / OLED)
// ─────────────────────────────────────────────────────────────
function initTheme() {
  const saved = localStorage.getItem('aira_theme') || 'dark';
  setTheme(saved, false);
}

function setTheme(name, showToast = true) {
  if (!['dark', 'light', 'oled'].includes(name)) name = 'dark';
  document.documentElement.setAttribute('data-theme', name);
  localStorage.setItem('aira_theme', name);

  document.querySelectorAll('.theme-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.theme === name);
  });

  if (showToast) {
    const labels = { dark: 'Dark', light: 'Light', oled: 'OLED Pure Black' };
    toast(`${labels[name]} theme enabled`, 'info');
  }
}

// ─────────────────────────────────────────────────────────────
// VOICE INPUT (SPEECH-TO-TEXT)
// ─────────────────────────────────────────────────────────────
let activeRecognition = null;
let activeMicBtn = null;

function toggleVoiceInput(targetInputId, micBtnId) {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    toast("Voice input requires Web Speech API (supported in Chrome, Edge, Safari)", "error");
    return;
  }

  const micBtn = document.getElementById(micBtnId);
  const targetInput = document.getElementById(targetInputId);
  if (!targetInput) return;

  // Toggle off if currently active
  if (activeRecognition) {
    try { activeRecognition.stop(); } catch(_) {}
    activeRecognition = null;
    if (activeMicBtn) {
      activeMicBtn.classList.remove('listening');
      activeMicBtn = null;
    }
    toast("Voice input stopped.", "info");
    return;
  }

  try {
    const recognition = new SpeechRecognition();
    recognition.lang = 'en-US';
    recognition.continuous = false;
    recognition.interimResults = true;

    recognition.onstart = () => {
      if (micBtn) micBtn.classList.add('listening');
      activeMicBtn = micBtn;
      activeRecognition = recognition;
      toast("Listening... speak your research prompt.", "info");
    };

    let baseText = targetInput.value ? targetInput.value.trim() + " " : "";

    recognition.onresult = (event) => {
      let transcript = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        transcript += event.results[i][0].transcript;
      }
      targetInput.value = baseText + transcript;
      // Auto-resize
      targetInput.style.height = "auto";
      targetInput.style.height = targetInput.scrollHeight + "px";
    };

    recognition.onerror = (event) => {
      console.warn("Speech recognition error:", event.error);
      if (micBtn) micBtn.classList.remove('listening');
      activeRecognition = null;
      activeMicBtn = null;
      if (event.error === 'not-allowed') {
        toast("Microphone access blocked. Please allow mic permission.", "error");
      } else if (event.error !== 'aborted') {
        toast("Voice input error: " + event.error, "error");
      }
    };

    recognition.onend = () => {
      if (micBtn) micBtn.classList.remove('listening');
      activeRecognition = null;
      activeMicBtn = null;
    };

    recognition.start();
  } catch (err) {
    console.error("Speech recognition start failed:", err);
    toast("Could not start voice recognition: " + err.message, "error");
    if (micBtn) micBtn.classList.remove('listening');
    activeRecognition = null;
    activeMicBtn = null;
  }
}

// ─────────────────────────────────────────────────────────────
// FOLLOW-UP
// ─────────────────────────────────────────────────────────────
function askFollowup() {
  const question = document.getElementById("followupInput").value.trim();
  if (!question || !state.currentHistoryId) {
    if (!question) toast("Please enter a follow-up question.", "error");
    return;
  }

  const btn = document.getElementById("followupBtn");
  btn.disabled = true;
  btn.innerHTML = `<div class="mini-spinner"></div>`;

  const thread = document.getElementById("followupThread");

  // Add question immediately
  const qEl = document.createElement("div");
  qEl.className = "followup-item";
  qEl.innerHTML = `
    <div class="followup-question">
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/>
      </svg>
      ${escHtml(question)}
    </div>
    <div class="followup-answer" id="followupAnswerPending">
      <div class="loading-pulse" style="width:12px;height:12px;display:inline-block;margin-right:6px;"></div>
      Researching...
    </div>
  `;
  thread.appendChild(qEl);
  thread.scrollIntoView({ behavior: "smooth" });

  document.getElementById("followupInput").value = "";

  const url = sseUrl(`/api/followup/stream?history_id=${state.currentHistoryId}&q=${encodeURIComponent(question)}&mode=quick`);
  const evtSource = new EventSource(url);

  evtSource.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    if (msg.type === "result") {
      evtSource.close();
      const answerEl = document.getElementById("followupAnswerPending");
      if (answerEl) {
        answerEl.id = "";
        answerEl.innerHTML = escHtml(msg.data?.summary || "No answer found.");
      }
      btn.disabled = false;
      btn.innerHTML = `
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>
        </svg>
      `;
    } else if (msg.type === "error") {
      evtSource.close();
      const answerEl = document.getElementById("followupAnswerPending");
      if (answerEl) {
        answerEl.id = "";
        answerEl.textContent = "Error: " + msg.message;
      }
      btn.disabled = false;
      btn.innerHTML = `
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>
        </svg>
      `;
    }
  };

  evtSource.onerror = () => {
    evtSource.close();
    btn.disabled = false;
    btn.innerHTML = `
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
        <line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>
      </svg>
    `;
    toast("Follow-up connection error.", "error");
  };
}

// ─────────────────────────────────────────────────────────────
// HISTORY PAGE
// ─────────────────────────────────────────────────────────────
async function loadHistoryPage() {
  const container = document.getElementById("historyList");
  container.innerHTML = `<div class="empty-state"><p>Loading...</p></div>`;
  try {
    const res  = await authFetch("/api/history");
    const json = await res.json();
    const rows = json.history || [];

    if (!rows.length) {
      container.innerHTML = `
        <div class="empty-state">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
          </svg>
          <p>No research history yet. Start by asking a question!</p>
        </div>`;
      return;
    }

    container.innerHTML = "";
    rows.forEach((row) => {
      const card = buildHistoryCard(row);
      container.appendChild(card);
    });
  } catch (_) {
    container.innerHTML = `<div class="empty-state"><p>Failed to load history.</p></div>`;
  }
}

async function loadSavedPage() {
  const container = document.getElementById("savedList");
  container.innerHTML = `<div class="empty-state"><p>Loading...</p></div>`;
  try {
    const res  = await authFetch("/api/saved");
    const json = await res.json();
    const rows = json.saved || [];

    if (!rows.length) {
      container.innerHTML = `
        <div class="empty-state">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M19 21l-7-5-7 5V5a2 2 0 012-2h10a2 2 0 012 2z"/>
          </svg>
          <p>No saved research yet. Save a result from the results page.</p>
        </div>`;
      return;
    }

    container.innerHTML = "";
    rows.forEach((row) => {
      const card = buildHistoryCard(row, true);
      container.appendChild(card);
    });
  } catch (_) {
    container.innerHTML = `<div class="empty-state"><p>Failed to load saved research.</p></div>`;
  }
}

function buildHistoryCard(row, isSaved = false) {
  const card = document.createElement("div");
  card.className = "history-card";

  const histId = row.history_id || row.id;
  const date = new Date(row.created_at + "Z").toLocaleString();
  const mode = row.mode || "normal";

  card.innerHTML = `
    <div class="history-card-left" onclick="openHistoryItem(${histId})">
      <div class="history-card-query">${escHtml(row.query)}</div>
      <div class="history-card-meta">
        <span class="history-card-mode">${escHtml(mode)}</span>
        <span>${date}</span>
      </div>
    </div>
    <div class="history-card-right">
      ${isSaved ? `
        <button class="icon-btn" onclick="unsaveItem(${histId}, this)" title="Unsave">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor">
            <path d="M19 21l-7-5-7 5V5a2 2 0 012-2h10a2 2 0 012 2z"/>
          </svg>
        </button>` : ""}
      <button class="icon-btn" onclick="deleteHistoryItem(${histId}, this)" title="Delete">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6"/>
          <path d="M10 11v6"/><path d="M14 11v6"/>
        </svg>
      </button>
    </div>
  `;
  return card;
}

async function openHistoryItem(historyId) {
  try {
    const res  = await authFetch(`/api/history/${historyId}`);
    const json = await res.json();
    if (!json.ok) { toast("Failed to load research.", "error"); return; }

    const item = json.item;
    state.currentHistoryId = historyId;
    state.currentResult = item.result;

    renderResult(item.result, historyId);

    // Restore follow-ups
    const thread = document.getElementById("followupThread");
    thread.innerHTML = "";
    (item.followups || []).forEach((fu) => {
      const el = document.createElement("div");
      el.className = "followup-item";
      el.innerHTML = `
        <div class="followup-question">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/>
          </svg>
          ${escHtml(fu.question)}
        </div>
        <div class="followup-answer">${escHtml(fu.answer?.summary || "No answer.")}</div>
      `;
      thread.appendChild(el);
    });

    if (item.saved) {
      const saveBtn = document.getElementById("saveBtn");
      saveBtn.classList.add("saved");
      saveBtn.innerHTML = `
        <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
          <path d="M19 21l-7-5-7 5V5a2 2 0 012-2h10a2 2 0 012 2z"/>
        </svg>
        Saved
      `;
    }

    showPage("result");
  } catch (_) {
    toast("Failed to load research.", "error");
  }
}

async function deleteHistoryItem(historyId, btn) {
  if (!confirm("Delete this research item?")) return;
  try {
    await authFetch(`/api/history/${historyId}`, { method: "DELETE" });
    const card = btn.closest(".history-card");
    if (card) card.remove();
    loadSidebarHistory();
    toast("Deleted.", "success");
  } catch (_) {
    toast("Failed to delete.", "error");
  }
}

async function unsaveItem(historyId, btn) {
  try {
    await authFetch(`/api/saved/${historyId}`, { method: "DELETE" });
    const card = btn.closest(".history-card");
    if (card) card.remove();
    toast("Removed from saved.", "success");
  } catch (_) {
    toast("Failed to unsave.", "error");
  }
}

// ─────────────────────────────────────────────────────────────
// SIDEBAR HISTORY
// ─────────────────────────────────────────────────────────────
async function loadSidebarHistory() {
  try {
    const res  = await authFetch("/api/history?limit=15");
    const json = await res.json();
    const rows = json.history || [];
    const container = document.getElementById("sidebarHistoryList");

    if (!rows.length) {
      container.innerHTML = `<div class="sidebar-empty">No research yet</div>`;
      return;
    }

    container.innerHTML = "";
    rows.forEach((row) => {
      const el = document.createElement("div");
      el.className = "sidebar-history-item";
      el.title = row.query;
      el.textContent = row.query;
      el.onclick = () => openHistoryItem(row.id);
      container.appendChild(el);
    });
  } catch (_) {/* silent */}
}

// ─────────────────────────────────────────────────────────────
// COMPARE
// ─────────────────────────────────────────────────────────────
function startCompare() {
  const topicA = document.getElementById("compareA").value.trim();
  const topicB = document.getElementById("compareB").value.trim();
  if (!topicA || !topicB) {
    toast("Please enter both topics.", "error");
    return;
  }

  const progressEl = document.getElementById("compareProgress");
  const resultEl   = document.getElementById("compareResult");
  progressEl.style.display = "flex";
  progressEl.innerHTML = `<div class="loading-pulse" style="width:14px;height:14px;flex-shrink:0;"></div> Starting comparison...`;
  resultEl.innerHTML = "";

  const url = sseUrl(`/api/compare/stream?a=${encodeURIComponent(topicA)}&b=${encodeURIComponent(topicB)}&mode=${encodeURIComponent(state.compareMode)}`);
  const evtSource = new EventSource(url);

  evtSource.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    if (msg.type === "stage") {
      progressEl.innerHTML = `<div class="loading-pulse" style="width:14px;height:14px;flex-shrink:0;"></div> ${escHtml(msg.message)}`;
    } else if (msg.type === "result") {
      evtSource.close();
      progressEl.style.display = "none";
      renderComparison(msg.data);
    } else if (msg.type === "error") {
      evtSource.close();
      progressEl.style.display = "none";
      toast("Comparison error: " + msg.message, "error");
    }
  };

  evtSource.onerror = () => {
    evtSource.close();
    progressEl.style.display = "none";
    toast("Comparison connection error.", "error");
  };
}

function renderComparison(data) {
  const container = document.getElementById("compareResult");
  const a = data.result_a || {};
  const b = data.result_b || {};

  container.innerHTML = `
    <div class="compare-result-header">
      <div class="compare-topic-box">
        <div class="compare-topic-label">Topic A</div>
        <div class="compare-topic-name">${escHtml(data.topic_a)}</div>
        <div class="compare-topic-summary">${escHtml(a.summary || "No summary.")}</div>
      </div>
      <div class="compare-topic-box">
        <div class="compare-topic-label">Topic B</div>
        <div class="compare-topic-name">${escHtml(data.topic_b)}</div>
        <div class="compare-topic-summary">${escHtml(b.summary || "No summary.")}</div>
      </div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;">
      <div>
        <div class="section-label" style="margin-bottom:12px;">Sources — ${escHtml(data.topic_a)}</div>
        ${buildSourceList(a.sources || [])}
      </div>
      <div>
        <div class="section-label" style="margin-bottom:12px;">Sources — ${escHtml(data.topic_b)}</div>
        ${buildSourceList(b.sources || [])}
      </div>
    </div>
  `;
}

function buildSourceList(sources) {
  if (!sources.length) return `<p style="color:var(--text-dim);font-size:0.83rem">No sources found.</p>`;
  return sources.map((s, i) => {
    const score = s.score || 0;
    const scoreClass = score >= 0.7 ? "score-high" : score >= 0.5 ? "score-mid" : "score-low";
    return `
      <div style="margin-bottom:8px;padding:10px 12px;background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-sm);">
        <a href="${escHtml(s.url)}" target="_blank" rel="noopener noreferrer" style="font-size:0.82rem;font-weight:500;">${escHtml(s.title || s.domain || s.url)}</a>
        <div style="margin-top:4px;">
          <span class="source-card-score ${scoreClass}" style="font-size:0.68rem;">${(score * 100).toFixed(0)}%</span>
        </div>
      </div>
    `;
  }).join("");
}

// ─────────────────────────────────────────────────────────────
// TOAST NOTIFICATIONS
// ─────────────────────────────────────────────────────────────
function toast(message, type = "") {
  // Remove existing
  document.querySelectorAll(".toast").forEach((t) => t.remove());
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.textContent = message;
  document.body.appendChild(el);
  requestAnimationFrame(() => {
    requestAnimationFrame(() => el.classList.add("show"));
  });
  setTimeout(() => {
    el.classList.remove("show");
    setTimeout(() => el.remove(), 300);
  }, 3000);
}

// ─────────────────────────────────────────────────────────────
// UTILITIES
// ─────────────────────────────────────────────────────────────
function escHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function extractDomain(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch (_) {
    return url;
  }
}
