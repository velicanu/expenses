import json
import os
import subprocess
import threading
import webbrowser

from flask import Flask, Response, request
from werkzeug.utils import secure_filename

import pipeline
from detect import save_file_if_valid

script_dir = os.path.dirname(os.path.realpath(__file__))

app = Flask(__name__)
app.url_map.strict_slashes = False
app.config["DATA_DIR"] = os.path.join(script_dir, "..", "data")
streamlit_options = [
    "streamlit",
    "run",
    os.path.join(script_dir, "streamlit_app.py"),
    "--server.headless",
    "true",
    "--browser.gatherUsageStats",
    "false",
    "--server.port",
    "8501",
]

app.streamlit = subprocess.Popen(streamlit_options)


# Routes
@app.route("/")
def root():
    return app.send_static_file("index.html")


@app.route("/upload", methods=["GET", "POST"])
def upload():
    if request.method == "POST":
        file_upload_status = {"success": [], "failed": []}
        for file_ in request.files.getlist("file"):
            filename = secure_filename(file_.filename)
            status, status_string = save_file_if_valid(
                file_, filename, app.config["DATA_DIR"]
            )
            file_upload_status[status].append(status_string)

        return Response(json.dumps(file_upload_status))
    else:
        return Response()


@app.route("/run")
def run():
    if pipeline.run(app.config["DATA_DIR"]):
        app.streamlit.terminate()
        app.streamlit = subprocess.Popen(streamlit_options)
        return Response()
    else:
        return Response(status=400)


@app.route("/<path:path>")
def static_proxy(path):
    return app.send_static_file(path)


def open_browser():
    webbrowser.open("http://127.0.0.1:5000/")


if __name__ == "__main__":
    threading.Timer(1, open_browser).start()
    app.run(port=5000)
