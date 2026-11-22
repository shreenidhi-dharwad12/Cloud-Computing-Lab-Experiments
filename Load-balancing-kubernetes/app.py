import json
import re
import subprocess
import time
from collections import Counter
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

NAMESPACE = "load-balancing"
DEPLOYMENT = "lb-demo"
SERVICE = "lb-demo-svc"
HTML_FILE = Path(__file__).with_name("dashboard.html")


def kubectl(*args, timeout=30):
    p = subprocess.run(["kubectl", *args], capture_output=True, text=True, timeout=timeout)
    if p.returncode:
        raise RuntimeError((p.stderr or p.stdout).strip() or "kubectl command failed")
    return p.stdout


def cluster_status():
    pods_doc = json.loads(kubectl("get", "pods", "-n", NAMESPACE, "-o", "json"))
    dep = json.loads(kubectl("get", "deployment", DEPLOYMENT, "-n", NAMESPACE, "-o", "json"))
    eps = json.loads(kubectl("get", "endpoints", SERVICE, "-n", NAMESPACE, "-o", "json"))
    pods = []
    for pod in pods_doc.get("items", []):
        if pod.get("metadata", {}).get("labels", {}).get("app") != "lb-demo":
            continue
        statuses = pod.get("status", {}).get("containerStatuses", [])
        pods.append({
            "name": pod["metadata"]["name"],
            "ip": pod.get("status", {}).get("podIP") or "Pending",
            "status": pod.get("status", {}).get("phase", "Unknown"),
            "ready": bool(statuses) and all(c.get("ready", False) for c in statuses),
            "node": pod.get("spec", {}).get("nodeName", "Pending"),
            "restarts": sum(c.get("restartCount", 0) for c in statuses),
        })
    endpoint_count = sum(len(s.get("addresses", [])) for s in eps.get("subsets", []))
    st = dep.get("status", {})
    return {"desired": dep.get("spec", {}).get("replicas", 0),
            "ready": st.get("readyReplicas", 0),
            "available": st.get("availableReplicas", 0),
            "readyEndpoints": endpoint_count, "pods": pods}


def run_real_test(count):
    if not isinstance(count, int) or count < 1 or count > 300:
        raise ValueError("Request count must be between 1 and 300")
    name = "lb-dashboard-test"
    # Remove only this dashboard's previous temporary test Pod.
    subprocess.run(["kubectl", "delete", "pod", name, "-n", NAMESPACE, "--ignore-not-found=true", "--wait=true"], capture_output=True, text=True, timeout=25)
    command = f"for i in $(seq 1 {count}); do curl -sS --max-time 5 http://{SERVICE}/ || echo REQUEST_FAILED; done"
    kubectl("run", name, "--restart=Never", "--image=curlimages/curl", "-n", NAMESPACE,
            "--command", "--", "sh", "-c", command, timeout=35)
    try:
        phase = ""
        for _ in range(90):
            raw = kubectl("get", "pod", name, "-n", NAMESPACE, "-o", "json", timeout=10)
            phase = json.loads(raw).get("status", {}).get("phase", "")
            if phase in ("Succeeded", "Failed"):
                break
            time.sleep(1)
        if phase != "Succeeded":
            logs = subprocess.run(["kubectl", "logs", name, "-n", NAMESPACE], capture_output=True, text=True, timeout=15).stdout
            raise RuntimeError("In-cluster request test did not complete. " + logs[-1000:])
        output = kubectl("logs", name, "-n", NAMESPACE, timeout=20)
        hosts = re.findall(r"Hostname:\s*([^\s]+)", output)
        counts = dict(Counter(hosts))
        failed = max(0, count - len(hosts))
        return {"requested": count, "successful": len(hosts), "failed": failed, "counts": counts}
    finally:
        subprocess.run(["kubectl", "delete", "pod", name, "-n", NAMESPACE, "--ignore-not-found=true", "--wait=false"], capture_output=True, text=True, timeout=15)


class Handler(BaseHTTPRequestHandler):
    def send_json(self, status, data):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_body(self):
        size = int(self.headers.get("Content-Length", "0"))
        if size > 4096:
            raise ValueError("Request too large")
        return json.loads(self.rfile.read(size) or b"{}")

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/dashboard.html"):
            try:
                body = HTML_FILE.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                self.send_json(500, {"error": str(e)})
        elif self.path == "/api/status":
            try:
                self.send_json(200, cluster_status())
            except Exception as e:
                self.send_json(500, {"error": str(e)})
        else:
            self.send_json(404, {"error": "Not found"})

    def do_POST(self):
        try:
            data = self.read_body()
            if self.path == "/api/test":
                self.send_json(200, run_real_test(data.get("count", 100)))
            elif self.path == "/api/scale":
                replicas = data.get("replicas")
                if type(replicas) is not int or not 1 <= replicas <= 10:
                    raise ValueError("Replicas must be between 1 and 10")
                kubectl("scale", "deployment", DEPLOYMENT, f"--replicas={replicas}", "-n", NAMESPACE)
                self.send_json(200, {"message": f"Scaling requested: {replicas} replicas"})
            elif self.path == "/api/delete-pod":
                pod_name = data.get("pod", "")
                if not isinstance(pod_name, str) or not re.fullmatch(r"lb-demo-[a-z0-9-]+", pod_name):
                    raise ValueError("Invalid application Pod name")
                doc = json.loads(kubectl("get", "pod", pod_name, "-n", NAMESPACE, "-o", "json"))
                if doc.get("metadata", {}).get("labels", {}).get("app") != "lb-demo":
                    raise ValueError("Selected Pod is not part of this application")
                kubectl("delete", "pod", pod_name, "-n", NAMESPACE, "--wait=false")
                self.send_json(200, {"message": f"Deleted {pod_name}. Kubernetes should create a replacement."})
            else:
                self.send_json(404, {"error": "Not found"})
        except Exception as e:
            self.send_json(400, {"error": str(e)})

    def log_message(self, fmt, *args):
        print(fmt % args)


if __name__ == "__main__":
    print("Kubernetes Load Balancing Dashboard")
    print("Open http://127.0.0.1:8000")
    print("Connected to current kubectl context; namespace: " + NAMESPACE)
    print("Press Ctrl+C to stop.")
    HTTPServer(("127.0.0.1", 8000), Handler).serve_forever()
