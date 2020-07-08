import json
import os
import subprocess

from flask import Flask, Response, request
from werkzeug.utils import secure_filename

import pipeline
from common import save_file_if_valid

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
    pipeline.run(app.config["DATA_DIR"])
    app.streamlit.terminate()
    app.streamlit = subprocess.Popen(streamlit_options)
    return Response()


@app.route("/<path:path>")
def static_proxy(path):
    return app.send_static_file(path)


if __name__ == "__main__":
    app.run()
