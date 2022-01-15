import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from pprint import pformat

from pytrie import SortedStringTrie

from .argument import (Argument, UnparsedArgument, UnparsedConfigArgument,
                       canonicalize)
from .property import add_properties, has_properties, set_properties


class DuplicateError(Exception):
    pass


class MultipleMatchError(Exception):
    pass


class KeywordError(Exception):
    pass


class ParsedError(Exception):
    pass


class NArgsError(Exception):
    pass


def get_log_dir(config, msg):
    while True:
        now = datetime.now()
        date = now.strftime("%m-%d")
        timestamp = now.strftime("%H%M%S")
        name = list()
        if config:
            name.append(config)
        if msg:
            name.append(msg)
        name.append(timestamp)
        name = '-'.join(name)
        log_dir = 'log\\%s\\%s' % (date, name)

        try:
            os.makedirs(log_dir)
            break
        except OSError:
            time.sleep(1)
            pass
    return log_dir


def handle_error(error):
    global _TEST
    if not _TEST:
        raise error


_DEFAULT_NODE = '_root'
_NODES = dict()
@has_properties('command_name')
class _ParserNode:
    '''
    Each node is (sub)command.
    '''
    _unsafe = False

    def __init__(self, command_name):
        assert command_name not in _NODES
        _NODES[command_name] = self
        self._args = SortedStringTrie()
        self._arg_views = SortedStringTrie()  # This stores argument views for booleans.
        self._registry = None
        self._kwds = {'--unsafe', '-u', '--help', '-h', '--config', '-cfg', '--log_dir', '-ld', '--msg', '-m'}
        self._parsed = False
        self._cli_unparsed = None
        self.add_argument('--unsafe', '-u', dtype=bool, force=True)
        self.add_argument('--msg', '-m', dtype=str, force=True)

    def __repr__(self):
        return self.command_name

    def add_cfg_registry(self, registry):
        self._registry = registry
        self.add_argument('--config', '-cfg', dtype=str, default='', force=True)

    def _check_keywords(self, name):
        # Raise error if keywords are used.
        if name in self._kwds:
            raise KeywordError(f'Keyword {name} cannot be used here')

    def add_argument(self, full_name, short_name=None, default=None, dtype=None, nargs=None, help='', force=False):
        if self._parsed and not _ParserNode._unsafe:
            handle_error(ParsedError('Already parsed.'))

        unsafe = self._parsed and _ParserNode._unsafe

        if not force:
            self._check_keywords(full_name)
            self._check_keywords(short_name)

        arg = Argument(full_name, short_name=short_name, default=default,
                       dtype=dtype, nargs=nargs, unsafe=unsafe, help=help)
        if full_name in self._args:
            handle_error(DuplicateError(f'Full name {full_name} has already been defined.'))
        if short_name and short_name in self._args:
            handle_error(DuplicateError(f'Short name {short_name} has already been defined.'))

        self._args[full_name] = arg
        if short_name:
            self._args[short_name] = arg
        # For bool arguments, we need multiple views of the same underlying argument.
        if dtype is bool:
            pos_name = full_name
            neg_name = f'--no_{full_name[2:]}'
            self._arg_views[pos_name] = arg.view(pos_name, True)
            self._arg_views[neg_name] = arg.view(neg_name, False)
            if short_name:
                pos_name = short_name
                neg_name = f'-no_{short_name[1:]}'
                self._arg_views[pos_name] = arg.view(pos_name, True)
                self._arg_views[neg_name] = arg.view(neg_name, False)

        if unsafe:
            self._parse_one_arg(full_name)
        return arg

    def help(self):
        print('Usage:')
        for k, a in self._args.items():
            print(' ' * 9, a)
        sys.exit(0)

    def get_argument(self, name, view_ok=True):
        name = canonicalize(name)
        # Always go for views first.
        # TODO Greedy decoding might result in conflict for arguments that are added after parse_args. Need to recheck the parsed?
        a = None
        if view_ok:
            try:
                a = self._get_argument_from_trie(name, self._arg_views)
            except NameError:
                pass
        if a is None:
            a = self._get_argument_from_trie(name, self._args)
        else:
            # Need to check that there isn't another match in self._args.
            try:
                a_normal = self._get_argument_from_trie(name, self._args)
            except NameError:
                a_normal = None
            if a_normal is not None and a_normal != a:
                raise MultipleMatchError(f'Found multiple matches for "{name}".')
        return a

    def set_argument(self, name, value):
        logging.warning(f'Setting {value} for argument {name}. This would change arguments globally')
        a = self.get_argument(name)
        a.value = value

    def _get_argument_from_trie(self, name, trie):
        # Try exact match first.
        try:
            a = trie[name]
            return a
        except KeyError:
            pass
        # Try fuzzy match.
        a = trie.values(prefix=name)
        if len(a) > 1:
            raise MultipleMatchError(f'Found multiple matches for "{name}".')
        elif len(a) == 0:
            if _ParserNode._unsafe:
                return None
            else:
                raise NameError(f'Name {name} not found.')
        a = a[0]
        return a

    def _update_arg(self, arg, un_arg):
        """Update arg using un_arg, always taking the last un_arg if multiple un_arg's are mapped to the same arg.
        Delete the un_arg afterwards.

        Args:
            arg ([type]): [description]
            un_arg ([type]): [description]
        """
        arg.update(un_arg)
        del self._cli_unparsed[un_arg.name]

    def _parse_one_cli_arg(self, un_arg):
        """Parse one CLI argument.

        Args:
            un_arg (UnparsedArgument): unparsed argument.
        """
        a = self.get_argument(un_arg.name)
        if a is None:
            return None
        if not self._check_nargs(a, un_arg.value):
            raise NArgsError(f'nargs not matched for "{a.name}" from "{un_arg.value}".')
        self._update_arg(a, un_arg)
        return a

    def _parse_one_arg(self, name):
        """Parse one declared argument.

        Args:
            name (str): the name of the declared argument. Fuzzy match is allowed.

        Returns:
            None or Argument: if an argument is updated, return that argument, otherwise return None.
        """
        arg = self.get_argument(name)
        if arg is None:
            return None

        prefixes = list()
        if arg.is_view():
            for view in arg.views:
                prefixes.append(view.name)
        else:
            prefixes.append(arg.full_name)
            if arg.short_name:
                prefixes.append(arg.short_name)
        items = list()
        for p in prefixes:
            items += list(self._cli_unparsed.iter_prefix_items(p))

        if len(items) == 0:
            return None

        for k, un_arg in items:
            double_check = self.get_argument(un_arg.name)
            assert double_check == arg, f'{double_check} : {arg}'
            # NOTE Use double_check here since this is the view that matches the un_arg.
            self._update_arg(double_check, un_arg)
        return arg

    def _check_nargs(self, arg, value):
        if arg.nargs == 0:
            return value is None
        elif arg.nargs == 1:
            return value is not None and not isinstance(value, tuple)
        elif arg.nargs == '+':
            return (isinstance(value, tuple) and len(value) > 0) or not isinstance(value, tuple)
        else:
            return isinstance(value, tuple) and len(value) == arg.nargs

    def _parse_cfg_arg(self, name, value):
        a = self.get_argument(name)
        if a is not None:
            a.value = value
        else:
            # If it is not a argument right now, add it later.
            name = f'--{name}'
            unparsed_a = UnparsedConfigArgument(name, value)  # NOTE Full name in cfg files.
            self._cli_unparsed[name] = unparsed_a

    def parse_args(self):
        """
        There are three ways of parsing args.
        1. Provide the declared argument (and its full name as the key) and find matching CLI arguments (unparsed). This is handled by ``_parse_one_arg`` function.
        2. Provide the CLI arguments, and find matching declared arguments. This is handled by ``_parse_one_cli_arg`` function.
        3. Read from config file. Handled by ``_parse_cfg_arg``.
        The second one is more natural, and we can easily go from left to right to make sure every CLI argument is handled.
        However, the first one is needed in unsafe mode, where a newly declared argument should be resolved.
        """
        if self._parsed:
            handle_error(ParsedError('Already parsed.'))

        argv = sys.argv[1:]
        self._cli_unparsed = SortedStringTrie()
        i = 0
        while i < len(argv):
            name = argv[i]
            value = tuple()
            j = i + 1
            while j < len(argv) and not argv[j].startswith('-'):
                value += (argv[j], )
                j += 1
            # Light processing of the value tuple.
            if len(value) == 0:
                value = None
            elif len(value) == 1:
                value = value[0]
            # Add a new cli argument.
            unparsed_a = UnparsedArgument(name, value)
            self._cli_unparsed[name] = unparsed_a
            i = j

        # Deal with help.
        if '--help' in argv or '-h' in argv:
            self.help()

        # Switch on unsafe mode (arguments can be created ad-hoc).
        if any([self._parse_one_arg('--unsafe'), self._parse_one_arg('-u')]):
            _ParserNode._unsafe = True
            logging.warning('Unsafe argument mode switched on.')

        # Use args in the cfg file as defaults.
        if self._registry is not None:
            a_cfg = self._parse_one_arg('--config')
            config = a_cfg.value
            cfg_cls = self._registry[config]
            cfg = cfg_cls()
            default_args = vars(cfg)
            for name, v in default_args.items():
                self._parse_cfg_arg(name, v)
        else:
            config = ''

        # Use CLI args to override all.
        for un_arg in self._cli_unparsed.values():
            self._parse_one_cli_arg(un_arg)

        # Get log dir.
        a = self.add_argument('--log_dir', '-ld', dtype=str, force=True)

        def try_get_value(name):
            try:
                return self.get_argument(name).value
            except (AttributeError, NameError):
                return None
        a.value = get_log_dir(try_get_value('config'), try_get_value('msg'))

        self._parsed = True
        return self._args


