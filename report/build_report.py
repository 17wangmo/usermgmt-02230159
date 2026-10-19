#!/usr/bin/env python3
"""Build the PDF report.  Usage: python report/build_report.py <sid> "<Full Name>" [ingress=nginx]
Screenshots: put PNG/JPG files in report/screenshots/ using the names listed in SHOTS.
Missing screenshots are shown as placeholder boxes."""
import csv, glob, os, sys
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (Flowable, Image, KeepTogether, PageBreak, Paragraph,
                                Preformatted, SimpleDocTemplate, Spacer, Table, TableStyle)

SID = sys.argv[1] if len(sys.argv) > 1 else "<sid>"
NAME = sys.argv[2] if len(sys.argv) > 2 else "Student Name"
INGRESS = sys.argv[3] if len(sys.argv) > 3 else "nginx"
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
NS, HOST = f"usermgmt-{SID}", f"usermgmt-{SID}.local"

ss = getSampleStyleSheet()
B = ParagraphStyle("B", parent=ss["BodyText"], fontSize=9.2, leading=12.2, spaceAfter=4)
H1 = ParagraphStyle("H1", parent=ss["Heading1"], fontSize=13, spaceBefore=8, spaceAfter=4,
                    textColor=colors.HexColor("#1F3A5F"))
H2 = ParagraphStyle("H2", parent=ss["Heading2"], fontSize=10.5, spaceBefore=5, spaceAfter=3)
CAP = ParagraphStyle("CAP", parent=B, fontSize=7.8, leading=9.5, textColor=colors.grey)
CODE = ParagraphStyle("CODE", fontName="Courier", fontSize=7, leading=8.4)
TITLE = ParagraphStyle("T", parent=ss["Title"], fontSize=17, spaceAfter=2)


def P(t, s=B):
    return Paragraph(t.replace("@SID@", SID), s)


class Arch(Flowable):
    W, Hh = 16.6 * cm, 7.6 * cm

    def wrap(self, aw, ah):
        return self.W, self.Hh

    def draw(self):
        c = self.canv
        c.saveState()
        sc = self.W / 470.0
        c.scale(sc, sc)

        def box(x, y, w, h, lines, fill="#E8F0FE", dash=False):
            c.setFillColor(colors.HexColor(fill)); c.setStrokeColor(colors.HexColor("#1F3A5F"))
            c.setDash(3, 2) if dash else c.setDash()
            c.roundRect(x, y, w, h, 4, fill=1, stroke=1); c.setFillColor(colors.black)
            c.setFont("Helvetica", 6.8)
            ty = y + h / 2 + (len(lines) - 1) * 4 - 2.5
            for ln in lines:
                c.drawCentredString(x + w / 2, ty, ln); ty -= 8.2

        def arrow(x1, y1, x2, y2, dash=False):
            c.setStrokeColor(colors.HexColor("#333333")); c.setFillColor(colors.HexColor("#333333"))
            c.setDash(2, 2) if dash else c.setDash()
            c.line(x1, y1, x2, y2)
            import math
            a = math.atan2(y2 - y1, x2 - x1)
            p = c.beginPath(); p.moveTo(x2, y2)
            p.lineTo(x2 - 5 * math.cos(a - .4), y2 - 5 * math.sin(a - .4))
            p.lineTo(x2 - 5 * math.cos(a + .4), y2 - 5 * math.sin(a + .4)); p.close()
            c.setDash(); c.drawPath(p, fill=1, stroke=0)

        # namespace boundary
        c.setStrokeColor(colors.HexColor("#888888")); c.setDash(4, 3)
        c.roundRect(205, 4, 262, 222, 6, fill=0, stroke=1); c.setDash()
        c.setFont("Helvetica-Bold", 7); c.setFillColor(colors.HexColor("#444444"))
        c.drawString(211, 214, f"namespace {NS}")
        # outside namespace
        box(0, 165, 80, 45, ["Client", HOST, "(hosts file)"], "#FFF4D6")
        box(95, 165, 95, 45, ["Ingress controller", f"({INGRESS}, ingress ns)"], "#FDE2E2")
        box(0, 20, 190, 60, ["kube-system", "metrics-server", "VPA: recommender, updater,", "admission-controller"], "#EEEEEE", True)
        # inside namespace
        box(215, 165, 70, 45, ["Ingress", "api-ingress", f"host rule"], "#E8F0FE")
        box(300, 165, 70, 45, ["Service api", "ClusterIP :80", "-> :8080"], "#E3F5E1")
        box(385, 165, 75, 45, ["Deployment api", "2-6 Pods", "HPA 50% CPU"], "#E3F5E1")
        box(215, 95, 70, 45, ["ConfigMap", "api-config", "(DB_HOST...)"], "#F3E8FF")
        box(300, 95, 70, 45, ["Secret", "postgres-secret", "(user/password)"], "#F3E8FF")
        box(385, 95, 75, 45, ["Service postgres", "headless", "clusterIP: None"], "#E3F5E1")
        box(385, 22, 75, 55, ["StatefulSet", "postgres-0", "VPA (Off)"], "#FFF4D6")
        box(300, 22, 70, 55, ["PVC", "data-postgres-0", "1Gi -> PV", "StorageClass standard"], "#FFF4D6")
        arrow(80, 187, 95, 187); arrow(190, 187, 215, 187); arrow(285, 187, 300, 187)
        arrow(370, 187, 385, 187); arrow(422, 165, 422, 140); arrow(422, 95, 422, 77)
        arrow(385, 50, 370, 50); arrow(250, 140, 250, 160, True)
        arrow(335, 140, 385, 172, True)
        arrow(95, 80, 230, 100, True)
        c.restoreState()


