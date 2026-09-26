from flask import Flask
from flask_cors import CORS

from app.config import Config
from app.errors import register_error_handlers


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    CORS(app)
    register_error_handlers(app)

    from app.routes.search import search_bp
    from app.routes.videos import videos_bp
    from app.routes.embed import embed_bp
    from app.routes.health import health_bp
    from app.routes.dres import dres_bp
    from app.routes.admin import admin_bp
    from app.routes.submissions import submissions_bp
    from app.routes.keyframes import keyframes_bp
    from app.routes.video_stream import video_stream_bp
    from app.routes.agent import agent_bp

    app.register_blueprint(search_bp)
    app.register_blueprint(videos_bp)
    app.register_blueprint(embed_bp)
    app.register_blueprint(health_bp)
    app.register_blueprint(dres_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(submissions_bp)
    app.register_blueprint(keyframes_bp)
    app.register_blueprint(video_stream_bp)
    app.register_blueprint(agent_bp)

    return app


app = create_app()
