# server.py
# Flask backend for AIRA AI Research Assistant.
# Features: JWT auth with token blacklisting, per-user data, SSE streaming, PDF/MD export.

import json
import queue
import threading

from flask import Flask, Response, jsonify, redirect, render_template, request, url_for
from flask_cors import CORS

import auth
import database as db
from exporter import export_markdown, export_pdf
from research_engine import STAGES, ShortResearchAgent

app = Flask(__name__, static_folder="static", template_folder="templates")
CORS(app)

# ─────────────────────────────────────────────────────────────
# Single shared agent instance (embedding model loaded once)
# ─────────────────────────────────────────────────────────────
print("Initialising AIRA research agent...")
agent = ShortResearchAgent()
print("Agent ready. Visit http://localhost:5000")


# ══════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════

def _ok(data):
    return jsonify({"ok": True, **data})

def _err(msg, status=400):
    return jsonify({"ok": False, "error": msg}), status

def _sse_headers():
    return {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}

def _sse(gen):
    return Response(gen, mimetype="text/event-stream", headers=_sse_headers())

def _drain(q, timeout=120):
    """Drain a progress queue and yield SSE strings."""
    while True:
        try:
            item = q.get(timeout=timeout)
        except queue.Empty:
            yield 'data: {"type":"error","message":"Request timed out"}\n\n'
            break

        if item[0] == "stage":
            yield f"data: {json.dumps({'type':'stage','index':item[1],'message':item[2]})}\n\n"
        elif item[0] == "result":
            yield f"data: {json.dumps({'type':'result','id':item[1],'data':item[2]})}\n\n"
            break
        elif item[0] == "error":
            yield f"data: {json.dumps({'type':'error','message':item[1]})}\n\n"
            break


# ══════════════════════════════════════════════════════════════
# AUTH MIDDLEWARE
# ══════════════════════════════════════════════════════════════