SHOTS = {}


def shot(key, caption, cmd):
    """Insert a screenshot if present, otherwise a placeholder box with the command to capture."""
    files = glob.glob(os.path.join(HERE, "screenshots", key + ".*"))
    if files:
        from reportlab.lib.utils import ImageReader
        iw, ih = ImageReader(files[0]).getSize()
        w = min(15.5 * cm, iw); h = w * ih / iw
        if h > 6.2 * cm:
            h = 6.2 * cm; w = h * iw / ih
        el = Image(files[0], width=w, height=h)
    else:
        t = Table([[P(f"<b>[Insert screenshot: {key}]</b><br/>Command: <font face='Courier'>{cmd}</font>", CAP)]],
                  colWidths=[16.4 * cm], rowHeights=[1.3 * cm])
        t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), .6, colors.red), ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FFF5F5")),
                               ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        el = t
    return KeepTogether([el, P(caption, CAP), Spacer(1, 3)])


def tbl(rows, widths, head=True):
    t = Table([[P(str(c), CAP if False else ParagraphStyle("c", parent=B, fontSize=8.2, leading=10, spaceAfter=0)) for c in r] for r in rows],
              colWidths=widths, repeatRows=1 if head else 0)
    st = [("GRID", (0, 0), (-1, -1), .4, colors.grey), ("VALIGN", (0, 0), (-1, -1), "TOP")]
    if head:
        st.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DCE6F5")))
    t.setStyle(TableStyle(st)); return t


class Doc(SimpleDocTemplate):
    appendix_page = None

    def afterFlowable(self, f):
        if getattr(f, "_appx", False):
            self.appendix_page = self.page


def footer(c, d):
    c.saveState(); c.setFont("Helvetica", 7.5); c.setFillColor(colors.grey)
    c.drawString(2 * cm, 1.1 * cm, f"{NAME} - {SID} - Kubernetes User Management Assignment")
    c.drawRightString(A4[0] - 2 * cm, 1.1 * cm, f"Page {d.page}"); c.restoreState()


s = []
s += [P("Deploying a Scalable User Management Application on Kubernetes", TITLE),
      P(f"Practical Assignment Report &nbsp;|&nbsp; <b>{NAME}</b> &nbsp;|&nbsp; Student ID: <b>{SID}</b><br/>"
        f"Namespace: <font face='Courier'>{NS}</font> &nbsp;|&nbsp; Host: <font face='Courier'>{HOST}</font> &nbsp;|&nbsp; "
        "College of Science and Technology, Royal University of Bhutan", CAP)]

