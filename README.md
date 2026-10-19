# User Management API on Kubernetes

Flask + PostgreSQL user service on minikube: StatefulSet DB, Deployment API,
Ingress, HPA (api) and VPA (postgres, recommend-only).

```
app/       Flask source, requirements.txt, Dockerfile
k8s/       manifests, numbered in apply order (STUDENTID is a placeholder)
scripts/   personalise / test / load / record helpers
report/    report generator
```

## Deploy from scratch
Windows: run these in WSL 2 or Git Bash. Replace `<sid>` with your student ID.

```bash
# 0. personalise manifests (once) and set the DB password in k8s/01-postgres-secret.yaml
./scripts/personalise.sh <sid>
export NS=usermgmt-<sid>

# 1. cluster + add-ons
minikube start --driver=docker --cpus=2 --memory=4096
minikube addons enable metrics-server
minikube addons enable ingress            # ingress-nginx (ingressClassName: nginx)
git clone https://github.com/kubernetes/autoscaler.git /tmp/autoscaler
(cd /tmp/autoscaler/vertical-pod-autoscaler && ./hack/vpa-up.sh)
kubectl get pods -n kube-system | grep -E "vpa|metrics"

# 2. image
docker build -t usermgmt-api:1.0 ./app
minikube image load usermgmt-api:1.0

# 3. apply manifests in order
kubectl apply -f k8s/00-namespace.yaml
kubectl apply -f k8s/01-postgres-secret.yaml -f k8s/02-postgres-service.yaml
kubectl apply -f k8s/03-postgres-statefulset.yaml
kubectl rollout status statefulset/postgres -n $NS
kubectl apply -f k8s/04-api-configmap.yaml -f k8s/05-api-deployment.yaml -f k8s/06-api-service.yaml
kubectl rollout status deployment/api -n $NS
kubectl apply -f k8s/07-ingress.yaml -f k8s/08-api-hpa.yaml -f k8s/09-postgres-vpa.yaml

# 4. hosts file entry
#   Linux:           echo "$(minikube ip) usermgmt-<sid>.local" | sudo tee -a /etc/hosts
#   Windows / macOS: add "127.0.0.1 usermgmt-<sid>.local" to the hosts file
#                    and keep `minikube tunnel` running in a separate terminal

# 5. test
curl http://usermgmt-<sid>.local/users
./scripts/test-crud.sh http://usermgmt-<sid>.local
```

## Persistence test
```bash
kubectl exec -n $NS postgres-0 -- sh -c 'psql -U $POSTGRES_USER -d $POSTGRES_DB -c "SELECT * FROM users;"'
kubectl delete pod postgres-0 -n $NS
kubectl wait --for=condition=Ready pod/postgres-0 -n $NS --timeout=120s
kubectl exec -n $NS postgres-0 -- sh -c 'psql -U $POSTGRES_USER -d $POSTGRES_DB -c "SELECT * FROM users;"'
```

## Autoscaling test
```bash
kubectl top pods -n $NS
./scripts/record-hpa.sh $NS 12 &        # terminal 1 (or: kubectl get hpa -n $NS -w)
./scripts/loadtest.sh <sid>             # terminal 2 (3 minutes of load)
kubectl describe vpa postgres-vpa -n $NS
```

## Tear down
```bash
kubectl delete namespace $NS      # also removes the PVC
minikube delete
```