def _get_token_from_request() -> str | None:
    """Extract Bearer token from Authorization header or cookie."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    # Also accept token from query string (for SSE EventSource which can't set headers)
    return request.args.get("token") or request.cookies.get("aira_token")


def _current_user() -> dict | None:
    """
    Decode and validate the JWT from the request.
    Returns user dict or None if unauthenticated.
    """
    token = _get_token_from_request()
    if not token:
        return None

    payload = auth.decode_token(token)
    if not payload:
        return None

    # Check per-JTI blacklist (explicit logout)
    if auth.is_token_blacklisted(payload.get("jti", "")):
        return None

    # Check global per-user revocation timestamp
    if not auth.is_token_valid_for_user(payload):
        return None

    return auth.get_user_by_id(int(payload["sub"]))


def require_auth(f):
    """Decorator: return 401 if no valid JWT."""
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        user = _current_user()
        if not user:
            # For SSE endpoints, return SSE error
            if request.headers.get("Accept") == "text/event-stream":
                return _sse(iter(['data: {"type":"error","message":"Authentication required"}\n\n']))
            return _err("Authentication required. Please log in.", 401)
        return f(*args, user=user, **kwargs)
    return decorated


# ══════════════════════════════════════════════════════════════
# FRONTEND ROUTES
# ══════════════════════════════════════════════════════════════

@app.route("/")
def index():
    resp = app.make_response(render_template("index.html"))
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    return resp

@app.route("/login")
def login_page():
    resp = app.make_response(render_template("login.html"))
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    return resp


# ══════════════════════════════════════════════════════════════
# AUTH API
# ══════════════════════════════════════════════════════════════

@app.route("/api/auth/register", methods=["POST"])
def api_register():
    body     = request.get_json(force=True, silent=True) or {}
    username = (body.get("username") or "").strip()
    email    = (body.get("email") or "").strip()
    password = body.get("password") or ""

    if not username or not email or not password:
        return _err("username, email, and password are required.")

    result = auth.register_user(username, email, password)
    if not result["ok"]:
        return _err(result["error"])
    return _ok({"user_id": result["user_id"]})


@app.route("/api/auth/login", methods=["POST"])
def api_login():
    body     = request.get_json(force=True, silent=True) or {}
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""

    if not username or not password:
        return _err("username and password are required.")

    user = auth.authenticate_user(username, password)
    if not user:
        return _err("Invalid username or password.", 401)

    access_token  = auth.create_access_token(user["id"])
    refresh_token = auth.create_refresh_token(user["id"])

    return _ok({
        "access_token":  access_token,
        "refresh_token": refresh_token,
        "user": {
            "id":       user["id"],
            "username": user["username"],
            "email":    user["email"],
        },
    })


@app.route("/api/auth/refresh", methods=["POST"])
def api_refresh():
    """Exchange a refresh token for a new access token."""
    body  = request.get_json(force=True, silent=True) or {}
    token = body.get("refresh_token") or ""

    payload = auth.decode_token(token)
    if not payload or payload.get("type") != "refresh":
        return _err("Invalid or expired refresh token.", 401)

    if auth.is_token_blacklisted(payload.get("jti", "")):
        return _err("Refresh token has been revoked.", 401)

    if not auth.is_token_valid_for_user(payload):
        return _err("Token revoked. Please log in again.", 401)

    user_id      = int(payload["sub"])
    access_token = auth.create_access_token(user_id)
    return _ok({"access_token": access_token})


@app.route("/api/auth/logout", methods=["POST"])
@require_auth
def api_logout(user):
    """Blacklist the current access token and optionally the refresh token."""
    token = _get_token_from_request()
    if token:
        auth.blacklist_token(token, user["id"])

    body = request.get_json(force=True, silent=True) or {}
    refresh = body.get("refresh_token")
    if refresh:
        auth.blacklist_token(refresh, user["id"])

    return _ok({"logged_out": True})


@app.route("/api/auth/logout-all", methods=["POST"])
@require_auth
def api_logout_all(user):
    """Revoke ALL tokens for this user (logout from every device)."""
    auth.revoke_all_user_tokens(user["id"])
    return _ok({"revoked_all": True})


@app.route("/api/auth/me")
@require_auth
def api_me(user):
    return _ok({
        "user": {
            "id":         user["id"],
            "username":   user["username"],
            "email":      user["email"],
            "created_at": user["created_at"],
        }
    })


# ══════════════════════════════════════════════════════════════
# HEALTH / META
# ══════════════════════════════════════════════════════════════

@app.route("/api/health")
def health():
    return _ok({"status": "running"})

@app.route("/api/stages")
def get_stages():
    return _ok({"stages": STAGES})


# ══════════════════════════════════════════════════════════════
# RESEARCH — SSE streaming
# ══════════════════════════════════════════════════════════════

@app.route("/api/research/stream")
@require_auth
def research_stream(user):
    """
    SSE endpoint. Query params: q, mode (quick|normal|deep), token
    Streams: stage events → result event
    """
    query = request.args.get("q", "").strip()
    mode  = request.args.get("mode", "normal").strip()

    if not query:
        return _sse(iter(['data: {"type":"error","message":"No query provided"}\n\n']))
    if mode not in ("quick", "normal", "deep"):
        mode = "normal"

    q = queue.Queue()

    def _run():
        try:
            result = agent.run(query, mode=mode,
                               progress_callback=lambda i, m: q.put(("stage", i, m)))
            hid = db.save_history(query, mode, result, user_id=user["id"])
            q.put(("result", hid, result))
        except Exception as e:
            q.put(("error", str(e)))

    threading.Thread(target=_run, daemon=True).start()
    return _sse(_drain(q, timeout=120))


# ══════════════════════════════════════════════════════════════
# HISTORY
# ══════════════════════════════════════════════════════════════

@app.route("/api/history")
@require_auth
def get_history(user):
    limit = int(request.args.get("limit", 50))
    return _ok({"history": db.get_history(limit=limit, user_id=user["id"])})

@app.route("/api/history/<int:hid>")
@require_auth
def get_history_item(user, hid):
    item = db.get_history_item(hid, user_id=user["id"])
    if not item:
        return _err("Not found", 404)
    item["saved"]     = db.is_saved(hid, user_id=user["id"])
    item["followups"] = db.get_followups(hid)
    return _ok({"item": item})

@app.route("/api/history/<int:hid>", methods=["DELETE"])
@require_auth
def delete_history_item(user, hid):
    db.delete_history_item(hid, user_id=user["id"])
    return _ok({"deleted": hid})


# ══════════════════════════════════════════════════════════════
# SAVED RESEARCH
# ══════════════════════════════════════════════════════════════

@app.route("/api/saved")
@require_auth
def get_saved(user):
    return _ok({"saved": db.get_saved(user_id=user["id"])})

@app.route("/api/saved", methods=["POST"])
@require_auth
def save_item(user):
    body = request.get_json(force=True, silent=True) or {}
    hid  = body.get("history_id")
    if not hid:
        return _err("history_id required")
    db.save_research(hid, tag=body.get("tag", ""), user_id=user["id"])
    return _ok({"saved": True})

@app.route("/api/saved/<int:hid>", methods=["DELETE"])
@require_auth
def unsave_item(user, hid):
    db.unsave_research(hid, user_id=user["id"])
    return _ok({"unsaved": hid})


# ══════════════════════════════════════════════════════════════
# FOLLOW-UP — SSE streaming
# ══════════════════════════════════════════════════════════════

@app.route("/api/followup/stream")
@require_auth
def followup_stream(user):
    hid      = request.args.get("history_id", type=int)
    question = request.args.get("q", "").strip()
    mode     = request.args.get("mode", "quick")

    if not hid or not question:
        return _sse(iter(['data: {"type":"error","message":"history_id and q required"}\n\n']))

    parent = db.get_history_item(hid, user_id=user["id"])
    if not parent:
        return _sse(iter(['data: {"type":"error","message":"History item not found"}\n\n']))

    q = queue.Queue()

    def _run():
        try:
            passages   = parent.get("result", {}).get("passages", [])
            ctx        = " ".join(p.get("passage", "") for p in passages[:3])
            enhanced_q = f"{question} (Context: {ctx[:500]})" if ctx else question

            result = agent.run(enhanced_q, mode=mode,
                               progress_callback=lambda i, m: q.put(("stage", i, m)))
            result["original_question"] = question
            fid = db.save_followup(hid, question, result)
            q.put(("result", fid, result))
        except Exception as e:
            q.put(("error", str(e)))

    threading.Thread(target=_run, daemon=True).start()
    return _sse(_drain(q, timeout=120))


# ══════════════════════════════════════════════════════════════
# COMPARE — SSE streaming
# ══════════════════════════════════════════════════════════════

@app.route("/api/compare/stream")
@require_auth
def compare_stream(user):
    topic_a = request.args.get("a", "").strip()
    topic_b = request.args.get("b", "").strip()
    mode    = request.args.get("mode", "normal")

    if not topic_a or not topic_b:
        return _sse(iter(['data: {"type":"error","message":"Both topics required"}\n\n']))

    q = queue.Queue()

    def _run():
        try:
            q.put(("stage", 0, f"Researching: {topic_a}..."))
            res_a = agent.run(topic_a, mode=mode)

            q.put(("stage", 2, f"Researching: {topic_b}..."))
            res_b = agent.run(topic_b, mode=mode)

            comparison = {"topic_a": topic_a, "topic_b": topic_b,
                          "result_a": res_a, "result_b": res_b}
            cid = db.save_comparison(topic_a, topic_b, comparison, user_id=user["id"])
            q.put(("stage", 6, "Comparison complete."))
            q.put(("result", cid, comparison))
        except Exception as e:
            q.put(("error", str(e)))

    threading.Thread(target=_run, daemon=True).start()
    return _sse(_drain(q, timeout=300))

@app.route("/api/comparisons")
@require_auth
def get_comparisons(user):
    return _ok({"comparisons": db.get_comparisons(user_id=user["id"])})

@app.route("/api/comparisons/<int:cid>")
@require_auth
def get_comparison(user, cid):
    item = db.get_comparison(cid, user_id=user["id"])
    if not item:
        return _err("Not found", 404)
    return _ok({"comparison": item})


# ══════════════════════════════════════════════════════════════
# EXPORT  (PDF fixed — unicode-safe)
# ══════════════════════════════════════════════════════════════

@app.route("/api/export/markdown/<int:hid>")
@require_auth
def export_md(user, hid):
    item = db.get_history_item(hid, user_id=user["id"])
    if not item:
        return _err("Not found", 404)
    md = export_markdown(item["result"], followups=db.get_followups(hid))
    return Response(md, mimetype="text/markdown",
                    headers={"Content-Disposition": f'attachment; filename="aira_research_{hid}.md"'})

@app.route("/api/export/pdf/<int:hid>")
@require_auth
def export_pdf_route(user, hid):
    item = db.get_history_item(hid, user_id=user["id"])
    if not item:
        return _err("Not found", 404)
    try:
        pdf_bytes = export_pdf(item["result"], followups=db.get_followups(hid))
    except ImportError as e:
        return _err(str(e))
    except Exception as e:
        return _err(f"PDF generation failed: {str(e)}")
    return Response(pdf_bytes, mimetype="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="aira_research_{hid}.pdf"'})


@app.route("/api/history/export-zip")
@require_auth
def export_history_zip(user):
    import io
    import re
    import zipfile
    from datetime import datetime

    items = db.get_all_history_for_export(user_id=user["id"])
    if not items:
        return _err("No research history records found to export.", 404)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        index_lines = [
            f"# AIRA AI Research Archive",
            f"**User:** {user['username']} ({user['email']})  ",
            f"**Exported:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}  ",
            f"**Total Research Sessions:** {len(items)}\n",
            "---",
            "",
            "## Table of Contents",
            "",
            "| # | Date | Query | Mode | Sources | Report File |",
            "|---|------|-------|------|---------|-------------|",
        ]

        for i, item in enumerate(items, 1):
            hid = item["id"]
            query = item.get("query", f"Research {hid}")
            mode = item.get("mode", "normal")
            created_at = item.get("created_at", "")[:19].replace("T", " ")
            res_data = item.get("result", {})
            sources_count = res_data.get("total_sources", len(res_data.get("sources", [])))

            clean_q = re.sub(r'[\\/*?:"<>|]', "", query).strip()
            clean_q = re.sub(r'\s+', "_", clean_q)[:45] or f"session_{hid}"
            filename = f"reports/{i:03d}_{clean_q}.md"

            followups = db.get_followups(hid)
            md_content = export_markdown(res_data, followups=followups)
            zf.writestr(filename, md_content.encode("utf-8"))

            index_lines.append(f"| {i} | {created_at} | {query} | {mode.capitalize()} | {sources_count} | [{filename}]({filename}) |")

        index_lines.append("")
        index_lines.append("---")
        index_lines.append("_Generated by AIRA AI Research Assistant_")
        zf.writestr("README.md", "\n".join(index_lines).encode("utf-8"))

    buf.seek(0)
    safe_uname = re.sub(r'\W+', '_', user['username'])
    return Response(
        buf.getvalue(),
        mimetype="application/zip",
        headers={"Content-Disposition": f'attachment; filename="aira_research_history_{safe_uname}.zip"'}
    )


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
