from app.services.encoders.base import Encoder
from app.services.encoders.beit3 import Beit3Encoder
from app.services.encoders.bge_vl import BgeVlEncoder
from app.services.encoders.metaclip import MetaClipEncoder
from app.services.encoders.siglip2 import Siglip2Encoder

ENCODER_REGISTRY: dict[str, type[Encoder]] = {
    MetaClipEncoder.model_id: MetaClipEncoder,
    BgeVlEncoder.model_id: BgeVlEncoder,
    Beit3Encoder.model_id: Beit3Encoder,
    Siglip2Encoder.model_id: Siglip2Encoder,
}
