"""
Appointment Service
-------------------
Responsibility: owns appointment records and builds the combined
appointment view by calling the Patient Service and the Doctor Service.

Endpoints
  GET /health                       -> liveness check used by Docker Compose
  GET /health/dependencies          -> checks that patient-service and
                                       doctor-service are reachable
  GET /appointments                 -> list all appointments (no enrichment)
  GET /appointments/<appointment_id>-> appointment + patient + doctor
                                       (end-to-end request across 3 services)

Where the other services live is configured with environment variables:
  PATIENT_SERVICE_URL  (default http://localhost:5001)
  DOCTOR_SERVICE_URL   (default http://localhost:5002)

Inside Docker Compose these are set to the Docker service names
(http://patient-service:5001 and http://doctor-service:5002), so the
containers talk to each other over the hospital-network bridge network.
The localhost defaults let the service also be run on its own with
`python app.py` for Checkpoint 1.

Error handling for downstream calls
  downstream unreachable (container stopped) -> 503 Service Unavailable
  downstream too slow (timeout)              -> 504 Gateway Timeout
  referenced patient/doctor does not exist   -> 404 Not Found
  any other bad downstream response          -> 502 Bad Gateway
"""

import json
import os
from pathlib import Path

import requests
from flask import Flask, jsonify

SERVICE_NAME = "appointment-service"
PORT = int(os.getenv("PORT", "5003"))

PATIENT_SERVICE_URL = os.getenv(
    "PATIENT_SERVICE_URL", "http://localhost:5001"
).rstrip("/")
DOCTOR_SERVICE_URL = os.getenv(
    "DOCTOR_SERVICE_URL", "http://localhost:5002"
).rstrip("/")

# Timeout in seconds (applied to both connecting and reading) for every
# downstream call, so a hung service cannot block appointment-service forever.
DOWNSTREAM_TIMEOUT = float(os.getenv("DOWNSTREAM_TIMEOUT_SECONDS", "3"))

DATA_FILE = Path(__file__).resolve().parent / "data" / "appointments.json"

app = Flask(__name__)


def load_appointments():
    with DATA_FILE.open(encoding="utf-8") as file:
        return {item["id"]: item for item in json.load(file)}


appointments = load_appointments()


class DownstreamError(Exception):
    """Raised when a call to patient-service or doctor-service fails."""

    def __init__(self, service, status_code, message):
        super().__init__(message)
        self.service = service
        self.status_code = status_code
        self.message = message


def call_service(service, url):
    """GET a downstream URL and return its JSON body, or raise DownstreamError."""
    try:
        response = requests.get(url, timeout=DOWNSTREAM_TIMEOUT)
    except requests.Timeout:
        raise DownstreamError(
            service, 504,
            f"{service} did not respond within {DOWNSTREAM_TIMEOUT} s",
        )
    except requests.ConnectionError:
        raise DownstreamError(service, 503, f"{service} is unavailable")
    except requests.RequestException as error:
        raise DownstreamError(service, 502, f"{service} request failed: {error}")

    if response.status_code == 404:
        raise DownstreamError(service, 404, f"Record not found in {service}")

    if response.status_code != 200:
        raise DownstreamError(
            service, 502,
            f"{service} returned HTTP {response.status_code}",
        )

    try:
        return response.json()
    except ValueError:
        raise DownstreamError(service, 502, f"{service} returned invalid JSON")


def error_response(error):
    return jsonify({"error": error.message, "service": error.service}), error.status_code


@app.get("/health")
def health():
    return jsonify({"service": SERVICE_NAME, "status": "UP"})


@app.get("/health/dependencies")
def health_dependencies():
    """Shows that appointment-service can reach the other two containers."""
    dependencies = {}
    all_up = True

    for service, base_url in (
        ("patient-service", PATIENT_SERVICE_URL),
        ("doctor-service", DOCTOR_SERVICE_URL),
    ):
        try:
            call_service(service, f"{base_url}/health")
            dependencies[service] = {"url": base_url, "status": "UP"}
        except DownstreamError as error:
            all_up = False
            dependencies[service] = {
                "url": base_url, "status": "DOWN", "error": error.message,
            }

    body = {
        "service": SERVICE_NAME,
        "status": "UP" if all_up else "DEGRADED",
        "dependencies": dependencies,
    }
    return jsonify(body), (200 if all_up else 503)


@app.get("/appointments")
def list_appointments():
    return jsonify(list(appointments.values()))


@app.get("/appointments/<int:appointment_id>")
def get_appointment(appointment_id):
    appointment = appointments.get(appointment_id)

    if appointment is None:
        return jsonify({"error": f"Appointment {appointment_id} not found"}), 404

    try:
        # The two downstream calls are made one after the other, so the
        # end-to-end response time includes both of them.
        patient = call_service(
            "patient-service",
            f"{PATIENT_SERVICE_URL}/patients/{appointment['patient_id']}",
        )
        doctor = call_service(
            "doctor-service",
            f"{DOCTOR_SERVICE_URL}/doctors/{appointment['doctor_id']}",
        )
    except DownstreamError as error:
        return error_response(error)

    return jsonify({
        "appointment": appointment,
        "patient": patient,
        "doctor": doctor,
    })


@app.errorhandler(404)
def not_found(_error):
    return jsonify({"error": "Endpoint not found"}), 404


if __name__ == "__main__":
    # threaded=True: each incoming request is handled in its own thread.
    app.run(host="0.0.0.0", port=PORT, threaded=True)
