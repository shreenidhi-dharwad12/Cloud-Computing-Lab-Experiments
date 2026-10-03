from flask import Flask, jsonify

app = Flask(__name__)

patients = {
    1: {
        "id": 1,
        "name": "Rahul",
        "age": 25,
        "gender": "Male"
    },
    2: {
        "id": 2,
        "name": "Priya",
        "age": 30,
        "gender": "Female"
    }
}


@app.route("/patients/<int:patient_id>", methods=["GET"])
def get_patient(patient_id):
    patient = patients.get(patient_id)

    if patient:
        return jsonify(patient)

    return jsonify({"error": "Patient not found"}), 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)