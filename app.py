from flask import Flask, Response

app = Flask(__name__)
app.url_map.strict_slashes = False


# Routes
@app.route("/")
def root():
    return app.send_static_file("index.html")


@app.route("/upload")
def upload():
    print("upload")
    return Response("upload")


@app.route("/run")
def run():
    print("run")
    return Response("run")


@app.route("/<path:path>")
def static_proxy(path):
    return app.send_static_file(path)


if __name__ == "__main__":
    app.run()
