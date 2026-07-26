import os
import threading

from flask import Flask
from flask_cors import CORS

from app.config import Config

WARMUP = os.getenv("SEARCH_WARMUP", "1") != "0"


def _warmup() -> None:
    """Build the lazy singletons before the first request.

    Request threads share the CLIP model and the Milvus connection; without this
    two concurrent cold requests would each load ViT-H-14.
    """
    from app.services import embed, milvus_client

    for name, fn in (("milvus", milvus_client.warmup), ("clip", embed.warmup)):
        try:
            fn()
        except Exception as e:  # a missing backend must not stop the API
            print(f"warmup {name} failed: {e}")


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    CORS(app)

    from app.services import video_meta

    print(f"Loaded metadata for {video_meta.load()} videos.")
    if WARMUP:
        threading.Thread(target=_warmup, daemon=True).start()

    from app.routes.search import search_bp
    from app.routes.videos import videos_bp
    from app.routes.embed import embed_bp
    from app.routes.health import health_bp
    from app.routes.dres import dres_bp

    app.register_blueprint(search_bp)
    app.register_blueprint(videos_bp)
    app.register_blueprint(embed_bp)
    app.register_blueprint(health_bp)
    app.register_blueprint(dres_bp)

    return app


app = create_app()
