from collections import OrderedDict
from copy import copy
from typing import Collection, Dict, Iterator, Optional, Sequence, Tuple, Union

import torch
from torch import nn

import pystiche
from pystiche.misc import warn_deprecation

from .encoder import Encoder
from .guides import propagate_guide

__all__ = ["MultiLayerEncoder", "SingleLayerEncoder"]


class MultiLayerEncoder(pystiche.Module):
    def __init__(self, modules: Dict[str, nn.Module]) -> None:
        super().__init__(named_children=modules)
        self.registered_layers = set()
        # TODO: rename to storage
        self._cache = dict()

        # TODO: remove this?
        self.requires_grad_(False)
        self.eval()

    def children_names(self) -> Iterator[str]:
        for name, child in self.named_children():
            yield name

    def __contains__(self, name: str) -> bool:
        return name in self.children_names()

    def _verify_layer(self, layer: str) -> None:
        if layer not in self:
            raise ValueError(f"Layer {layer} is not part of the encoder.")

    def extract_deepest_layer(self, layers: Collection[str]) -> str:
        for layer in layers:
            self._verify_layer(layer)
        return sorted(set(layers), key=list(self.children_names()).index)[-1]

    def named_children_to(
        self, layer: str, include_last: bool = False
    ) -> Iterator[Tuple[str, pystiche.Module]]:
        self._verify_layer(layer)
        idx = list(self.children_names()).index(layer)
        if include_last:
            idx += 1
        return iter(tuple(self.named_children())[:idx])

    def named_children_from(
        self, layer: str, include_first: bool = True
    ) -> Iterator[Tuple[str, pystiche.Module]]:
        self._verify_layer(layer)
        idx = list(self.children_names()).index(layer)
        if not include_first:
            idx += 1
        return iter(tuple(self.named_children())[idx:])

    def forward(
        self, input: torch.Tensor, layers: Sequence[str], store=False
    ) -> Tuple[torch.Tensor, ...]:
        storage = copy(self._cache)
        input_key = pystiche.TensorKey(input)
        stored_layers = [name for name, key in storage.keys() if key == input_key]
        diff_layers = set(layers) - set(stored_layers)

        if diff_layers:
            deepest_layer = self.extract_deepest_layer(diff_layers)
            for name, module in self.named_children_to(
                deepest_layer, include_last=True
            ):
                input = storage[(name, input_key)] = module(input)

            if store:
                self._cache.update(storage)

        return tuple([storage[(name, input_key)] for name in layers])

    def extract_single_layer_encoder(self, layer: str) -> "SingleLayerEncoder":
        self._verify_layer(layer)
        self.registered_layers.add(layer)
        return SingleLayerEncoder(self, layer)

    def __getitem__(self, layer: str) -> "SingleLayerEncoder":
        warn_deprecation(
            "method",
            "MultiLayerEncoder.__getitem__",
            "0.4",
            info=(
                "To extract a single layer encoder use MultiLayerEncoder.extract_"
                "single_layer_encoder() instead."
            ),
        )
        return self.extract_single_layer_encoder(layer)

    def encode(self, input: torch.Tensor):
        if not self.registered_layers:
            return

        key = pystiche.TensorKey(input)
        keys = [(layer, key) for layer in self.registered_layers]
        encs = self(input, layers=self.registered_layers, store=True)
        self._cache = dict(zip(keys, encs))

    # TODO: rename to empty_storage
    def clear_cache(self):
        self._cache = {}

    def trim(self, layers: Optional[Collection[str]] = None):
        if layers is None:
            layers = self.registered_layers
        deepest_layer = self.extract_deepest_layer(layers)
        for name, _ in self.named_children_from(deepest_layer, include_first=False):
            del self._modules[name]

    def propagate_guide(
        self,
        guide: torch.Tensor,
        layers: Sequence[str],
        method: str = "simple",
        allow_empty=False,
    ) -> Tuple[torch.Tensor, ...]:
        guides = {}
        deepest_layer = self.extract_deepest_layer(layers)
        for name, module in self.named_children_to(deepest_layer, include_last=True):
            try:
                guide = guides[name] = propagate_guide(
                    module, guide, method=method, allow_empty=allow_empty
                )
            except RuntimeError as error:
                # TODO: customize error message to better reflect which layer causes
                #       the problem
                raise error

        return tuple([guides[name] for name in layers])


class SingleLayerEncoder(Encoder):
    def __init__(self, multi_layer_encoder: MultiLayerEncoder, layer: str):
        super().__init__()
        self.multi_layer_encoder = multi_layer_encoder
        self.layer = layer

    def forward(self, input_image: torch.Tensor) -> torch.Tensor:
        return self.multi_layer_encoder(input_image, layers=(self.layer,))[0]

    def propagate_guide(self, guide: torch.Tensor) -> torch.Tensor:
        return self.multi_layer_encoder.propagate_guide(guide, layers=(self.layer,))[0]

    def __str__(self) -> str:
        name = self.multi_layer_encoder.__class__.__name__
        properties = OrderedDict()
        properties["layer"] = self.layer
        properties.update(self.multi_layer_encoder.properties())
        named_children = ()
        return self._build_str(
            name=name, properties=properties, named_children=named_children
        )
