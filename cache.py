from functools import wraps
from inspect import signature
from collections import defaultdict, namedtuple
from collections.abc import Callable, Hashable

from .map import Map

_CachedItem = namedtuple('_CachedItem', ['persist', 'value'])
_CACHE = dict()
_USE_CACHE = True

def cache(full=True, persist=False):
    global _USE_CACHE

    def descriptor(func):
        func_sig = signature(func)
        def decorator(self, *args, **kwargs):
            if not _USE_CACHE:
                return func(self, *args, **kwargs)

            bound = func_sig.bind(self, *args, **kwargs)
            bound.apply_defaults()
            items = [(k, v) for k, v in bound.arguments.items() if not isinstance(v, dict)]
            arg_key = frozenset(items)
            if full:
                key = (id(self), func.__name__, arg_key)
            else:
                key = (id(self), func.__name__)
            if key in _CACHE:
                return _CACHE[key].value
            else:
                ret = func(self, *args, **kwargs)
                _CACHE[key] = _CachedItem(persist, ret)
                return ret
            
        return decorator
    
    return descriptor

def clear_cache():
	global _CACHE
	# First pass to get keys to be removed.
	to_remove = list()
	for k, item in _CACHE.items():
		if not item.persist:
			to_remove.append(k)
	# Now remove them.
	for k in to_remove:
		del _CACHE[k]

def set_cache(flag):
	global _USE_CACHE
	assert flag in [True, False]
	_USE_CACHE = flag

####################################### structured cache #################################

class _StructuredCache:
	'''
	Assuming that the return is a Map object, this cache will selectively keep some 
	attributes while removing the rest. 
	You can also dynamically select what to cache, useful when you want to perform analysis.
	'''
	
	def __init__(self):
		# What should be kept.
		self._to_keep = dict()
		# What should be cached.
		self._to_cache = defaultdict(set)
		# What is cached. Note that each instance method has its own cache, keyed by the object's unique id. 
		self.clear_cache()
		# The mapping from the object id to the object.
		self._id2obj = dict()
	
	def keep(self, name, ret):
		'''Only keep what should be kept.'''
		if self._to_keep[name] is None:
			return ret
		else:
			return Map(**{k: ret[k] for k in self._to_keep[name] if k in ret})
	
	def __contains__(self, key):
		return key in self._to_keep
	
	def register_keep(self, name, *to_keep):
		'''Record what to keep for each function.'''
		assert name not in self
		if len(to_keep) == 0:
			self._to_keep[name] = None # NOTE None means keeping everthing. 
		else:
			self._to_keep[name] = set(to_keep)
	
	def register_cache(self, name, *keys):
		'''Register cache for all instances of the same registered function with ``name``.'''
		self._to_cache[name].update(keys)
	
	def cache(self, name, obj, ret):
		id_ = id(obj)
		if id_ not in self._id2obj:
			self._id2obj[id_] = obj
		else:
			assert self._id2obj[id_] is obj # Make sure it's the same object.
		for k in self._to_cache[name]:
			assert k not in self._cache[name][id_]
			self._cache[name][id_][k] = ret[k]
	
	def get_cache(self, name, *keys):
		'''Get all caches generated from the same function.'''
		ret = list()
		for id_ in self._cache[name]:
			obj = self._id2obj[id_]
			cache = self._cache[name][id_]
			ret.append((obj, {k: cache[k] for k in keys}))
		return ret
	
	def clear_cache(self):
		self._cache = defaultdict(lambda: defaultdict(defaultdict))

_SC = _StructuredCache()
def sc(name, *to_keep):
	global _SC
	
	def descriptor(func):

		@wraps(func)
		def decorator(self, *args, **kwargs):
			ret = func(self, *args, **kwargs)
			assert isinstance(ret, Map)
			_SC.cache(name, self, ret)
			return _SC.keep(name, ret)

		return decorator
	
	_SC.register_keep(name, *to_keep)
	return descriptor

def sc_clear_cache():
	global _SC
	_SC.clear_cache()

def sc_register_cache(name, *keys):
	global _SC
	_SC.register_cache(name, *keys)
	
def sc_get_cache(name, *keys):
	global _SC
	return _SC.get_cache(name, *keys)
