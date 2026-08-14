from flask import Flask
from flask_cors import CORS

from app.config import Config


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    CORS(app)

    from app.routes.search import search_bp
    from app.routes.videos import videos_bp
    from app.routes.embed import embed_bp
    from app.routes.health import health_bp
    from app.routes.dres import dres_bp
    from app.routes.admin import admin_bp
    from app.routes.submissions import submissions_bp

    app.register_blueprint(search_bp)
    app.register_blueprint(videos_bp)
    app.register_blueprint(embed_bp)
    app.register_blueprint(health_bp)
    app.register_blueprint(dres_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(submissions_bp)

    return app


app = create_app()
