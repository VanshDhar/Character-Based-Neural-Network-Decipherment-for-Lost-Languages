import io
import logging
import sys
import time

import enlighten
from prettytable import PrettyTable as pt
from treelib import Tree

from arglib import has_properties

from .logger import log_pp
from .metrics import Metrics, plain

_manager = enlighten.get_manager()
_stage_names = set()

def clear_stages():
    global _manager
    global _stage_names
    _manager = enlighten.get_manager()
    _stage_names = set()

def _check_name(name):
    assert name not in _stage_names
    _stage_names.add(name)


def _reset_pbar(pbar):
    pbar.count = 0
    pbar.start = time.time()


@has_properties('name', 'num_steps', 'parent')
class _Stage:

    def __init__(self, name, num_steps=1, parent=None):
        _check_name(name)

        self._pbars = dict()
        self.substages = list()
        if self.num_steps > 1:
            self.add_pbar(name, total=self.num_steps)

    def update_pbars(self):
        for pbar in self._pbars.values():
            if pbar.total == pbar.count:
                _reset_pbar(pbar)
            pbar.update()

    def reset_pbars(self, recursive=False):
        for pbar in self._pbars.values():
            _reset_pbar(pbar)
        if recursive:
            for substage in self.substages:
                substage.reset_pbars(recursive=True)

    def add_pbar(self, name, total=None, unit='samples'):
        if name in self._pbars:
            raise NameError(f'Name {name} already exists.')
        pbar = _manager.counter(
            desc=name,
            total=total,
            unit=unit,
            leave=False)
        pbar.refresh()
        self._pbars[name] = pbar

    def add_stage(self, name, num_steps=1):
        stage = _Stage(name, num_steps=num_steps, parent=self)
        self.substages.append(stage)
        return stage

    # def adjoin_stage(self, stage):
    #     assert isinstance(stage, _Stage)
    #     self.substages.append(stage)
    #     return self

    def __str__(self):
        return f'"{self.name}"'

    def __repr__(self):
        return f'Stage(name={self.name}, num_steps={self.num_steps})'

    def load_state_dict(self, state_dict):
        missing = list()
        for name, pbar_meta in state_dict['_pbars'].items():
            try:
                pbar = self._pbars[name]
            except KeyError:
                missing.append(f'pbar:{name}')
                continue
            pbar.count = pbar_meta['count']
            pbar.refresh()
        for s1, s2 in zip(self.substages, state_dict['_stages']):
            s1.load_state_dict(s2)
        if missing:
            raise RuntimeError(f'Missing {missing}')

    def state_dict(self):
        ret = dict()
        # NOTE pbar itself cannot be serialized for some reason.
        ret['_pbars'] = {name: {'count': pbar.count} for name, pbar in self._pbars.items()}
        stage_ret = list()
        for s in self.substages:
            stage_ret.append(s.state_dict())
        ret['_stages'] = stage_ret
        return ret


@has_properties('step', 'substage_idx')
class _Node:
    """A wrapper of stage that contains step and substage_idx information."""

    def __init__(self, stage, step, substage_idx):
        self.stage = stage

    @property
    def name(self):
        return self.stage.name

    def is_last(self):
        last_step = (self.step == self.stage.num_steps - 1)
        if self.stage.substages:
            last_substage = (self.substage_idx == len(self.stage.substages) - 1)
            last = last_substage and last_step
        else:
            last = last_step
        return last

    def next_node(self):
        """Return whether next node will increment the step."""
        if self.stage.substages:
            new_substage_idx = self.substage_idx + 1
            incremented = False
            if new_substage_idx == len(self.stage.substages):
                new_substage_idx = 0
                incremented = True
            new_step = self.step + incremented
            return _Node(self.stage, new_step, new_substage_idx), incremented
        else:
            return _Node(self.stage, self.step + 1, None), True

    def __str__(self):
        return f'{self.stage}: {self.step}'

    def __repr__(self):
        return f'Node(stage={str(self.stage)}, step={self.step}, substage_idx={self.substage_idx})'


