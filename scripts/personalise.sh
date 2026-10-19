#!/usr/bin/env bash
# Usage: ./scripts/personalise.sh <your-student-id>
set -euo pipefail
SID="${1:?usage: personalise.sh <student-id>}"
sed -i "s/STUDENTID/${SID}/g" k8s/*.yaml
echo "Namespace: usermgmt-${SID}   Host: usermgmt-${SID}.local"