def _get_node(node):
    global _DEFAULT_NODE
    node = node or _DEFAULT_NODE
    if node not in _NODES:
        _NODES[node] = _ParserNode(node)
    return _NODES[node]


def set_default_parser(name):
    global _DEFAULT_NODE
    _DEFAULT_NODE = name


def add_argument(full_name, short_name=None, default=None, dtype=None, node=None, nargs=None, help=''):
    node = _get_node(node)
    a = node.add_argument(full_name, short_name=short_name, default=default, dtype=dtype, nargs=nargs, help=help)
    return a.value


def get_argument(name, node=None):
    node = _get_node(node)
    return node.get_argument(name, view_ok=False).value  # NOTE This public API should not allow views.


def set_argument(name, value, node=None):
    node = _get_node(node)
    node.set_argument(name, value)


def clear():
    """Clear all parser data."""
    global _NODES
    _NODES = dict()
    _ParserNode._unsafe = False


_TEST = False


def test_mode(flag=True):
    global _TEST
    _TEST = flag


def parse_args(node=None):
    node = _get_node(node)
    args = node.parse_args()
    return {a.name: a.value for k, a in sorted(args.items())}


def add_cfg_registry(registry, node=None):
    node = _get_node(node)
    node.add_cfg_registry(registry)


def use_arguments_as_properties(*names):
    def decorator(cls):
        cls = add_properties(*names)(cls)

        old_init = cls.__init__

        def new_init(self, *args, **kwargs):
            values = {name: get_argument(name) for name in names}
            self = set_properties(*names, **values)(self)
            old_init(self, *args, **kwargs)

        cls.__init__ = new_init
        return cls
    return decorator
