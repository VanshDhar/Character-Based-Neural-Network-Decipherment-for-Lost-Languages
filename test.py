'''
Modififed TestCase to handle matrices.
'''
import logging

import unittest
import unittest.mock
import functools

import numpy as np
import torch

from .cache import set_cache
from .config import set_singleton

patch = functools.partial(unittest.mock.patch, autospec=True)
Mock = unittest.mock.MagicMock

def untested(func):

    def decorated(*args, **kwargs):
        logging.warning(f'This function {func.__name__} is untested.')
        return func(*args, **kwargs)

    return decorated

class TestCase(unittest.TestCase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        set_cache(False)
        set_singleton(False)

    def assertMatrixShapeEqual(self, m1, m2):
        self.assertTupleEqual(m1.shape, m2.shape)

    def assertHasShape(self, m, s):
        self.assertTupleEqual(m.shape, s)

    def assertMatrixEqual(self, m1, m2):
        self.assertMatrixShapeEqual(m1, m2)
        if torch.is_tensor(m1):
            m1 = m1.cpu().numpy()
        if torch.is_tensor(m2):
            m2 = m2.cpu().numpy()
        np.testing.assert_array_almost_equal(m1, m2)

    def assertProbs(self, probs):
        self.assertMatrixEqual(probs.sum(dim=-1).detach(), torch.ones(*probs.shape[:-1]))

