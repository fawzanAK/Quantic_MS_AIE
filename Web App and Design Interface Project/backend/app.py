from flask import Flask, jsonify
from flask_cors import CORS

from config import Config
from extensions import db
from menu_data import MENU
from routes.newsletter import newsletter_bp
from routes.reservations import reservations_bp


def create_app(config_object=Config):
    app = Flask(__name__)
    app.config.from_object(config_object)

    db.init_app(app)
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    app.register_blueprint(reservations_bp)
    app.register_blueprint(newsletter_bp)

    @app.route("/api/menu", methods=["GET"])
    def get_menu():
        return jsonify(MENU)

    @app.route("/api/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok"})

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
