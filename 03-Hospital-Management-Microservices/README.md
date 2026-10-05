# Hospital Management System using Microservices and Docker

## 1. Project Overview

This project implements a small **Hospital Management System** using a **microservices architecture**.

The application is divided into exactly three independent services:

* **Patient Service** – owns patient records.
* **Doctor Service** – owns doctor records.
* **Appointment Service** – owns appointment records and builds the full appointment view by calling the Patient and Doctor services.

Each service is containerized with its own **Dockerfile**, and the three containers are deployed with **Docker Compose** on a shared Docker bridge network.

---

## 2. Problem Statement

Build, deploy and analyze a containerized microservice application under varying workloads:

* Three independent microservices with REST APIs
* Containerization using Docker and deployment using Docker Compose
* Communication between services over the container network
* Workload testing at five concurrency levels (1, 2, 4, 8, 16)
* Measurement of response time, throughput, failed requests, CPU utilization and memory utilization
* Analysis of the measured results

---

## 3. Objectives

1. To implement a hospital management application using microservices.
2. To separate application functionality into independent services.
3. To containerize each service using Docker.
4. To enable communication between microservices using Docker service names.
5. To deploy the containers using Docker Compose.
6. To evaluate the system under different workload levels.
7. To measure response time, throughput, failures, CPU utilization and memory utilization for every service.

---

## 4. System Architecture

```text
                    Client
                      |
                      v
             Appointment Service
                  Port 5003
                  /       \
                 /         \
                v           v
       Patient Service   Doctor Service
          Port 5001         Port 5002
```

All three containers are attached to one user-defined bridge network:

```text
                 hospital-network (bridge)
       +-------------------+-------------------+
       |                   |                   |
 patient-service     doctor-service     appointment-service
```

Inside Docker Compose, the Appointment Service reaches the other two services through Docker's internal DNS, using their **service names**:

```text
PATIENT_SERVICE_URL = http://patient-service:5001
DOCTOR_SERVICE_URL  = http://doctor-service:5002
```

These URLs are passed as **environment variables** in `docker-compose.yml` (they are not hard-coded). When the services are run on their own outside Docker, the defaults `http://localhost:5001` and `http://localhost:5002` are used instead.

---

## 5. Microservices and REST APIs

| Service | Port | Endpoint | Description |
|---|---:|---|---|
| Patient | 5001 | `GET /health` | Liveness check |
| Patient | 5001 | `GET /patients` | List all patients |
| Patient | 5001 | `GET /patients/<id>` | One patient (404 if not found) |
| Doctor | 5002 | `GET /health` | Liveness check |
| Doctor | 5002 | `GET /doctors` | List all doctors |
| Doctor | 5002 | `GET /doctors/<id>` | One doctor (404 if not found) |
| Appointment | 5003 | `GET /health` | Liveness check |
| Appointment | 5003 | `GET /health/dependencies` | Checks that patient-service and doctor-service are reachable |
| Appointment | 5003 | `GET /appointments` | List all appointments |
| Appointment | 5003 | `GET /appointments/<id>` | **End-to-end request**: appointment + patient + doctor |

Example end-to-end response (`GET /appointments/1`):

```json
{
    "appointment": {"id": 1, "patient_id": 1, "doctor_id": 1,
                    "date": "2026-10-03", "time": "10:00 AM", "status": "Confirmed"},
    "patient":     {"id": 1, "name": "Rahul", "age": 25, "gender": "Male"},
    "doctor":      {"id": 1, "name": "Dr. Ashok Dharwad", "specialization": "Gastroenterologist"}
}
```

**Data storage:** each service loads its records from a JSON file in its own `data/` folder at start-up and keeps them in memory. Each service owns its own data, which is the microservice principle. A database is not required by the lab manual, so one was not added. This keeps the workload test focused on the services and the network rather than on a database.

### Error handling in the Appointment Service

Every call to the Patient or Doctor service has a **timeout (3 s)** and is wrapped in error handling:

| Situation | HTTP status returned to the client |
|---|---|
| Patient/Doctor container stopped or unreachable | `503 Service Unavailable` |
| Patient/Doctor service does not answer within 3 s | `504 Gateway Timeout` |
| Referenced patient/doctor record does not exist | `404 Not Found` |
| Any other bad response from Patient/Doctor | `502 Bad Gateway` |
| Appointment id does not exist | `404 Not Found` |

