from . import admin
from flask import jsonify
from flask_jwt_extended import jwt_required, verify_jwt_in_request

@admin.route('/api/dashboard', methods=["GET", "POST"])
@jwt_required()
def dashboard():
    claims = verify_jwt_in_request()[1]
    
    role = claims['sub']['role']
    if not role == "admin":
        return jsonify({"msg": "Admins only!"}), 403