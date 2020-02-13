from typing import Sized, Tuple, Iterator
import itertools
from torch.utils.data import Sampler

__all__ = [
    "InfiniteCycleBatchSampler",
    "FiniteCycleBatchSampler",
]


class InfiniteCycleBatchSampler(Sampler):
    def __init__(self, data_source: Sized, batch_size: int = 1):
        super().__init__(data_source)
        self.data_source = data_source
        self.batch_size = batch_size

    def __iter__(self) -> Iterator[Tuple[int, ...]]:
        def nextn(iterator, n):
            for _ in range(n):
                yield next(iterator)

        iterator = itertools.cycle(range(len(self.data_source)))
        while True:
            yield tuple(nextn(iterator, self.batch_size))

    def __len__(self) -> int:
        return -1


class FiniteCycleBatchSampler(InfiniteCycleBatchSampler):
    def __init__(self, data_source: Sized, num_batches: int, batch_size: int = 1):
        super().__init__(data_source, batch_size=batch_size)
        self.num_batches = num_batches

    def __iter__(self) -> Iterator[Tuple[int, ...]]:
        iterator = super().__iter__()
        for _ in range(self.num_batches):
            yield next(iterator)

    def __len__(self) -> int:
        return self.num_batches