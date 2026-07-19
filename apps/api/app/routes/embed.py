from flask import Blueprint, request, jsonify
from app.services.embed import embed_text, embed_image, enhance_query

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
    vec = embed_text([text])[0].tolist()
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
    vec = embed_image(file.read()).tolist()
    return jsonify({"vector": vec, "dim": len(vec), "filename": file.filename})