# ---------------- Architecture
s += [P("1. Architecture and design choices", H1), Arch(),
      P("<i>Figure 1 - Deployed architecture. Solid arrows are request/data paths; dashed arrows are configuration or "
        "monitoring relationships.</i>", CAP),
      tbl([["Choice", "Decision and reason"],
           ["Cluster", "minikube (docker driver), 2 CPUs, 4 GB; add-ons: metrics-server and ingress."],
           ["Ingress controller", f"<b>{'Ingress NGINX (ingressClassName: nginx)' if INGRESS=='nginx' else 'Traefik (ingressClassName: traefik)'}</b> "
            "- enabled with the minikube add-on. Only one controller can run at a time."],
           ["Database", "PostgreSQL 16 as a 1-replica StatefulSet, headless Service <font face='Courier'>postgres</font>, 1 Gi PVC via volumeClaimTemplates."],
           ["Application", "Python Flask API served by gunicorn, image <font face='Courier'>usermgmt-api:1.0</font> (versioned tag), loaded with <font face='Courier'>minikube image load</font>."],
           ["Configuration", "Non-secret settings (host, port, DB name) in ConfigMap <font face='Courier'>api-config</font>; user and password only from Secret <font face='Courier'>postgres-secret</font>."],
           ["Autoscaling", "HPA on the stateless api (2-6 replicas, 50% CPU); VPA in recommendation-only mode on the postgres StatefulSet."]],
          [3.3 * cm, 13.1 * cm])]

# ---------------- M1
s += [P("2. Milestone 1 - Cluster and platform set-up", H1),
      P("I started minikube with <font face='Courier'>minikube start --driver=docker --cpus=2 --memory=4096</font>, enabled the "
        "<i>metrics-server</i> and <i>ingress</i> add-ons, and installed the VPA components by running "
        "<font face='Courier'>./hack/vpa-up.sh</font> from the kubernetes/autoscaler repository. The namespace was created from "
        "<font face='Courier'>k8s/00-namespace.yaml</font>. The default StorageClass is <b>standard</b> and its provisioner is "
        "<b>k8s.io/minikube-hostpath</b> (verify against your own output below)."),
      shot("m1_nodes", "kubectl get nodes", "kubectl get nodes"),
      shot("m1_pods", "Ingress controller, metrics-server and the three VPA components Running", "kubectl get pods -A"),
      shot("m1_storageclass", "Default StorageClass and provisioner", "kubectl get storageclass"),
      shot("m1_top_nodes", "metrics-server returning node values", "kubectl top nodes")]

# ---------------- M2
s += [P("3. Milestone 2 - Stateful database", H1),
      P("The Secret <font face='Courier'>postgres-secret</font> holds <i>POSTGRES_DB</i>, <i>POSTGRES_USER</i> and <i>POSTGRES_PASSWORD</i>; the "
        "StatefulSet reads each through <font face='Courier'>secretKeyRef</font>, so no credential appears in the StatefulSet manifest. "
        "The headless Service (<font face='Courier'>clusterIP: None</font>) gives the Pod a stable DNS identity, and "
        "<font face='Courier'>volumeClaimTemplates</font> created PVC <font face='Courier'>data-postgres-0</font> (1 Gi) from the default "
        "StorageClass. Requests (100m CPU / 256Mi) and limits (500m / 512Mi) are set."),
      shot("m2_resources", "StatefulSet, Pod, PVC and PV (PVC Bound)", f"kubectl get statefulset,pod,pvc,pv -n {NS}"),
      shot("m2_persistence", "Persistence test: rows before deletion, Pod deletion, rows after postgres-0 is recreated",
           "psql SELECT -> kubectl delete pod postgres-0 -> psql SELECT"),
      P("<b>Why a StatefulSet suits a database better than a Deployment.</b> A StatefulSet gives each Pod a stable name (postgres-0), "
        "stable DNS through the headless Service, ordered start-up and its own PVC per Pod, which is re-attached to the replacement Pod with the same name. "
        "A Deployment's Pods have random names and share one claim template; with one shared PVC all replicas would mount the same ReadWriteOnce volume, "
        "so extra replicas could not start or would corrupt data, and a rescheduled Pod has no stable identity for replication or clients."),
      P("<b>What happens to the PVC when the StatefulSet is deleted?</b> It is kept. Kubernetes deliberately does not delete PVCs "
        "created from volumeClaimTemplates (unless a persistentVolumeClaimRetentionPolicy says so) to protect data from accidental deletion; "
        "it must be deleted explicitly, or by deleting the namespace.")]

