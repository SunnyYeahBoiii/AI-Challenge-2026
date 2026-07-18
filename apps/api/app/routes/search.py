from flask import Blueprint

search_bp = Blueprint("search", __name__)


@search_bp.route("/api/search", methods=["POST"])
def search():
    return {"results": [], "total": 0}
