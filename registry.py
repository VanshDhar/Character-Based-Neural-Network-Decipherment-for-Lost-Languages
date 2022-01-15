from dataclasses import dataclass, make_dataclass

_REGS = dict()


def create_registry(name):
    assert name not in _REGS
    reg = Registry()
    _REGS[name] = reg
    return reg


class Registry(dict):

    def register(self, *args, **kwargs):
        if isinstance(args[0], str):
            cls = make_dataclass(*args, **kwargs)
            cls_name = args[0]
        else:
            cls = args[0]
            cls_name = cls.__name__
            assert cls_name not in self
            cls = dataclass(cls)
        self[cls_name] = cls
        return cls
