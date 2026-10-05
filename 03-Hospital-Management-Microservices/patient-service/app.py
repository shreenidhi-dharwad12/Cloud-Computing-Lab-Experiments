"""
Patient Service
---------------
Responsibility: owns patient records and exposes them over REST.

Endpoints
  GET /health                 -> liveness check used by Docker Compose
  GET /patients               -> list all patients
  GET /patients/<patient_id>  -> one patient (404 if it does not exist)

Data is loaded from data/patients.json at start-up and kept in memory
(no database is required by the lab manual).
"""

import json
import os
from pathlib import Path

from flask import Flask, jsonify

SERVICE_NAME = "patient-service"
PORT = int(os.getenv("PORT", "5001"))
DATA_FILE = Path(__file__).resolve().parent / "data" / "patients.json"

app = Flask(__name__)


def load_patients():
    with DATA_FILE.open(encoding="utf-8") as file:
        return {patient["id"]: patient for patient in json.load(file)}


patients = load_patients()


@app.get("/health")
def health():
    return jsonify({"service": SERVICE_NAME, "status": "UP"})


@app.get("/patients")
def list_patients():
    return jsonify(list(patients.values()))


@app.get("/patients/<int:patient_id>")
def get_patient(patient_id):
    patient = patients.get(patient_id)

    if patient is None:
        return jsonify({"error": f"Patient {patient_id} not found"}), 404

    return jsonify(patient)


@app.errorhandler(404)
def not_found(_error):
    return jsonify({"error": "Endpoint not found"}), 404


if __name__ == "__main__":
    # threaded=True: each incoming request is handled in its own thread.
    app.run(host="0.0.0.0", port=PORT, threaded=True)