# ---------------- M3
s += [P("4. Milestone 3 - User management application", H1),
      P("A small Flask API implements <font face='Courier'>GET/POST /users</font>, <font face='Courier'>GET/PUT/DELETE /users/{id}</font>, "
        "<font face='Courier'>/healthz</font> (liveness, no DB check) and <font face='Courier'>/ready</font> (readiness, runs <i>SELECT 1</i> "
        "and returns 503 if the DB is unreachable). Email is UNIQUE, so a duplicate returns HTTP 409. The Deployment runs 2 replicas with "
        "image <font face='Courier'>usermgmt-api:1.0</font> and <font face='Courier'>imagePullPolicy: IfNotPresent</font>; settings come from "
        "<font face='Courier'>envFrom: configMapRef</font> and the DB user/password from the Secret. Requests are 100m CPU / 64Mi and limits 500m / 256Mi. "
        "The ClusterIP Service <font face='Courier'>api</font> maps port 80 to container port 8080."),
      shot("m3_resources", "Deployment, ReplicaSet, Pods and Services", f"kubectl get deploy,rs,pods,svc -n {NS}"),
      shot("m3_crud", "CRUD test through kubectl port-forward svc/api 8080:80", "kubectl port-forward svc/api 8080:80 -n " + NS + "  +  ./scripts/test-crud.sh"),
      P("<b>If postgres-0 restarts:</b> the /ready probe fails, the api Pods become NotReady and are removed from the Service endpoints "
        "(they are not restarted, because liveness does not depend on the DB). When the database is back, readiness passes and traffic resumes; "
        "the data persists on the PVC.")]

# ---------------- M4
s += [P("5. Milestone 4 - Ingress", H1),
      P(f"Ingress <font face='Courier'>api-ingress</font> uses <font face='Courier'>ingressClassName: {INGRESS}</font>, host "
        f"<font face='Courier'>{HOST}</font>, path <font face='Courier'>/</font> (Prefix), backend Service <font face='Courier'>api</font> port 80. "
        "The host name was added to the hosts file (Linux: <font face='Courier'>minikube ip</font>; Windows/macOS Docker Desktop: 127.0.0.1 with "
        "<font face='Courier'>minikube tunnel</font> running)."),
      shot("m4_describe", "Ingress description (rules and backends)", f"kubectl describe ingress -n {NS}"),
      shot("m4_hosts", "Hosts file entry", "cat /etc/hosts | grep usermgmt"),
      shot("m4_curl", "Request by host name returns data", f"curl http://{HOST}/users"),
      shot("m4_otherhost", "Request with a different host name does not reach the app (404 from the controller)",
           "curl -i -H 'Host: other.local' http://<ingress-address>/users"),
      P("<b>Request path.</b> The client resolves <i>" + HOST + "</i> through the hosts file to the cluster entry address and sends an HTTP request with "
        "<i>Host: " + HOST + "</i>. It reaches the <b>Ingress controller</b> Pods (the only component listening from outside). The controller watches "
        "Ingress objects and has built its routing table from them: the <b>Ingress rule</b> matching that host and path selects the backend "
        "Service <i>api:80</i>. The controller proxies to one of the Service's ready endpoints (the Pod IPs, chosen by the controller; "
        "kube-proxy handles ClusterIP traffic when the Service IP is used), reaching port 8080 of an <b>api Pod</b>. The Pod queries "
        "<i>postgres</i> through the headless Service and the response returns along the same path. An unknown host matches no rule, so the "
        "controller answers 404.")]

# ---------------- M5
s += [P("6. Milestone 5 - Autoscaling (metrics-server, HPA, VPA)", H1),
      P("<font face='Courier'>kubectl top pods</font> confirmed metrics for the namespace. The HPA (<i>autoscaling/v2</i>) targets the api Deployment: "
        "min 2, max 6, average CPU utilisation 50%, with a 120 s scale-down stabilisation window (default is 300 s) so the scale-down is visible within the lab. "
        f"Load was generated with <font face='Courier'>hey -z 3m -c 50 http://{HOST}/users</font>."),
      shot("m5_top_pods", "Pod metrics available", f"kubectl top pods -n {NS}")]
rows = [["Time (s)", "CPU % (avg)", "Current replicas", "Desired replicas", "Phase / note"]]
csvp = os.path.join(HERE, "hpa_timeline.csv")
if os.path.exists(csvp):
    with open(csvp) as fh:
        data = list(csv.DictReader(fh))
    for r in data:
        rows.append([r["time_s"], r["cpu_percent"], r["current_replicas"], r["desired_replicas"], ""])
