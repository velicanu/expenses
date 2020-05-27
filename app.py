import os

from flask import Flask, Response, request
from werkzeug.utils import secure_filename

script_dir = os.path.dirname(os.path.realpath(__file__))

app = Flask(__name__)
app.url_map.strict_slashes = False
app.config["UPLOAD_FOLDER"] = os.path.join(script_dir, "data", "raw")


# Routes
@app.route("/")
def root():
    return app.send_static_file("index.html")


@app.route("/upload", methods=["GET", "POST"])
def upload():
    if request.method == "POST":
        for file_ in request.files.getlist("file"):
            filename = secure_filename(file_.filename)
            file_.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

        return Response("success")
    else:
        return Response()


@app.route("/run")
def run():
    print("run")
    return Response("run")


@app.route("/<path:path>")
def static_proxy(path):
    return app.send_static_file(path)


if __name__ == "__main__":
    app.run()
