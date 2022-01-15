"""
Options or arguments are all referred to as arguments in this library. After all, options are just optinal arguments.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Tuple

from .property import has_properties


class FormatError(Exception):
    pass


def _check_format(name):
    if name.startswith('--') and not name.startswith('---'):
        return 'full'
    if name.startswith('-') and not name.startswith('--'):
        return 'short'
    if not name.startswith('-'):
        return 'plain'
    raise FormatError(f'Unrecognized format for name {name}')


def canonicalize(name):
    fmt = _check_format(name)
    if fmt == 'plain':
        return f'--{name}'
    else:
        return name


class Source(Enum):
    CONFIG = 0
    CLI = 1


@dataclass(order=True, frozen=True)
class Index:
    """Store the index and source of an unparsed argument (from CLI or config files)."""
    source: Source
    idx: int


@has_properties('value', 'name')
class UnparsedArgument:

    _IDX = 0
    _SOURCE = Source.CLI

    def __init__(self, name, value):
        if _check_format(name) == 'plain':
            raise Exception('Should not have come here. Something wrong with the parser.')
        self._value = value
        cls = self.__class__
        self._idx = Index(cls._SOURCE, cls._IDX)
        cls._IDX += 1

    @property
    def idx(self):
        return self._idx

    def __repr__(self):
        return f'UnparsedArgument({self.name})'

    def __str__(self):
        return f'{self.name}: {self.value}'


class UnparsedConfigArgument(UnparsedArgument):
    """This is the class to represent unparsed argument in config files."""
    _IDX = 0
    _SOURCE = Source.CONFIG

    def __repr__(self):
        return f'UnparsedConfigArgument({self.name})'


@has_properties('full_name', 'short_name', 'default', 'dtype', 'help', 'nargs', 'unsafe')
class Argument:

    def __init__(self, full_name, short_name=None, default=None, dtype=None, nargs=None, unsafe=False, help=''):
        """Construct an Argument object.

        Args:
            full_name (str): full name of this argument.
            short_name (str, optional): short name for this argument. Defaults to None.
        """
        # Check leading hyphens.
        if _check_format(full_name) != 'full':
            raise FormatError(f'Format wrong for full name {full_name}.')
        if short_name is not None and _check_format(short_name) != 'short':
            raise FormatError(f'Format wrong for short name {short_name}.')
        # Check boolean format.
        if dtype is bool:
            if full_name.startswith('--no_'):
                raise FormatError(f'Format wrong for full name {full_name}.')
            if short_name is not None and short_name.startswith('-no_'):
                raise FormatError(f'Format wrong for short name {short_name}.')

        self._name = full_name[2:]

        # Keep track of the last idx of an unparsed argument that this argument is parsed from.
        self.last_idx = None

        nargs = nargs or 1
        assert isinstance(nargs, int) or nargs == '+'
        if dtype is bool:
            nargs = 0
        self._nargs = nargs

        # NOTE value should be set after everything is done.
        self.value = default
        if self.default is not None and dtype is None:
            # Use the type of the default.
            self._dtype = type(self.default)

        # Store all views.
        self._views = list()

    @property
    def name(self):
        return self._name

    @property
    def value(self):
        return self._value

    def is_view(self):
        return False

    def reset(self):
        self.value = self.default

    def update(self, un_arg):
        if self.last_idx is None or self.last_idx < un_arg.idx:
            if self.is_view():
                self.use_this_view()
            else:
                self.value = un_arg.value
            self.last_idx = un_arg.idx

    @value.setter
    def value(self, new_value):
        if new_value is not None:
            if self.nargs == '+':
                if not isinstance(new_value, tuple):
                    new_value = (new_value, )
            elif self.nargs == 1:
                if isinstance(new_value, tuple):
                    raise FormatError(f'nargs should not be a tuple with {new_value} for {self!r}.')
            elif self.nargs == 0:
                if not isinstance(new_value, bool):
                    raise ValueError(f'Can only assign True/False to bool argument.')
            else:
                if not isinstance(new_value, tuple) or len(new_value) != self.nargs:
                    raise FormatError(f'nargs mismatch with {new_value} for {self!r}.')

        if self._dtype and new_value is not None:
            if isinstance(new_value, tuple):
                new_value = tuple(self._dtype(v) for v in new_value)
            else:
                new_value = self._dtype(new_value)
        self._value = new_value

    def __str__(self):
        out = f'{self.full_name}'
        if self.short_name:
            out += f' {self.short_name}'
        if self.dtype:
            out += f' ({self.dtype.__name__})'
        if self.help:
            out += f': {self.help}'
        if self.default is not None:
            out += f' [DEFAULT = {self.default}]'
        return out

    def __repr__(self):
        return f'Argument({self.name})'

    def view(self, name, value):
        value = self.dtype(value)
        ret = _ArgumentView(self, name, value)
        self._views.append(ret)
        return ret

    def __eq__(self, other):
        if other.is_view():
            return self is other._arg
        else:
            return self is other

    @property
    def views(self):
        return self._views


@has_properties('name')
class _ArgumentView(Argument):

    def __init__(self, arg, name, value):
        self._arg = arg
        self._value = value

    def __getattribute__(self, key):
        try:
            return super().__getattribute__(key)
        except AttributeError:
            arg = super().__getattribute__('_arg')
            return getattr(arg, key)

    def __setattr__(self, key, value):
        if key in ['_arg', '_value', '_name']:  # These are the only true attributes for this view.
            super().__setattr__(key, value)
        else:
            arg = self._arg
            arg.__setattr__(key, value)

    @property
    def value(self):
        return self._arg.value

    @value.setter
    def value(self, new_value):
        self._arg.value = new_value

    def use_this_view(self):
        self.value = self._value

    def is_view(self):
        return True

    def __eq__(self, other):
        if other.is_view():
            return self._arg is other._arg
        else:
            return self._arg is other
