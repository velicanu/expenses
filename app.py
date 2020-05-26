from flask import Flask, Response, request
from werkzeug.utils import secure_filename

app = Flask(__name__)


# Routes
@app.route("/")
def root():
    return app.send_static_file("index.html")


@app.route("/upload", methods=["GET", "POST"])
def upload():
    if request.method == "POST":
        print(request.files)
        file = request.files["file"]

        filename = secure_filename(file.filename)

        print(filename)
        return Response("upload")


@app.route("/run")
@app.route("/run/")
def run():
    print("run")
    return Response("run")


@app.route("/<path:path>")
def static_proxy(path):
    return app.send_static_file(path)


if __name__ == "__main__":
    app.run()
