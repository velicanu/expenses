from flask import Flask, Response

app = Flask(__name__)


# Routes
@app.route("/")
def root():
    return app.send_static_file("index.html")


@app.route("/upload")
@app.route("/upload/")
def upload():
    print("upload")
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
