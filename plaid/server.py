@app.route("/api/manual", methods=["POST", "GET"])
def manual():
    global access_token
    access_token = request.get_json()["access_token"]
    return "OK"


@app.route("/api/info", methods=["POST", "GET"])
def info():
    global access_token
    global item_id
    return jsonify(
        {"item_id": item_id, "access_token": access_token, "products": PLAID_PRODUCTS}
    )
