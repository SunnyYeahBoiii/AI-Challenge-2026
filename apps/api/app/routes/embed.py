from flask import Blueprint, request, jsonify
from app.services.encoders import manager
from app.services.encoders.manager import NoActiveModelError
from app.services.query_enhance import enhance_query

embed_bp = Blueprint("embed", __name__)


@embed_bp.route("/api/embed/text", methods=["POST"])
def api_embed_text():
    data = request.get_json()
    text = data.get("text", "")
    enhance = data.get("enhance", True)
    if not text:
        return jsonify({"error": "text is required"}), 400
    original_text = text
    if enhance:
        text = enhance_query(text)
    try:
        vec = manager.embed_text([text])[0].tolist()
    except NoActiveModelError as exc:
        return jsonify({"error": str(exc)}), 409
    return jsonify({
        "vector": vec,
        "dim": len(vec),
        "text": text,
        "enhanced": enhance and text != original_text,
    })


@embed_bp.route("/api/embed/image", methods=["POST"])
def api_embed_image():
    if "image" not in request.files:
        return jsonify({"error": "image file is required"}), 400
    file = request.files["image"]
    try:
        vec = manager.embed_image(file.read()).tolist()
    except NoActiveModelError as exc:
        return jsonify({"error": str(exc)}), 409
    return jsonify({"vector": vec, "dim": len(vec), "filename": file.filename})
