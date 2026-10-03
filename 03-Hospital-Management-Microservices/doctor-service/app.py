from flask import Flask, jsonify

app = Flask(__name__)

doctors = {
    1: {
        "id": 1,
        "name": "Dr. Ashok Dharwad",
        "specialization": "Gastroenterologist"
    },
    2: {
        "id": 2,
        "name": "Dr. Sunita",
        "specialization": "Neurology"
    }
}


@app.route("/doctors/<int:doctor_id>", methods=["GET"])
def get_doctor(doctor_id):
    doctor = doctors.get(doctor_id)

    if doctor:
        return jsonify(doctor)

    return jsonify({"error": "Doctor not found"}), 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002)