All errors are returned as JSON, for example `{"error": "patient-service is unavailable", "service": "patient-service"}`.

---

## 6. Technology Stack

| Technology | Purpose |
|---|---|
| Python 3.13 | Application development |
| Flask 3.1 | REST API development |
| Requests | Inter-service HTTP calls and the load generator |
| Docker | Containerization |
| Docker Compose | Multi-container deployment, network, health checks |
| Docker bridge network | Service-to-service communication |
| `docker stats` | CPU and memory monitoring |
| Matplotlib | Performance graphs |

All service dependencies are **pinned** (`Flask==3.1.3`, `Werkzeug==3.1.8`, `requests==2.34.2`) so the images can be rebuilt with exactly the same versions.

---

## 7. Project Structure

```text
03-Hospital-Management-Microservices/
│
├── patient-service/
│   ├── app.py
│   ├── data/patients.json
│   ├── Dockerfile
│   ├── .dockerignore
│   └── requirements.txt
│
├── doctor-service/
│   ├── app.py
│   ├── data/doctors.json
│   ├── Dockerfile
│   ├── .dockerignore
│   └── requirements.txt
│
├── appointment-service/
│   ├── app.py
│   ├── data/appointments.json
│   ├── Dockerfile
│   ├── .dockerignore
│   └── requirements.txt
│
├── docker-compose.yml          # 3 services, network, env vars, health checks
├── benchmark.py                # the ONE workload + monitoring script
├── generate_graphs.py          # graphs from results/workload_results.csv
├── generate_report.py          # results/RESULTS.md from the CSV files
├── requirements-benchmark.txt  # packages needed on the host for the scripts
│
├── results/                    # created by benchmark.py
│   ├── workload_results.csv    # final observation table (mean of repetitions)
│   ├── runs.csv                # every individual run
│   ├── resource_samples.csv    # every raw docker stats sample
│   ├── run_info.json           # settings + machine info
│   └── RESULTS.md              # generated tables + observations
│
├── graphs/                     # created by generate_graphs.py
│   ├── 01-response-time.png
│   ├── 02-throughput.png
│   ├── 03-cpu-utilization.png
│   ├── 04-memory-utilization.png
│   └── 05-resource-by-service.png
│
├── screenshots/
└── README.md
```

---

## 8. Containerization

Each microservice has its own Dockerfile (same structure, different port):

```dockerfile
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=5001
WORKDIR /app
COPY requirements.txt .
RUN ["pip", "install", "--no-cache-dir", "-r", "requirements.txt"]
COPY app.py .
COPY data/ ./data/
USER 10001
EXPOSE 5001
CMD ["python", "app.py"]
```

* `requirements.txt` is copied and installed **before** the code, so Docker reuses the dependency layer when only the code changes.
* The container runs as an **unprivileged user** (`USER 10001`), not as root.
* `.dockerignore` keeps `__pycache__` and similar files out of the image.

`docker-compose.yml` additionally provides:

* **Health checks:** each container calls its own `/health` endpoint. `docker compose ps` therefore shows `(healthy)` only when the API actually answers, not just when the process has started.
* **`depends_on: condition: service_healthy`:** the Appointment Service is started only after the Patient and Doctor services are healthy.
* **`stop_signal: SIGINT`:** Python running as PID 1 ignores the default SIGTERM, so `docker compose stop` would otherwise wait 10 s. With SIGINT a container stops in under a second.
* **`restart: unless-stopped`:** a crashed service restarts automatically, but one stopped on purpose stays stopped.

---

## 9. How to Run and Demonstrate

All commands are run from the `03-Hospital-Management-Microservices` folder.

> **PowerShell tip:** in Windows PowerShell, `curl` is an alias of `Invoke-WebRequest`, which shows the "Security Warning: Script Execution Risk" prompt. Use **`curl.exe`** instead to get the plain JSON response.

### Checkpoint 1 – Run and test each service independently (without Docker)

Open three terminals:

```powershell
cd patient-service;     pip install -r requirements.txt; python app.py
cd doctor-service;      pip install -r requirements.txt; python app.py
cd appointment-service; pip install -r requirements.txt; python app.py
```

