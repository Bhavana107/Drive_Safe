from flask import Flask, jsonify, render_template, request

import config
import database


app = Flask(__name__, template_folder="templates", static_folder="static")


@app.get("/")
def dashboard():
    return render_template("index.html")


@app.get("/api/status")
def status():
    return jsonify(database.get_latest_state(read_only=True))


@app.get("/api/analytics")
def analytics():
    return jsonify(database.get_analytics(read_only=True))


@app.get("/api/history")
def history():
    try:
        limit = int(request.args.get("limit", "100"))
    except ValueError:
        return jsonify({"error": "limit must be an integer"}), 400
    level = request.args.get("level")
    return jsonify(database.get_history(limit=limit, level=level, read_only=True))


@app.get("/api/sessions")
def sessions():
    return jsonify(database.get_session_stats(read_only=True))


if __name__ == "__main__":
    app.run(
        host=config.FLASK_HOST,
        port=config.FLASK_PORT,
        debug=False,
        threaded=True,
    )
