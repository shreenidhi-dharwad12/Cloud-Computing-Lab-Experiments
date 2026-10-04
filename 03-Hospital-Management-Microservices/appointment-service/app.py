from flask import Flask, jsonify
import requests

app = Flask(__name__)

appointments = {
    1: {
        "id": 1,
        "patient_id": 1,
        "doctor_id": 1,
        "date": "2026-10-03",
        "time": "10:00 AM",
        "status": "Confirmed"
    },
    2: {
        "id": 2,
        "patient_id": 2,
        "doctor_id": 2,
        "date": "2026-10-04",
        "time": "11:30 AM",
        "status": "Confirmed"
    }
}


@app.route("/appointments/<int:appointment_id>", methods=["GET"])
def get_appointment(appointment_id):
    appointment = appointments.get(appointment_id)

    if not appointment:
        return jsonify({"error": "Appointment not found"}), 404

    try:
        patient_response = requests.get(
            f"http://patient-service:5001/patients/{appointment['patient_id']}",
            timeout=5
        )

        doctor_response = requests.get(
            f"http://doctor-service:5002/doctors/{appointment['doctor_id']}",
            timeout=5
        )

    except requests.RequestException:
        return jsonify({
            "error": "Dependent microservice unavailable"
        }), 503

    if patient_response.status_code != 200:
        return jsonify({
            "error": "Patient Service unavailable"
        }), 503

    if doctor_response.status_code != 200:
        return jsonify({
            "error": "Doctor Service unavailable"
        }), 503

    return jsonify({
        "appointment": appointment,
        "patient": patient_response.json(),
        "doctor": doctor_response.json()
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5003)