Then test:

```powershell
curl.exe http://localhost:5001/patients/1
curl.exe http://localhost:5002/doctors/1
curl.exe http://localhost:5003/appointments
curl.exe http://localhost:5003/appointments/1
```

The Appointment Service works on its own: `/appointments` answers even if the other two services are not running. If they are not running, `/appointments/1` returns a clear `503` JSON error instead of crashing.

Stop the three services (Ctrl+C) before the next step, so the ports are free.

### Checkpoint 2 – Build images and deploy with Docker Compose

```powershell
docker compose build
docker images            # three images: ...-patient-service, ...-doctor-service, ...-appointment-service
docker compose up -d
docker compose ps        # all three containers "Up ... (healthy)"
```

### Checkpoint 3 – Inter-service communication

```powershell
docker network inspect hospital-network            # all three containers on one network
curl.exe http://localhost:5003/health/dependencies # appointment-service reaches both others by name
curl.exe http://localhost:5003/appointments/1      # end-to-end request through all 3 services
docker exec appointment-service python -c "import socket; print(socket.gethostbyname('patient-service'))"
```

Failure demonstration:

```powershell
docker compose stop patient-service
curl.exe -i http://localhost:5003/appointments/1    # 503 {"error": "patient-service is unavailable", ...}
docker compose start patient-service
curl.exe http://localhost:5003/appointments/1       # works again
```

### Checkpoint 4 – Workload test and monitoring

Install the host-side packages once:

```powershell
pip install -r requirements-benchmark.txt
```

With the stack running (`docker compose up -d`), run:

```powershell
python benchmark.py
```

This takes roughly **4–5 minutes**: 5 levels × 3 repetitions × at least 10 s, plus pauses between runs. Do not run other heavy programs while it runs.

### Checkpoint 5 – Graphs and report

```powershell
python generate_graphs.py
python generate_report.py
```

The flow is always:

```text
benchmark.py  ->  results/*.csv  ->  generate_graphs.py  ->  graphs/*.png
                                 ->  generate_report.py  ->  results/RESULTS.md
```

No result is typed in by hand. Re-running the three commands regenerates every table and graph from one consistent run.

---

## 10. Workload Testing Methodology

### What "concurrency level" means here

The levels **1, 2, 4, 8, 16** are the number of **client worker threads** in the load generator (`benchmark.py`).

* Each worker sends a request, waits for the full response, then immediately sends the next request. This is called a **closed-loop** load.
* So at concurrency level *N*, exactly *N* requests are in flight at any moment.
* It is *not* "N requests in total". Each run sends many requests, as described below.
* Each request opens a new HTTP connection, as independent clients would.

### Endpoint under test

`GET /appointments/1` was chosen because it is the **end-to-end** request. A single client request causes:

1. client → appointment-service
2. appointment-service → patient-service
3. appointment-service → doctor-service

So the test loads all three containers and the Docker network at the same time.

### Test procedure (what `benchmark.py` does)

| Step | Detail |
|---|---|
| Health check | Aborts if `/health/dependencies` is not `UP` |
| Monitoring | One `docker stats` stream runs in the background for the **whole** test. Every sample (about 1 per second per container) is time-stamped and saved. |
| Idle baseline | 5 s with no load, to compare against |
| Warm-up | 50 requests that are **not** recorded (first requests are slower) |
| Run length | Each run sends **at least 500 requests and lasts at least 10 s**. The 10 s floor gives about 10 or more `docker stats` samples per run even at the highest throughput. Otherwise a fast run could finish between two samples. |
| Repetitions | Every level is run **3 times**, interleaved (W1…W5, W1…W5, W1…W5), and the mean is reported with its standard deviation |
| Cool-down | 3 s pause between runs so resource samples of different runs do not mix |

### What is measured

| Metric | How |
|---|---|
| Response time | Time from sending the request to receiving the complete response, measured by the client: average, median, 95th percentile, max |
| Throughput | Successful requests ÷ wall-clock duration of the run (req/s) |
| Success / failed | HTTP 200 = success; any other status, timeout or connection error = failed (type recorded) |
| CPU % | `docker stats` samples taken **during** the run → **average and peak for each container separately** (100 % = one full CPU core) |
| Memory | `docker stats` samples taken **during** the run → **average and peak for each container separately** (MiB) |

