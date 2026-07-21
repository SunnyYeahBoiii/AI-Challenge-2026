from typing import Any

from flask import Flask, jsonify
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

from app.config import Config


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    CORS(app)

    from app.routes.search import search_bp
    from app.routes.videos import videos_bp
    from app.routes.embed import embed_bp
    from app.routes.dres import dres_bp
    from app.routes.health import health_bp

    app.register_blueprint(search_bp)
    app.register_blueprint(videos_bp)
    app.register_blueprint(embed_bp)
    app.register_blueprint(dres_bp)
    app.register_blueprint(health_bp)

    @app.errorhandler(Exception)
    def handle_unexpected_error(error: Exception) -> Any:
        if isinstance(error, HTTPException):
            return error
        app.logger.exception("Unhandled API error", exc_info=error)
        return (
            jsonify(
                {
                    "error": {
                        "code": "INTERNAL_SERVER_ERROR",
                        "message": "An unexpected server error occurred",
                    }
                }
            ),
            500,
        )

    return app


app = create_app()
