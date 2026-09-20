from app.config import Config
from app.services.encoders.base import Encoder
from app.services.encoders.beit3 import Beit3Encoder
from app.services.encoders.bge_vl import BgeVlEncoder
from app.services.encoders.metaclip import MetaClipEncoder

ENCODER_REGISTRY: dict[str, type[Encoder]] = {
    MetaClipEncoder.model_id: MetaClipEncoder,
    BgeVlEncoder.model_id: BgeVlEncoder,
    Beit3Encoder.model_id: Beit3Encoder,
}

# SigLIP2 pulls its weights from HuggingFace at load time, so it only joins the
# registry when SIGLIP2_ENABLED is set. Importing it unconditionally would make
# `transformers` a hard import for every process that touches the registry.
if Config.SIGLIP2_ENABLED:
    from app.services.encoders.siglip2 import Siglip2Encoder

    ENCODER_REGISTRY[Siglip2Encoder.model_id] = Siglip2Encoder