A `docker stats` sample describes roughly the second *before* it was printed. The script therefore matches samples to a run using the window [start + 1 s, end + 1 s].

---

## 11. Results

The measured results of the final run are in **[`results/RESULTS.md`](results/RESULTS.md)**. It contains:

* the observation table required by the manual: workload, concurrency, response time, throughput, failed requests, CPU and memory,
* a per-service table with CPU and memory average and peak for each microservice,
* observations computed from the data: response-time growth, saturation point, failures, which service uses the most resources, and load compared with idle,
* the five graphs.

The raw data is in `results/workload_results.csv`, `results/runs.csv` and `results/resource_samples.csv`.

### Graphs

| Graph | File |
|---|---|
| Concurrency vs average and p95 response time | `graphs/01-response-time.png` |
| Concurrency vs throughput | `graphs/02-throughput.png` |
| Concurrency vs CPU utilization, per service | `graphs/03-cpu-utilization.png` |
| Concurrency vs memory usage, per service | `graphs/04-memory-utilization.png` |
| CPU and memory per service at the highest load | `graphs/05-resource-by-service.png` |

---

## 12. Interpreting the Results

Use this section together with the numbers in `results/RESULTS.md`.

**Why response time increases with concurrency.**
Each service has a limited capacity: the CPU it can use, and Python's Global Interpreter Lock (GIL). Once that capacity is reached, more concurrent requests cannot be processed faster. They wait for a thread or the CPU, so each request takes longer. In a closed-loop test, *concurrency ≈ throughput × response time* (Little's law). Once throughput stops growing, doubling the concurrency roughly doubles the response time. `RESULTS.md` checks this relation on the measured data.

**Why throughput rises and then levels off.**
At low concurrency the services are partly idle while waiting for the network, so adding clients adds throughput. The level at which throughput stops increasing is the **saturation point**. `RESULTS.md` identifies it automatically. Beyond it, throughput stays flat or drops slightly, because more threads competing for the same CPU adds context-switching overhead.

**Why appointment-service uses the most CPU.**
For every client request, appointment-service:

* receives the request,
* makes **two outgoing HTTP calls** (to patient-service and to doctor-service), each with a new TCP connection,
* parses two JSON responses,
* builds and serializes a larger combined JSON response.

The patient and doctor services each do only one simple dictionary lookup per request.

**How to read the memory results.**
A container's memory is mostly its *starting footprint*: the Python interpreter, Flask and the loaded data. That footprint is already there before any load. Small differences in it between containers, or between runs, say little about the workload. The part caused by the load is the **increase from the idle baseline**, which `results/RESULTS.md` reports for each service.

* Appointment-service shows the largest load-related increase, because it holds two outgoing connections and larger JSON objects for every request in flight. It also loads the `requests` library.
* In the final run, doctor-service already used about 44 MiB while completely idle, before any request was sent. Patient-service used about 25 MiB. That higher figure is a difference in starting footprint, not an effect of the load: doctor-service's memory grew by only about 0.2 MiB under the heaviest load.

**Why memory stays almost constant.**
The data is small and held in memory from start-up, and nothing is cached or stored per request. The only per-request memory is short-lived (thread stack, request/response objects) and is freed straight away. Memory therefore rises only slightly under load.

**Other factors that limit performance in this set-up:**

* The services use Flask's built-in threaded server, which is meant for development. Each request gets a thread, but all threads share one Python process and therefore one GIL. A production WSGI server with several worker processes (for example Gunicorn) would scale further.
* The two downstream calls are made one after the other, so the end-to-end latency is the sum of both.
* The load generator runs on the same machine as the containers and competes with them for CPU.
* On Windows/macOS, Docker Desktop runs containers inside a lightweight VM. `docker stats` CPU % is relative to the CPUs given to that VM.
* **Why a container can show more than 100 % CPU.** `docker stats` counts 100 % as one full CPU core, and it counts *all* CPU time charged to the container. That includes the operating-system kernel's work for the container's network traffic: appointment-service opens three TCP connections per client request (one in, two out). The GIL only prevents two threads from running *Python code* at the same moment. Socket I/O, the kernel networking work and parts of the `requests`/JSON libraries run outside the GIL, so a busy multithreaded Python container can use more than one core.
* The idle baseline is measured over only 5 s (about 8 samples per container). A single health-check sample can therefore raise the idle *average* noticeably. In the final run, the idle CPU of about 15 % comes from one sample of 45 % (doctor-service) and one of 33 % (appointment-service), each taken while a health check was running.
* Docker health checks start a short Python process inside each container every 30 s. This can show up as an occasional small spike in the *peak* CPU or memory of a container. The *average* is barely affected.

