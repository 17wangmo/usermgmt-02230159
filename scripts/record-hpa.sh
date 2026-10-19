#!/usr/bin/env bash
# Records HPA state every 30 s into report/hpa_timeline.csv
# Usage: ./scripts/record-hpa.sh <namespace> [minutes=12]
NS="${1:?namespace}"; MIN="${2:-12}"
OUT=report/hpa_timeline.csv
echo "time_s,cpu_percent,current_replicas,desired_replicas" > "$OUT"
START=$(date +%s)
for i in $(seq 0 $((MIN*2))); do
  T=$(( $(date +%s) - START ))
  CPU=$(kubectl get hpa api -n "$NS" -o jsonpath='{.status.currentMetrics[0].resource.current.averageUtilization}')
  CUR=$(kubectl get hpa api -n "$NS" -o jsonpath='{.status.currentReplicas}')
  DES=$(kubectl get hpa api -n "$NS" -o jsonpath='{.status.desiredReplicas}')
  echo "${T},${CPU:-n/a},${CUR},${DES}" | tee -a "$OUT"
  sleep 30
done
