#!/usr/bin/env bash
# Usage: ./scripts/loadtest.sh <sid>      (needs `hey`; run in its own terminal)
hey -z 3m -c 50 "http://usermgmt-${1:?sid}.local/users"
