"""Minimal user-management REST API (Flask + PostgreSQL)."""
import os

import psycopg2
import psycopg2.extras
from flask import Flask, jsonify, request

app = Flask(__name__)
_schema_ready = False


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
