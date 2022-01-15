import os
import sys
import logging
from prettytable import PrettyTable as pt
from functools import reduce
from operator import mul

import numpy as np
import torch

def get_tensor(data, dtype=None, requires_grad=False, use_cuda=True):
    use_cuda = os.environ.get('CUDA_VISIBLE_DEVICES', False) and use_cuda # NOTE only use cuda when it's not overriden and there is a device available

    # If data is a tensor already, move to gpu if use_cuda
    if isinstance(data, torch.Tensor):
        if use_cuda:
            return data.cuda()
        return data

    if dtype is None: # NOTE infer dtype
        dtype = 'f'
        if isinstance(data, np.ndarray) and issubclass(data.dtype.type, np.integer):
            dtype = 'l'

    # NOTE directly declare data. I believe it's faster on cuda, although I'm not entirely sure
    requires_grad = requires_grad and dtype == 'f'
    assert dtype in ['f', 'l']
    if use_cuda:
        module = getattr(torch, 'cuda')
    else:
        module = torch
    if dtype == 'f':
        cls = getattr(module, 'FloatTensor')
        dtype = 'float32'
    elif dtype == 'l':
        cls = getattr(module, 'LongTensor')
        dtype = 'int64'
    ret = cls(np.asarray(data, dtype=dtype))
    ret.requires_grad = requires_grad
    return ret

def get_zeros(*shape, **kwargs):
    if len(shape) == 1 and isinstance(shape[0], torch.Size): # NOTE deal with 1D tensor whose shape cannot be unpacked
        shape = list(shape[0])
    return get_tensor(np.zeros(shape), **kwargs)

def get_eye(n):
    return get_tensor(np.eye(n))

def counter(iterable, *args, max_size=0, interval=1000, **kwargs):
    total = 0
    for i, item in enumerate(iterable, *args, **kwargs):
        yield item
        total += 1
        if total % interval == 0:
            logging.debug(f'{total}')
            sys.stdout.flush()
        if max_size and total == max_size:
            logging.info(f'Reached max size')
            break
    logging.debug(f'Finished enumeration of size {total}')

def freeze(mod):
    for p in mod.parameters():
        p.requires_grad = False
    for m in mod.children():
        freeze(m)

def sort_all(anchor, *others):
    '''
    Sort everything (``anchor`` and ``others``) in this based on the lengths of ``anchor``. 
    '''
    # Check everything is an numpy array.
    for a in (anchor, ) + others:
        assert isinstance(a, np.ndarray)
    #  Check everything has the same length in the first dimension.
    l = len(anchor)
    for o in others:
        assert len(o) == l
    # Sort by length.
    lens = np.asarray([len(x) for x in anchor], dtype='int64')
    inds = np.argsort(lens)[::-1]
    # Return everything after sorting.
    return [lens[inds]] + [anchor[inds]] + [o[inds] for o in others]

def pprint_cols(data, num_cols=4):
    t = pt()
    num_rows = len(data) // num_cols + (len(data) % num_cols > 0)
    for col in range(num_cols - 1):
        t.add_column(f'Column:{col+1}', data[col * num_rows: (col + 1) * num_rows])
    t.add_column(f'Column:{num_cols}', data[(num_cols - 1) * num_rows:] + [''] * ((num_rows - len(data) % num_rows) % num_rows))
    t.align = 'l'
    print(t)

def check(t):
    if (torch.isnan(t).any() | torch.isinf(t).any()).item():
        breakpoint()

def canonicalize(shape, dim):
    if dim < 0:
        return len(shape) + dim 
    else:
        return dim

def divide(tensor, dim, div_shape):
    prev_shape = tensor.shape
    dim = canonicalize(prev_shape, dim)
    if -1 not in div_shape:
        total = reduce(mul, div_shape, 1)
        assert total == prev_shape[dim]
    new_shape = prev_shape[:dim] + tuple(div_shape) + prev_shape[dim + 1:]
    return tensor.view(*new_shape)

def merge(tensor, dims):
    prev_shape = tensor.shape
    dims = [canonicalize(prev_shape, dim) for dim in dims]
    for a, b in zip(dims[:-1], dims[1:]):
        assert b == a + 1
    total = reduce(mul, [prev_shape[d] for d in dims], 1)
    new_shape = prev_shape[:dims[0]] + (total, ) + prev_shape[dims[-1] + 1:]
    return tensor.view(*new_shape)
