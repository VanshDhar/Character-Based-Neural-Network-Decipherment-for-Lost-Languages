from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from datetime import datetime
import os
import sys
import random

import numpy as np
import torch

from .map import Map

def get_log_dir(args):
    while True:
        now = datetime.now()
        date = now.strftime("%m-%d")
        timestamp = now.strftime("%H:%M:%S")
        msg = args.msg
        msg = args.config + '-' * (msg != '') + msg
        log_dir = 'log/%s/%s-%s' %(date, msg, timestamp)

        try:
            os.makedirs(log_dir)
            break
        except OSError:
            pass
    return log_dir

class _CommandNode(object):

    def __init__(self, name, cmd_name, parent=None):
        self.parent = parent
        self.name = name
        self.cmd_name = cmd_name
        self.children = list()
        self.argument_info = list()
        self.bool_flags_info = list()

    def add_command(self, command):
        self.children.append(command)

    def add_argument(self, *args, **kwargs):
        info = Map(args=args, kwargs=kwargs)
        self.argument_info.append(info)

    def add_bool_flags(self, on_name, default=False):
        info = Map(on_name=on_name, default=default)
        self.bool_flags_info.append(info)

    def is_leaf(self):
        return not self.children

    def __repr__(self):
        return self.cmd_name

class CommandException(Exception):
    pass

class ArgParser(object):
    '''
    A customized class for handling CLI. It makes heavy use of argparse, but the main class ArgumentParser is initialized lazily.
    It works by building nested commands as a tree, and associate each leaf node with a combination of node-specific options,
    and options inherited from its parent.
    '''

    def __init__(self, parent=None, root=None, cfg_cls=None):
        if parent is None:
            name = sys.argv[0]
            self.root_command = _CommandNode(name, '')
            self.name2command = {name: self.root_command}
        else:
            self.name2command = parent.name2command
            self.root_command = root
        self.cfg_cls = cfg_cls

    def add_command(self, name):
        '''
        Return a ArgParser instance with different root node every time a new (sub)command is added.
        '''
        new_name = self.root_command.name + '=>' + name
        command = _CommandNode(new_name, name, parent=self.root_command)
        self.name2command[new_name] = command
        self.root_command.add_command(command)
        return ArgParser(parent=self, root=command)

    def add_argument(self, *args, **kwargs):
        self.root_command.add_argument(*args, **kwargs)

    def add_bool_flags(self, on_name, default=False):
        self.root_command.add_bool_flags(on_name, default=default)

    def parse_args(self, to_log=True):
        # get config args first
        _base_parser = ArgumentParser(formatter_class=ArgumentDefaultsHelpFormatter, add_help=False)
        _base_parser.add_argument('--config', '-cfg', type=str, help='Configure file')
        config_arg, _remaining_args = _base_parser.parse_known_args()
        defaults = {'config': config_arg.config}
        if config_arg.config:
            assert self.cfg_cls is not None
            config_cls = self.cfg_cls.get(config_arg.config)
            cfg = config_cls()
            defaults.update(vars(cfg))

        # first parse the subcommand structure
        command = self.root_command
        chain = [command]
        i = 1 # NOTE the first argument is sys.argv is also the python script
        try:
            while not command.is_leaf():
                name = command.name + '=>' + sys.argv[i]
                command = self.name2command[name]
                chain.append(command)
                i += 1
        except (KeyError, IndexError):
            raise CommandException('This is not a leaf command. Possible subcommands are \n%r' %command.children)

        # now construct an ArgumentParser
        info = list()
        bool_info = list()
        for command in chain:
            info.extend(command.argument_info)
            bool_info.extend(command.bool_flags_info)
        parser = ArgumentParser(formatter_class=ArgumentDefaultsHelpFormatter, parents=[_base_parser])
        for node_info in info:
            parser.add_argument(*node_info.args, **node_info.kwargs)
        for node_info in bool_info:
            on_name = node_info.on_name
            group = parser.add_mutually_exclusive_group(required=False)
            group.add_argument('--' + on_name, dest=on_name, action='store_true')
            group.add_argument('--no_' + on_name, dest=on_name, action='store_false')
            parser.set_defaults(**{on_name: node_info.default})
        parser.set_defaults(**defaults)
        args = parser.parse_args(sys.argv[i:])
        args.mode = '-'.join(chain[-1].name.split('=>')[1:])
        if to_log:
            args.log_dir = get_log_dir(args)
        else:
            args.log_dir = None
        return Map(**vars(args))
        
