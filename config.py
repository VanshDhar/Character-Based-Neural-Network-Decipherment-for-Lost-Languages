import logging
import inspect
from importlib import import_module
from importlib import resources

USE_SINGLETON = True
def _make_singleton_metaclass_with_registry(registry):
    
    class _Singleton(type):
        '''
        A Singleton metaclass with automatic registration of classes.
        '''
        _instances = {}
        def __call__(cls, *args, **kwargs):
            if USE_SINGLETON:
                if cls not in cls._instances:
                    cls._instances[cls] = super().__call__(*args, **kwargs)
                return cls._instances[cls]
            else:
                return super().__call__(*args, **kwargs)

        def __new__(cls, clsname, bases, attrs):
            newclass = super().__new__(cls, clsname, bases, attrs)
            assert clsname not in registry
            if not clsname.startswith('_'):
                registry[clsname] = newclass
            return newclass
    
    return _Singleton

def make_config_class():
    '''
    Make an inheritable class which is itself based on a metaclass defined above.
    '''
    registry = dict()
    _Singleton = _make_singleton_metaclass_with_registry(registry)
    class _Config(metaclass=_Singleton):
    
        @classmethod
        def get(self, name):
            try:
                return registry[name]
            except Exception as e:
                raise e

    return _Config

def set_singleton(flag):
    assert flag in [True, False]
    global USE_SINGLETON
    USE_SINGLETON = flag

def has_params(params_cls):
    '''
    This hooks ``params_cls`` with any class, and instantiate a params obj for that class.
    It works by replacing the old __new__ method with a new one.
    '''
    
    def wrapper(cls):
        
        old_new = cls.__new__
        def new_new(cls, *args, **kwargs):
            params_kwargs = {k: kwargs[k] for k in params_cls.__dataclass_fields__}
            params = params_cls(**params_kwargs)
            try:
                obj = old_new(cls, *args, **kwargs)
            except TypeError:
                obj = old_new(cls)
            obj.params = params
            return obj
        
        cls.__new__ = new_new
        return cls
    
    return wrapper