else:
    rows += [[str(i * 30), "", "", "", ""] for i in range(0, 12)]
s += [P("<b>Replica timeline</b> (recorded every 30 s by <font face='Courier'>scripts/record-hpa.sh</font>; add a note where load starts, stops and where scale-up / scale-down occur):"),
      tbl(rows, [2.2 * cm, 2.6 * cm, 3.2 * cm, 3.2 * cm, 5.2 * cm]), Spacer(1, 4),
      shot("m5_hpa_watch", "HPA output during and after the load test", f"kubectl get hpa -n {NS} -w"),
      shot("m5_vpa", "VPA recommendation: target, lower bound, upper bound", f"kubectl describe vpa postgres-vpa -n {NS}"),
      P("<b>Why is the VPA attached to the database and not to the api Deployment?</b> The api is stateless, so it scales <i>horizontally</i>: the HPA "
        "adds replicas under load. The database is a single stateful replica that cannot simply be cloned by an HPA (extra replicas would need "
        "replication), so the practical way to size it is <i>vertically</i>. Each workload therefore has exactly one autoscaler and each autoscaler "
        "controls a different axis."),
      P("<b>Why is it in \"Off\" mode?</b> In Auto/Recreate mode the VPA updater applies new requests by <i>evicting</i> the Pod. With one "
        "database replica that means downtime and a restart at a moment chosen by the VPA. In Off mode the recommender only publishes "
        "target/lower/upper bounds; I review them after a representative load and change the StatefulSet requests myself in a planned change."),
      P("<b>HPA and VPA conflict.</b> HPA utilisation = current CPU usage / CPU <i>request</i>. If a VPA also changed the api's CPU request, raising "
        "the request would lower the utilisation percentage and make the HPA remove replicas, while less capacity would push usage up again and the "
        "VPA would raise requests further: the two controllers react to each other's output and oscillate. My design avoids this by never "
        "letting both act on the same resource of the same workload: HPA (CPU) on api, VPA (Off) on postgres only."),
      P("<b>Why does the HPA need CPU requests?</b> Without a request there is no denominator for the percentage, so the HPA shows "
        "<i>&lt;unknown&gt;</i> and cannot scale.")]

# ---------------- M6
ts = open(os.path.join(HERE, "troubleshooting.txt")).read().replace("<sid>", SID).split("\n")
sections, cur = {}, None
for ln in ts:
    if ln.startswith("@@"):
        cur = ln[2:].strip(); sections[cur] = []
    elif cur:
        sections[cur].append(ln)
s += [P("7. Milestone 6 - Troubleshooting account", H1)]
for k, v in sections.items():
    s.append(P(f"<b>{k}</b>", H2))
    txt = "\n".join(v).strip()
    if k.lower().startswith("diagnosis"):
        s.append(Preformatted(txt, CODE))
    else:
        s.append(P(txt.replace("\n", "<br/>").replace("&", "&amp;")))
s += [P("8. Demonstration notes", H1),
      P("<b>Where does traffic enter and which object chooses the Service?</b> Traffic enters through the Ingress controller; the <i>Ingress</i> "
        "resource (host + path rules) decides which Service receives it.")]

# ---------------- Appendix
class Appx(Paragraph):
    _appx = True


s += [PageBreak(), Appx("Appendix - Source files", H1)]
files = ["app/Dockerfile", "app/app.py"] + sorted(os.path.relpath(f, ROOT) for f in glob.glob(os.path.join(ROOT, "k8s", "*.yaml")))
for f in files:
    s.append(P(f"<b>{f}</b>", H2))
    s.append(Preformatted(open(os.path.join(ROOT, f)).read().replace("STUDENTID", SID).rstrip(), CODE))
    s.append(Spacer(1, 4))

out = os.path.join(HERE, f"Report_{SID.replace('<','').replace('>','')}.pdf")
doc = Doc(out, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.6 * cm, bottomMargin=1.8 * cm,
          title="Kubernetes User Management - Report", author=NAME)
doc.build(s, onFirstPage=footer, onLaterPages=footer)
print("Wrote", out, "| body pages:", (doc.appendix_page - 1) if doc.appendix_page else "?",
      "(limit 8 excluding appendix; real screenshots add pages)")
