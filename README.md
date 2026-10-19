# User Management API on Kubernetes

Student ID **02230159** · namespace `usermgmt-02230159` · host `http://usermgmt-02230159.local`

Flask + PostgreSQL user service on minikube, with a small web dashboard at `/`: PostgreSQL as a StatefulSet with a headless Service
and a 1 Gi PVC, the API as a Deployment (2 replicas) behind a ClusterIP Service, an Ingress
(Ingress NGINX, class `nginx`), an HPA on the API (CPU 50 %, 2–6 replicas) and a VPA on the
database (`updateMode: "Off"`, recommend only).

```
app/       Flask source (app.py), requirements.txt, Dockerfile
k8s/       manifests, numbered in apply order (00 -> 09)
scripts/   bash helpers (Linux/macOS); on Windows use the PowerShell commands below
report/    hpa_timeline.csv recorded during the load test
```

**All commands below are for Windows PowerShell**, run from the repository folder.
Tested on Windows 11 Home, 7.3 GB RAM, Docker Desktop (WSL 2 backend), minikube v1.39.0,
Kubernetes v1.37.0. Git for Windows must be installed (the VPA installer is a bash script and
is run through Git's `bash.exe`).

```powershell
cd C:\Users\wangm\usermgmt          # or wherever you cloned this repository
$NS = "usermgmt-02230159"           # set this in every new PowerShell window
```

## 1. Cluster and platform add-ons

```powershell
minikube start --driver=docker --cpus=2 --memory=3800 --container-runtime=docker
minikube addons enable metrics-server
minikube addons enable ingress
kubectl get nodes
kubectl get storageclass            # standard (default), provisioner k8s.io/minikube-hostpath
```

> **3800 MB, not 4096 MB:** on a 7.3 GB host, WSL 2 gives Docker Desktop only ~3.9 GB, so
> `--memory=4096` fails with `MK_USAGE: Docker Desktop has only 3973MB memory`.
> **`--container-runtime=docker`:** after a Docker Desktop restart the containerd runtime inside
> the first node did not come back (kubelet/apiserver `Stopped`); the Docker runtime avoids this.
> If an add-on shows `enabled` but has no Pod, run `minikube addons disable <name>` then
> `minikube addons enable <name>`.
>
> **Slow internet:** if a Pod stays in `ContainerCreating` or shows `ErrImagePull` /
> `context canceled`, download the image inside the node (no time limit) and delete the Pod:
> `minikube ssh -- docker pull <image>` then `kubectl delete pod <pod> -n <namespace>`.
> The image name is in `kubectl describe pod <pod> -n <namespace>` under Events.

## 2. Vertical Pod Autoscaler (official kubernetes/autoscaler repository)

```powershell
git clone --depth 1 https://github.com/kubernetes/autoscaler.git $HOME\autoscaler
git -C $HOME\autoscaler fetch --depth 1 origin tag vertical-pod-autoscaler-1.8.0
cd $HOME\autoscaler\vertical-pod-autoscaler
& "C:\Program Files\Git\bin\bash.exe" ./hack/vpa-up.sh
```

On Windows the certificate step inside `vpa-up.sh` fails (`Failed to create CA certificate`,
because Git Bash rewrites `/CN=...` into a Windows path). Regenerate the certificate with path
conversion disabled for `/CN` only, then restart the admission controller:

```powershell
& "C:\Program Files\Git\bin\bash.exe" -c "MSYS2_ARG_CONV_EXCL='/CN' bash ./pkg/admission-controller/gencerts.sh"
kubectl rollout restart deployment vpa-admission-controller -n kube-system
kubectl get pods -n kube-system | findstr vpa     # recommender, updater, admission-controller: 1/1 Running
cd C:\Users\wangm\usermgmt
```

## 3. Build the API image and load it into minikube

The Deployment (`k8s/05-api-deployment.yaml`) uses `usermgmt-api:1.1`, so build that tag.

```powershell
docker build -t usermgmt-api:1.1 .\app
minikube image load usermgmt-api:1.1
minikube image ls | Select-String usermgmt-api
```

## 4. Deploy (only after the VPA is installed, so 09-postgres-vpa.yaml is accepted)

```powershell
kubectl apply -f k8s\
kubectl rollout status statefulset/postgres -n $NS
kubectl rollout status deployment/api -n $NS
kubectl get all,pvc,ingress,hpa,vpa -n $NS
```

## 5. Persistence test (data survives deletion of postgres-0)

```powershell
"CREATE TABLE IF NOT EXISTS persistence_check (id SERIAL PRIMARY KEY, note TEXT);" | kubectl exec -i -n $NS postgres-0 -- sh -c 'psql -U $POSTGRES_USER -d $POSTGRES_DB'
"INSERT INTO persistence_check (note) VALUES ('survives pod deletion');" | kubectl exec -i -n $NS postgres-0 -- sh -c 'psql -U $POSTGRES_USER -d $POSTGRES_DB'
kubectl delete pod postgres-0 -n $NS
kubectl wait --for=condition=Ready pod/postgres-0 -n $NS --timeout=180s
"SELECT * FROM persistence_check;" | kubectl exec -i -n $NS postgres-0 -- sh -c 'psql -U $POSTGRES_USER -d $POSTGRES_DB'
```

## 6. CRUD test through port-forward

```powershell
# window 1 (leave running)
kubectl port-forward svc/api 8080:80 -n $NS
# window 2
curl.exe -i http://localhost:8080/healthz
curl.exe -i http://localhost:8080/ready
Invoke-RestMethod -Method Post -Uri http://localhost:8080/users -ContentType "application/json" -Body '{"name":"Tashi Dorji","email":"tashi@example.bt"}'
curl.exe -s http://localhost:8080/users
curl.exe -s http://localhost:8080/users/1
Invoke-RestMethod -Method Put -Uri http://localhost:8080/users/1 -ContentType "application/json" -Body '{"name":"Tashi D.","email":"tashi@example.bt"}'
(Invoke-WebRequest -Method Delete -Uri http://localhost:8080/users/1 -UseBasicParsing).StatusCode
```

Web dashboard (same port-forward): open http://localhost:8080/ in a browser to add, edit and
delete users.

## 7. Ingress

1. Notepad **as Administrator** → `C:\Windows\System32\drivers\etc\hosts` → add `127.0.0.1 usermgmt-02230159.local`.
2. In a separate **Administrator** PowerShell window run `minikube tunnel` and leave it open.

```powershell
kubectl describe ingress api-ingress -n $NS
curl.exe -i http://usermgmt-02230159.local/users                       # 200 + JSON
curl.exe -i -H "Host: other-host.local" http://127.0.0.1/users         # 404 from nginx
```

The dashboard is also at http://usermgmt-02230159.local/ while `minikube tunnel` is running.

## 8. Autoscaling (HPA load test + VPA recommendation)

```powershell
# window A: record the HPA every 30 s into report\hpa_timeline.csv
Set-Content -Path report\hpa_timeline.csv -Value "time_s,cpu_percent,current_replicas,desired_replicas" -Encoding ascii
$start = Get-Date
1..25 | ForEach-Object { $t = [int]((Get-Date) - $start).TotalSeconds; $cpu = kubectl get hpa api -n $NS -o jsonpath="{.status.currentMetrics[0].resource.current.averageUtilization}"; $cur = kubectl get hpa api -n $NS -o jsonpath="{.status.currentReplicas}"; $des = kubectl get hpa api -n $NS -o jsonpath="{.status.desiredReplicas}"; $line = "$t,$cpu,$cur,$des"; Add-Content -Path report\hpa_timeline.csv -Value $line; $line; Start-Sleep -Seconds 30 }

# window B: live view
kubectl get hpa -n $NS -w

# window C: 3 minutes of load through the Ingress controller (20 parallel wget loops)
kubectl run load-gen -n $NS --rm -it --image=busybox:1.36 --restart=Never -- /bin/sh -c 'for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do (while true; do wget -q -O /dev/null --header=Host:usermgmt-02230159.local http://ingress-nginx-controller.ingress-nginx.svc.cluster.local/users; done) & done; sleep 180; kill 0'

# afterwards
kubectl describe hpa api -n $NS          # Events show each scale-up and the scale-down
kubectl describe vpa postgres-vpa -n $NS # Lower Bound / Target / Upper Bound
```

## 9. Tear down

```powershell
kubectl delete namespace $NS      # also removes the PVC
# stop minikube tunnel (Ctrl + C in its Administrator window) before the next line
minikube delete
```
