"""Minimal user-management REST API (Flask + PostgreSQL) with a small web dashboard."""
import os

import psycopg2
import psycopg2.extras
from flask import Flask, Response, jsonify, request

app = Flask(__name__)
_schema_ready = False
POD_NAME = os.environ.get("HOSTNAME", "local")


@app.after_request
def add_pod_header(resp):
    # Shows which api Pod answered, so the dashboard can display load balancing.
    resp.headers["X-Pod-Name"] = POD_NAME
    return resp


def get_conn():
    # Non-secret settings come from a ConfigMap, user/password from a Secret.
    return psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=os.environ.get("DB_PORT", "5432"),
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        connect_timeout=3,
    )


def ensure_schema(conn):
    """Create the table once. An advisory lock stops 2 replicas racing."""
    global _schema_ready
    if _schema_ready:
        return
    with conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_lock(42)")
        cur.execute(
            """CREATE TABLE IF NOT EXISTS users (
                 id    SERIAL PRIMARY KEY,
                 name  TEXT NOT NULL,
                 email TEXT NOT NULL UNIQUE)"""
        )
        cur.execute("SELECT pg_advisory_unlock(42)")
    conn.commit()
    _schema_ready = True


def run(query, params=(), fetch="all"):
    conn = get_conn()
    try:
        ensure_schema(conn)
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, params)
            if fetch == "all":
                result = cur.fetchall()
            elif fetch == "one":
                result = cur.fetchone()
            else:
                result = cur.rowcount
        conn.commit()
        return result
    finally:
        conn.close()


def valid(body):
    return (isinstance(body, dict) and str(body.get("name", "")).strip()
            and str(body.get("email", "")).strip())


@app.get("/")                 # web dashboard (calls the REST endpoints below)
def dashboard():
    return Response(DASHBOARD_HTML, mimetype="text/html")


@app.get("/healthz")          # liveness: process is up, no DB check
def healthz():
    return jsonify(status="ok"), 200


@app.get("/ready")            # readiness: only 200 if DB is reachable
def ready():
    try:
        run("SELECT 1", fetch="one")
        return jsonify(status="ready"), 200
    except Exception as exc:  # noqa: BLE001
        return jsonify(status="db unavailable", error=str(exc)), 503


@app.get("/users")
def list_users():
    return jsonify(run("SELECT id, name, email FROM users ORDER BY id"))


@app.post("/users")
def create_user():
    body = request.get_json(silent=True)
    if not valid(body):
        return jsonify(error="name and email are required"), 400
    try:
        row = run("INSERT INTO users (name, email) VALUES (%s, %s) "
                  "RETURNING id, name, email",
                  (body["name"].strip(), body["email"].strip()), fetch="one")
    except psycopg2.errors.UniqueViolation:
        return jsonify(error="email already exists"), 409
    return jsonify(row), 201


@app.get("/users/<int:uid>")
def get_user(uid):
    row = run("SELECT id, name, email FROM users WHERE id = %s", (uid,), "one")
    return (jsonify(row), 200) if row else (jsonify(error="not found"), 404)


@app.put("/users/<int:uid>")
def update_user(uid):
    body = request.get_json(silent=True)
    if not valid(body):
        return jsonify(error="name and email are required"), 400
    try:
        row = run("UPDATE users SET name=%s, email=%s WHERE id=%s "
                  "RETURNING id, name, email",
                  (body["name"].strip(), body["email"].strip(), uid), "one")
    except psycopg2.errors.UniqueViolation:
        return jsonify(error="email already exists"), 409
    return (jsonify(row), 200) if row else (jsonify(error="not found"), 404)


@app.delete("/users/<int:uid>")
def delete_user(uid):
    count = run("DELETE FROM users WHERE id = %s", (uid,), "count")
    return ("", 204) if count else (jsonify(error="not found"), 404)


