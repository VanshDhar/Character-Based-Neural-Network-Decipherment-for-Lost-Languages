import logging

from prettytable import PrettyTable as pt
import numpy as np
import torch

from .map import Map


def plain(value):
    '''Convert tensors or numpy arrays to one scalar.'''
    # Get to str, int or float first.
    if isinstance(value, torch.Tensor):
        assert value.numel() == 1
        value = value.item()
    elif isinstance(value, np.ndarray):
        assert value.size == 1
        value = value[0]
    # Format it nicely.
    if isinstance(value, (str, int)):
        value = value
    elif isinstance(value, float):
        value = float(f'{value:.3f}')
    else:
        raise NotImplementedError
    return value


class Metric:

    def __init__(self, name, value, weight, report_mean=True):
        self.name = name
        self._v = value
        self._w = weight
        self._report_mean = report_mean

    def __hash__(self):
        return hash(self.name)

    def __str__(self):
        if self.report_mean:
            return f'{plain(self._v)}/{plain(self._w)}={plain(self.mean)}'
        else:
            return f'{plain(self.total)}'

    def __repr__(self):
        return f'Metric(name={self.name}, report_mean={self.report_mean})'

    def __eq__(self, other):
        return self.name == other.name

    def __add__(self, other):
        if isinstance(other, Metric):
            assert self == other, 'Cannot add two different metrics.'
            assert self.report_mean == other.report_mean
            return Metric(self.name, self._v + other._v, self._w + other._w, report_mean=self.report_mean)
        else:
            # NOTE This is useful for sum() call.
            assert isinstance(other, (int, float)) and other == 0
            return self

    def __radd__(self, other):
        return self.__add__(other)

    def rename(self, name):
        '''This is in-place.'''
        self.name = name
        return self

    @property
    def value(self):
        return self._v

    @property
    def weight(self):
        return self._w if self.report_mean else 'N/A'

    @property
    def report_mean(self):
        return self._report_mean

    @property
    def mean(self):
        if self.report_mean:
            return self._v / self._w
        else:
            return 'N/A'

    @property
    def total(self):
        return self._v

    def clear(self):
        self._v = 0
        self._w = 0


class Metrics:

    def __init__(self, *metrics):
        # Check all of metrics are of the same type. Either all str or all Metric.
        types = set([type(m) for m in metrics])
        assert len(types) <= 1

        if len(types) == 1:
            if types.pop() is str:
                self._metrics = {k: Metric(k, 0, 0) for k in keys}
            else:
                self._metrics = {metric.name: metric for metric in metrics}
        else:
            self._metrics = dict()

    def __str__(self):
        out = '\n'.join([f'{k}: {m}' for k, m in self._metrics.items()])
        return out

    def __repr__(self):
        return f'Metrics({", ".join(self._metrics.keys())})'

    def __add__(self, other):
        if isinstance(other, Metric):
            other = Metrics(other)
        union_keys = set(self._metrics.keys()) | set(other._metrics.keys())
        metrics = list()
        for k in union_keys:
            m1 = self._metrics.get(k, 0)
            m2 = other._metrics.get(k, 0)
            metrics.append(m1 + m2)
        return Metrics(*metrics)

    def __getattr__(self, key):
        try:
            return super().__getattribute__('_metrics')[key]
        except KeyError:
            raise AttributeError(f'Cannot find this attribute {key}')

    def get_table(self, title=''):
        t = pt()
        if title:
            t.title = title
        t.field_names = 'name', 'value', 'weight', 'mean'
        for k in sorted(self._metrics.keys()):
            metric = self._metrics[k]
            t.add_row([k, plain(metric.value), plain(metric.weight), plain(metric.mean)])
        t.align = 'l'
        return t

    def clear(self):
        for m in self._metrics.values():
            m.clear()
