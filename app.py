import io
import json
import os

from flask import Flask, Response, request
from werkzeug.utils import secure_filename

from common import records_from_file
from detect import identify_card

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
        uploads = {"success": [], "failed": []}
        for file_ in request.files.getlist("file"):
            filename = secure_filename(file_.filename)
            with io.BytesIO() as stream:
                file_.save(stream)
                stream.seek(0)
                first_record = records_from_file(stream)[0]
                card, card_def = identify_card(first_record)
                if card:
                    file_.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
                    uploads["success"].append(f"{filename}: {card}")
                else:
                    uploads["failed"].append(f"{filename}")

        return Response(json.dumps(uploads))
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