class _Path:

    def __init__(self, schedule):
        self._nodes = list()
        self._nodes_dict = dict()
        self._schedule = schedule
        self._get_first_path(self._schedule)
        self._finished = False

    def _add(self, node):
        # Check that this is a valid extension of the original path.
        if len(self._nodes) == 0:
            safe = True
        else:
            last_node = self._nodes[-1]
            safe = last_node.stage.substages[last_node.substage_idx] is node.stage
        assert safe
        # Add it.
        self._nodes.append(node)
        self._nodes_dict[node.stage.name] = node.step

    def __str__(self):
        ret = ' -> '.join([str(node) for node in self._nodes])
        return ret

    def _get_first_path(self, stage_or_node):

        def helper(stage_or_node):
            if isinstance(stage_or_node, _Stage):
                stage = stage_or_node
                if stage.substages:
                    self._add(_Node(stage, 0, 0))
                    helper(stage.substages[0])
                else:
                    self._add(_Node(stage, 0, None))  # None means there is no substage.
            else:
                assert isinstance(stage_or_node, _Node)
                node = stage_or_node
                if node.stage.substages:
                    new_node = _Node(node.stage, node.step, node.substage_idx)
                    self._add(new_node)
                    child_node = _Node(new_node.stage.substages[new_node.substage_idx], 0, 0)
                    helper(child_node)
                else:
                    self._add(node)

        helper(stage_or_node)

    @property
    def finished(self):
        return self._finished

    def next_path(self):
        """Note that this is in-place. It returns the nodes incremented."""
        # First backtrack to the first ancestor that hasn't been completed yet.
        assert not self._finished
        i = len(self._nodes)
        while i > 0:
            i -= 1
            last_node = self._nodes[i]
            if not last_node.is_last():
                break
        # Now complete it.
        if last_node.is_last():
            self._finished = True
            affected_nodes = self._nodes[1:]
        else:
            affected_nodes = self._nodes[i + 1:]  # NOTE Everything that is last will be incremented.
            self._nodes = self._nodes[:i]
            next_node, incremented = last_node.next_node()
            if incremented:
                affected_nodes.append(next_node)
            self._get_first_path(next_node)
        return affected_nodes

    @property
    def leaf_node(self):
        return self._nodes[-1]

    def get_step(self, key):
        return self._nodes_dict[key]


class _Schedule(_Stage):

    def __init__(self, name):
        super().__init__(name, num_steps=1)
        self._path = None

    def _build_path(self):
        self._path = _Path(self)

    def update(self):
        affected_nodes = self._path.next_path()
        for node in affected_nodes:
            node.stage.update_pbars()

    def as_tree(self):
        tree = Tree()  # NOTE Store the tree structure for treelib.
        tree.create_node(repr(self), id(self))

        def helper(stage):
            for substage in stage.substages:
                tree.create_node(repr(substage), id(substage), parent=id(stage))
                helper(substage)

        helper(self)

        sys.stdout = io.StringIO()
        tree.show()
        output = sys.stdout.getvalue()
        sys.stdout = sys.__stdout__
        return output

    @property
    def current_stage(self):
        return self._path.leaf_node

    @property
    def finished(self):
        return self._path.finished

    def get_step(self, key):
        return self._path.get_step(key)

    def fix_schedule(self):
        self._build_path()

    def reset(self):
        self._build_path()


class Tracker:

    def __init__(self, name):
        self.clear_best()
        self._schedule = _Schedule(name)
        self._metrics = Metrics()

    def schedule_as_tree(self):
        return self._schedule.as_tree()

    @property
    def schedule(self):
        return self._schedule

    @property
    def metrics(self):
        return self._metrics

    def reset(self):
        self._schedule.reset()

    def add_stage(self, name, num_steps=1):
        return self._schedule.add_stage(name, num_steps=num_steps)

    def clear_best(self):
        self.best_score = None
        self.best_stage = None

    def check_metrics(self, epoch):
        log_pp(self._metrics.get_table(title=f'Epoch: {epoch}'))

    def clear_metrics(self):
        self._metrics.clear()

    def update_metrics(self, metrics):
        self._metrics += metrics

    def state_dict(self):
        ret = {'_schedule': self._schedule.state_dict(), 'best_score': self.best_score,
               'best_stage': self.best_stage, '_metrics': self._metrics}
        return ret

    def load_state_dict(self, state_dict):
        self._schedule.load_state_dict(state_dict['_schedule'])
        self.best_score = state_dict['best_score']
        self.best_stage = state_dict['best_stage']
        self._metrics = state_dict['_metrics']

    def update_best(self, score, mode='min', quiet=False):
        """Update the best score and best stage.

        Args:
            score: score for the current stage
            mode (str, optional): take the maximum or the minimum as the best score. Defaults to 'min'.
            quiet (bool, optional): flag to suppress outputting the best score. Defaults to False.

        Returns:
            updated (bool): whether the best score has been updated or not
        """
        score = plain(score)
        updated = False

        def should_update():
            if score is None:
                return False
            if self.best_score is None:
                return True
            if mode == 'max' and self.best_score < score:
                return True
            if mode == 'min' and self.best_score > score:
                return True
            return False

        updated = should_update()
        if updated:
            self.best_score = score
            self.best_stage = str(self.current_stage)
        if self.best_score is not None and not quiet:
            logging.info(f'Best score is {self.best_score:.3f} at stage {self.best_stage}')
        return updated

    def update(self):
        self._schedule.update()

    @property
    def current_stage(self):
        return self._schedule.current_stage

    @property
    def finished(self):
        return self._schedule.finished

    def get(self, key):
        return self._schedule.get_step(key)

    def fix_schedule(self):
        self._schedule.fix_schedule()

    def reset_pbars(self):
        self._schedule.reset_pbars(recursive=True)