# --------------------------------------------------------------------------
# Dashboard page served at "/" (plain HTML + JavaScript, no extra packages)
# --------------------------------------------------------------------------
DASHBOARD_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>User Management</title>
<style>
  :root {
    --ink: #1e1b4b;
    --muted: #6b6a8f;
    --card: #ffffff;
    --line: #e7e5f7;
    --indigo: #4f46e5;
    --violet: #7c3aed;
    --pink: #db2777;
    --teal: #0d9488;
    --rose-bg: #fff1f2;
    --rose: #e11d48;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    font-family: "Segoe UI", system-ui, -apple-system, Roboto, Arial, sans-serif;
    color: var(--ink);
    background: linear-gradient(135deg, #e0f2fe 0%, #ede9fe 45%, #fce7f3 100%);
    min-height: 100vh;
  }
  header {
    background: linear-gradient(120deg, var(--indigo), var(--violet) 55%, var(--pink));
    color: #fff;
    padding: 34px 20px 86px;
  }
  .wrap { max-width: 1040px; margin: 0 auto; }
  header h1 { margin: 0; font-size: 28px; font-weight: 700; letter-spacing: .2px; }
  header p { margin: 6px 0 0; opacity: .88; font-size: 14px; }
  .chip {
    display: inline-block; margin-top: 14px; padding: 5px 12px; border-radius: 999px;
    background: rgba(255,255,255,.18); font-size: 12px; font-weight: 600;
  }
  .chip .dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; background: #fbbf24; }
  .chip.ok .dot { background: #34d399; }
  .chip.bad .dot { background: #f87171; }

  main { margin-top: -58px; padding: 0 20px 40px; }
  .stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 20px; }
  .stat {
    background: var(--card); border-radius: 16px; padding: 18px 20px;
    box-shadow: 0 10px 30px rgba(79,70,229,.12);
    border-top: 4px solid var(--c);
  }
  .stat .label { font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: .8px; font-weight: 600; }
  .stat .value { font-size: 26px; font-weight: 700; margin-top: 4px; color: var(--c); }

  .grid { display: grid; grid-template-columns: 340px 1fr; gap: 20px; align-items: start; }
  .card { background: var(--card); border-radius: 18px; padding: 22px; box-shadow: 0 10px 30px rgba(79,70,229,.12); }
  .card h2 { margin: 0 0 4px; font-size: 18px; }
  .card .sub { margin: 0 0 18px; color: var(--muted); font-size: 13px; }

  label { display: block; font-size: 13px; font-weight: 600; margin: 12px 0 6px; }
  input {
    width: 100%; padding: 11px 13px; font: inherit; font-size: 14px; color: var(--ink);
    border: 1.5px solid var(--line); border-radius: 10px; background: #faf9ff; outline: none;
    transition: border-color .15s, box-shadow .15s;
  }
  input:focus { border-color: var(--violet); box-shadow: 0 0 0 4px rgba(124,58,237,.14); background: #fff; }

  .btn {
    border: 0; border-radius: 10px; padding: 11px 16px; font: inherit; font-size: 14px; font-weight: 600;
    cursor: pointer; transition: transform .08s, box-shadow .15s, opacity .15s;
  }
  .btn:active { transform: translateY(1px); }
  .btn-primary {
    width: 100%; margin-top: 18px; color: #fff;
    background: linear-gradient(120deg, var(--indigo), var(--violet));
    box-shadow: 0 8px 20px rgba(124,58,237,.30);
  }
  .btn-primary:hover { box-shadow: 0 10px 26px rgba(124,58,237,.42); }
  .btn-ghost { width: 100%; margin-top: 8px; background: #f3f2ff; color: var(--indigo); display: none; }
  .btn-edit { background: #ecfeff; color: var(--teal); padding: 7px 12px; font-size: 13px; }
  .btn-del  { background: var(--rose-bg); color: var(--rose); padding: 7px 12px; font-size: 13px; }
  .btn-edit:hover { background: #cffafe; }
  .btn-del:hover  { background: #ffe4e6; }

  .toolbar { display: flex; gap: 12px; align-items: center; justify-content: space-between; margin-bottom: 14px; flex-wrap: wrap; }
  .toolbar input { max-width: 260px; }

  ul.users { list-style: none; margin: 0; padding: 0; }
  ul.users li {
    display: flex; align-items: center; gap: 14px; padding: 12px 10px;
    border-bottom: 1px solid var(--line); border-radius: 10px; transition: background .15s;
  }
  ul.users li:hover { background: #faf8ff; }
  ul.users li:last-child { border-bottom: 0; }
  .avatar {
    flex: 0 0 42px; height: 42px; border-radius: 50%; color: #fff; font-weight: 700;
    display: grid; place-items: center; font-size: 15px;
  }
  .who { flex: 1; min-width: 0; }
  .who .name { font-weight: 600; }
  .who .email { color: var(--muted); font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .id { font-size: 12px; color: var(--violet); background: #f3f0ff; padding: 3px 8px; border-radius: 999px; font-weight: 600; }
  .actions { display: flex; gap: 6px; }

  .empty { text-align: center; padding: 40px 10px; color: var(--muted); }
  .empty .big { font-size: 40px; }

  #toast {
    position: fixed; right: 20px; bottom: 20px; padding: 12px 18px; border-radius: 12px;
    color: #fff; font-weight: 600; font-size: 14px; box-shadow: 0 12px 30px rgba(0,0,0,.18);
    transform: translateY(120px); opacity: 0; transition: all .25s;
  }
  #toast.show { transform: translateY(0); opacity: 1; }
  #toast.ok  { background: linear-gradient(120deg, #059669, var(--teal)); }
  #toast.err { background: linear-gradient(120deg, var(--rose), var(--pink)); }

  footer { text-align: center; color: var(--muted); font-size: 12px; margin-top: 26px; }

  @media (max-width: 800px) {
    .grid { grid-template-columns: minmax(0, 1fr); }
    .card { min-width: 0; }
    .stats { grid-template-columns: 1fr; }
    .toolbar input { max-width: none; }
  }
</style>
</head>
<body>
<header>
  <div class="wrap">
    <h1>User Management</h1>
    <p>Add, edit and remove users &middot; stored in PostgreSQL on Kubernetes</p>
    <span id="status" class="chip"><span class="dot"></span><span id="statusText">Checking database&hellip;</span></span>
  </div>
</header>

<main>
  <div class="wrap">
    <div class="stats">
      <div class="stat" style="--c: var(--indigo)"><div class="label">Total users</div><div class="value" id="total">0</div></div>
      <div class="stat" style="--c: var(--pink)"><div class="label">Served by Pod</div><div class="value" id="pod" style="font-size:15px;padding-top:8px">&ndash;</div></div>
      <div class="stat" style="--c: var(--teal)"><div class="label">Last added</div><div class="value" id="last" style="font-size:15px;padding-top:8px">&ndash;</div></div>
    </div>

    <div class="grid">
      <section class="card">
        <h2 id="formTitle">Add a new user</h2>
        <p class="sub" id="formSub">Enter a name and a unique email address.</p>
        <form id="form" autocomplete="off">
          <label for="name">Name</label>
          <input id="name" placeholder="e.g. Wangmo" maxlength="100" required>
          <label for="email">Email</label>
          <input id="email" type="email" placeholder="e.g. wangmo@cst.edu.bt" maxlength="150" required>
          <button class="btn btn-primary" id="submit" type="submit">+ Add user</button>
          <button class="btn btn-ghost" id="cancel" type="button">Cancel editing</button>
        </form>
      </section>

      <section class="card">
        <div class="toolbar">
          <div>
            <h2>All users</h2>
            <p class="sub" style="margin:0">Newest at the bottom</p>
          </div>
          <input id="search" placeholder="Search name or email&hellip;">
        </div>
        <ul class="users" id="list"></ul>
      </section>
    </div>

    <footer>ITM304 &middot; usermgmt-02230159 &middot; College of Science and Technology</footer>
  </div>
</main>

<div id="toast"></div>

<script>
  const palette = ["#4f46e5", "#7c3aed", "#db2777", "#0d9488", "#ea580c", "#0284c7", "#16a34a", "#c026d3"];
  let users = [];
  let editingId = null;
  const $ = (id) => document.getElementById(id);

  function toast(msg, ok = true) {
    const t = $("toast");
    t.textContent = msg;
    t.className = "show " + (ok ? "ok" : "err");
    clearTimeout(t._h);
    t._h = setTimeout(() => (t.className = ""), 2600);
  }

  function initials(name) {
    return name.trim().split(/\s+/).slice(0, 2).map((p) => p[0].toUpperCase()).join("");
  }

  function render() {
    const q = $("search").value.trim().toLowerCase();
    const list = $("list");
    list.replaceChildren();
    const shown = users.filter((u) => !q || u.name.toLowerCase().includes(q) || u.email.toLowerCase().includes(q));
    $("total").textContent = users.length;
    $("last").textContent = users.length ? users[users.length - 1].name : "–";

    if (!shown.length) {
      const li = document.createElement("li");
      li.className = "empty";
      li.style.display = "block";
      li.innerHTML = '<div class="big">\u{1F331}</div>';
      const p = document.createElement("div");
      p.textContent = users.length ? "No users match your search." : "No users yet – add the first one!";
      li.appendChild(p);
      list.appendChild(li);
      return;
    }
    for (const u of shown) {
      const li = document.createElement("li");
      const av = document.createElement("div");
      av.className = "avatar";
      av.style.background = palette[u.id % palette.length];
      av.textContent = initials(u.name);
      const who = document.createElement("div");
      who.className = "who";
      const n = document.createElement("div"); n.className = "name"; n.textContent = u.name;
      const e = document.createElement("div"); e.className = "email"; e.textContent = u.email;
      who.append(n, e);
      const id = document.createElement("span"); id.className = "id"; id.textContent = "#" + u.id;
      const actions = document.createElement("div"); actions.className = "actions";
      const ed = document.createElement("button"); ed.className = "btn btn-edit"; ed.textContent = "Edit";
      ed.onclick = () => startEdit(u);
      const del = document.createElement("button"); del.className = "btn btn-del"; del.textContent = "Delete";
      del.onclick = () => removeUser(u);
      actions.append(ed, del);
      li.append(av, who, id, actions);
      list.appendChild(li);
    }
  }

  async function load() {
    try {
      const r = await fetch("/users");
      users = await r.json();
      render();
    } catch {
      toast("Could not load users", false);
    }
  }

  async function checkStatus() {
    const chip = $("status");
    try {
      const r = await fetch("/ready");
      chip.className = "chip " + (r.ok ? "ok" : "bad");
      $("statusText").textContent = r.ok ? "Database connected" : "Database unavailable";
      const pod = r.headers.get("X-Pod-Name");
      if (pod) $("pod").textContent = pod;
    } catch {
      chip.className = "chip bad";
      $("statusText").textContent = "API unreachable";
    }
  }

  function startEdit(u) {
    editingId = u.id;
    $("name").value = u.name;
    $("email").value = u.email;
    $("formTitle").textContent = "Edit user #" + u.id;
    $("formSub").textContent = "Change the details and save.";
    $("submit").textContent = "Save changes";
    $("cancel").style.display = "block";
    $("name").focus();
  }

  function resetForm() {
    editingId = null;
    $("form").reset();
    $("formTitle").textContent = "Add a new user";
    $("formSub").textContent = "Enter a name and a unique email address.";
    $("submit").textContent = "+ Add user";
    $("cancel").style.display = "none";
  }

  async function removeUser(u) {
    if (!confirm("Delete " + u.name + "?")) return;
    const r = await fetch("/users/" + u.id, { method: "DELETE" });
    if (r.status === 204) { toast("Deleted " + u.name); if (editingId === u.id) resetForm(); load(); }
    else toast("Delete failed (HTTP " + r.status + ")", false);
  }

  $("form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const body = JSON.stringify({ name: $("name").value.trim(), email: $("email").value.trim() });
    const url = editingId ? "/users/" + editingId : "/users";
    const r = await fetch(url, { method: editingId ? "PUT" : "POST", headers: { "Content-Type": "application/json" }, body });
    if (r.ok) {
      toast(editingId ? "User updated" : "User added");
      resetForm();
      load();
    } else if (r.status === 409) {
      toast("That email is already used", false);
    } else {
      toast("Please enter a name and email (HTTP " + r.status + ")", false);
    }
  });

  $("cancel").onclick = resetForm;
  $("search").oninput = render;

  load();
  checkStatus();
  setInterval(checkStatus, 10000);
</script>
</body>
</html>
"""