**Failures.**
Every failed request is recorded with its type (HTTP status, timeout or connection error) in `results/runs.csv`. `RESULTS.md` reports the total.

---

## 13. Limitations

* Single machine: the client and all services share the same CPU.
* Flask development server instead of a production WSGI server.
* In-memory data (no database), so database latency is not part of the measurements.
* `docker stats` samples about once per second, so very short spikes may be missed. Averages over 10 s+ runs are reliable.
* Flask's development server closes the TCP connection after every response (`Connection: close`), so HTTP keep-alive is not possible. Every request, and every internal call, opens a new connection, which adds latency.

### Troubleshooting the benchmark

| Symptom | Cause / fix |
|---|---|
| `Cannot reach appointment-service` | Start the stack first: `docker compose up -d --build` |
| `docker stats produced no samples` | Docker Desktop is not running, or the containers are not up |
| Warning `fewer than 2 docker stats samples` | Increase the run length: `python benchmark.py --min-duration 15` |
| Failures of type `ConnectionError` at high load on Windows, while the containers stay healthy | Windows ran out of temporary client ports, because each request uses a new TCP connection and closed ones are held for about 2 minutes. This is a limit of the client machine, not of the application. Wait 2 minutes and re-run, or use `--min-duration 8`. If it still happens, report it as an observation. |
| Failures of type `HTTP 503` / `HTTP 504` | A downstream service was down or too slow. Check `docker compose ps` and `docker compose logs` |

---

## 14. Screenshots

Screenshots are stored in `screenshots/`:

| File | Shows |
|---|---|
| `01-Patient-Service-Running.png` | Patient service running standalone (`python app.py`) |
| `02-Patient-Service-API.png` | Patient API response |
| `03-Doctor-Service-Running.png` | Doctor service running standalone |
| `04-Doctor-Service-API.png` | Doctor API response |
| `05-Appointment-Service-Running.png` | Appointment service running standalone (`python app.py`): end-to-end response served by the local Python process |
| `06-Docker-Images.png` | `docker images` – three service images |
| `07-Docker-Compose-Containers.png` | `docker compose ps` / `docker ps` – three containers `(healthy)` |
| `08-Docker-Stats-During-Load.png` | `docker stats` while the benchmark is running |
| `09-End-to-End-Microservice-Communication.png` | `GET /appointments/1` combined response |
| `10-Graphs-and-Results-Generated.png` | `generate_graphs.py` / `generate_report.py` output and generated files |
| `11-Appointment-API.png` | Appointment API response and `docker compose up -d` |
| `12-Health-and-Dependencies.png` | `/health`, `/health/dependencies` and end-to-end request |
| `13-Workload-Benchmark.png` | `python benchmark.py` output |
| `14-Service-Down-503.png` | `docker compose stop patient-service` → 503 JSON error |

---

## 15. Conclusion

The Hospital Management System was implemented as three independent Flask microservices: Patient, Doctor and Appointment. Each was containerized with its own Dockerfile and deployed with Docker Compose.

All three services share a user-defined bridge network. The Appointment Service reaches the other two by their Docker service names, configured through environment variables. It combines their data into one end-to-end response, and it returns clear error codes when a dependency is down or slow.

The workload was tested at concurrency levels 1, 2, 4, 8 and 16:

* each level was run 3 times,
* each run sent at least 500 requests over at least 10 s, after a warm-up,
* CPU and memory were monitored continuously for each container during the load.

The measured results, generated directly from the raw data in `results/RESULTS.md`, show how response time, throughput and resource usage change as the load increases. They also identify the saturation point of the application and the microservice that consumes the most resources.

---

## Author

**Name:** Shreenidhi Dharwad

**Course:** Cloud Computing

**Institution:** KLE Technological University

**Academic Year:** 2026
