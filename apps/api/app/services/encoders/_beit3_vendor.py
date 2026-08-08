"""BEiT-3 retrieval head, vendored (inference-only) from microsoft/unilm/beit3.

Source: https://github.com/microsoft/unilm/tree/master/beit3
  - modeling_utils.py (BEiT3Wrapper, _get_large_config)
  - modeling_finetune.py (BEiT3ForRetrieval, beit3_large_patch16_384_retrieval)
Copyright (c) 2023 Microsoft. Licensed under the MIT License.

torchscale.model.BEiT3.BEiT3 (the transformer core) is not vendored — it ships as
a real PyPI package (`torchscale`) and is imported directly. Only the retrieval
head and config helper, which unilm/beit3 never published as a package, live here.
The training-only `criterion`/`ClipLoss` path from the original BEiT3ForRetrieval
is dropped since this project only ever calls the model with `only_infer=True`.
"""

from typing import Any

import torch
import torch.nn as nn
import torch.nn.functional as F
from timm.models.layers import trunc_normal_ as _trunc_normal_  # type: ignore[attr-defined]
from torchscale.architecture.config import EncoderConfig
from torchscale.model.BEiT3 import BEiT3


def _trunc_normal(tensor: torch.Tensor, std: float = 0.02) -> None:
    _trunc_normal_(tensor, mean=0.0, std=std, a=-std, b=std)


def get_large_config(img_size: int = 224, patch_size: int = 16, vocab_size: int = 64010) -> EncoderConfig:
    return EncoderConfig(
        img_size=img_size,
        patch_size=patch_size,
        vocab_size=vocab_size,
        multiway=True,
        layernorm_embedding=False,
        normalize_output=True,
        no_output_layer=True,
        drop_path_rate=0,
        encoder_embed_dim=1024,
        encoder_attention_heads=16,
        encoder_ffn_embed_dim=1024 * 4,
        encoder_layers=24,
        checkpoint_activations=None,
    )


class BEiT3Wrapper(nn.Module):
    def __init__(self, args: EncoderConfig) -> None:
        super().__init__()
        self.args = args
        self.beit3 = BEiT3(args)
        self.apply(self._init_weights)

    def _init_weights(self, m: nn.Module) -> None:
        if isinstance(m, nn.Linear):
            _trunc_normal(m.weight)
            if m.bias is not None:
                nn.init.constant_(m.bias, 0)
        elif isinstance(m, nn.LayerNorm):
            nn.init.constant_(m.bias, 0)
            nn.init.constant_(m.weight, 1.0)


class BEiT3ForRetrieval(BEiT3Wrapper):
    def __init__(self, args: EncoderConfig) -> None:
        super().__init__(args=args)
        embed_dim = args.encoder_embed_dim
        self.language_head = nn.Linear(embed_dim, embed_dim, bias=False)
        self.vision_head = nn.Linear(embed_dim, embed_dim, bias=False)
        self.language_head.apply(self._init_weights)
        self.vision_head.apply(self._init_weights)

    def forward(
        self,
        image: torch.Tensor | None = None,
        text_description: torch.Tensor | None = None,
        padding_mask: torch.Tensor | None = None,
    ) -> tuple[Any, Any]:
        vision_cls = None
        if image is not None:
            outputs = self.beit3(textual_tokens=None, visual_tokens=image, text_padding_position=None)
            x = outputs["encoder_out"]
            vision_cls = F.normalize(self.vision_head(x[:, 0, :]), dim=-1)

        language_cls = None
        if text_description is not None:
            outputs = self.beit3(
                textual_tokens=text_description, visual_tokens=None, text_padding_position=padding_mask
            )
            x = outputs["encoder_out"]
            language_cls = F.normalize(self.language_head(x[:, 0, :]), dim=-1)

        return vision_cls, language_cls


def beit3_large_patch16_384_retrieval() -> BEiT3ForRetrieval:
    args = get_large_config(img_size=384)
    return BEiT3ForRetrieval(args)
