"""Regression tests for SigLIP2 query preprocessing."""

import torch

from app.services.encoders.siglip2 import Siglip2Encoder


class RecordingProcessor:
    def __init__(self) -> None:
        self.kwargs: dict[str, object] = {}

    def __call__(self, **kwargs: object) -> dict[str, torch.Tensor]:
        self.kwargs = kwargs
        texts = kwargs["text"]
        assert isinstance(texts, list)
        return {
            "input_ids": torch.ones((len(texts), 64), dtype=torch.long),
            "attention_mask": torch.ones((len(texts), 64), dtype=torch.long),
        }


class FixedTextModel:
    def get_text_features(
        self, *, input_ids: torch.Tensor, attention_mask: torch.Tensor
    ) -> torch.Tensor:
        assert input_ids.shape == (2, 64)
        assert attention_mask.shape == (2, 64)
        return torch.tensor([[3.0, 4.0] + [0.0] * 1150, [0.0, 5.0] + [0.0] * 1150])


def test_siglip2_text_processor_uses_explicit_checkpoint_length() -> None:
    encoder = Siglip2Encoder()
    processor = RecordingProcessor()
    encoder._processor = processor
    encoder._model = FixedTextModel()

    vectors = encoder.embed_text(["a cat", "a dog"])

    assert processor.kwargs["padding"] == "max_length"
    assert processor.kwargs["truncation"] is True
    assert processor.kwargs["max_length"] == 64
    assert processor.kwargs["return_tensors"] == "pt"
    assert vectors.shape == (2, 1152)
    assert vectors.dtype.name == "float32"
    assert torch.allclose(torch.from_numpy(vectors).norm(dim=1), torch.ones(2))
    assert torch.isfinite(torch.from_numpy(vectors)).all()


def test_siglip2_calibrates_text_similarity_with_its_learned_logits() -> None:
    encoder = Siglip2Encoder()
    encoder._text_logit_scale = 10.0
    encoder._text_logit_bias = -1.0

    assert encoder.calibrate_text_similarity(0.1) == 0.5
    assert encoder.calibrate_text_similarity(0.2) is not None
    assert encoder.calibrate_text_similarity(0.2) > 0.5
