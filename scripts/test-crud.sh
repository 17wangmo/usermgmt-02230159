#!/usr/bin/env bash
# Usage: ./scripts/test-crud.sh http://localhost:8080   (or http://usermgmt-<sid>.local)
BASE="${1:-http://localhost:8080}"
show() { echo; echo "\$ $*"; }
show "GET /healthz";  curl -s -i "$BASE/healthz" | head -1
show "GET /ready";    curl -s -i "$BASE/ready"   | head -1
show "POST /users";   curl -s -X POST "$BASE/users" -H 'Content-Type: application/json' \
                        -d '{"name":"Tashi Dorji","email":"tashi@example.bt"}'
show "POST duplicate email (expect 409)"
curl -s -o /dev/null -w "HTTP %{http_code}\n" -X POST "$BASE/users" \
  -H 'Content-Type: application/json' -d '{"name":"Dup","email":"tashi@example.bt"}'
show "GET /users";    curl -s "$BASE/users"
show "GET /users/1";  curl -s "$BASE/users/1"
show "PUT /users/1";  curl -s -X PUT "$BASE/users/1" -H 'Content-Type: application/json' \
                        -d '{"name":"Tashi D.","email":"tashi@example.bt"}'
show "DELETE /users/1"; curl -s -o /dev/null -w "HTTP %{http_code}\n" -X DELETE "$BASE/users/1"
show "GET /users/1 (expect 404)"; curl -s -o /dev/null -w "HTTP %{http_code}\n" "$BASE/users/1"
echo
