"""
Doctor Service
--------------
Responsibility: owns doctor records and exposes them over REST.

Endpoints
  GET /health               -> liveness check used by Docker Compose
  GET /doctors              -> list all doctors
  GET /doctors/<doctor_id>  -> one doctor (404 if it does not exist)

Data is loaded from data/doctors.json at start-up and kept in memory
(no database is required by the lab manual).
"""

import json
import os
from pathlib import Path

from flask import Flask, jsonify

SERVICE_NAME = "doctor-service"
PORT = int(os.getenv("PORT", "5002"))
DATA_FILE = Path(__file__).resolve().parent / "data" / "doctors.json"

app = Flask(__name__)


def load_doctors():
    with DATA_FILE.open(encoding="utf-8") as file:
        return {doctor["id"]: doctor for doctor in json.load(file)}


doctors = load_doctors()


@app.get("/health")
def health():
    return jsonify({"service": SERVICE_NAME, "status": "UP"})


@app.get("/doctors")
def list_doctors():
    return jsonify(list(doctors.values()))


@app.get("/doctors/<int:doctor_id>")
def get_doctor(doctor_id):
    doctor = doctors.get(doctor_id)

    if doctor is None:
        return jsonify({"error": f"Doctor {doctor_id} not found"}), 404

    return jsonify(doctor)


@app.errorhandler(404)
def not_found(_error):
    return jsonify({"error": "Endpoint not found"}), 404


if __name__ == "__main__":
    # threaded=True: each incoming request is handled in its own thread.
    app.run(host="0.0.0.0", port=PORT, threaded=True)
