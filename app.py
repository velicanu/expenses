from flask import Flask

app = Flask(__name__)


# Routes
@app.route("/")
def root():
    return app.send_static_file("index.html")


if __name__ == "__main__":
    app.run()
