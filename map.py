class Map(dict):
	"""
	Abandoned the original way of doing it:
		self.__dict__ = self
	This introduces a self-reference and makes gc fail to collect garbage 
	in time. As a result, pytorch can't properly empty cache if a tensor is 
	stored in it.
	"""

	def __getattr__(self, key):
		try:
			return self[key]
		except KeyError:
			raise AttributeError

	def __setattr__(self, key, value):
		self[key] = value

	def update(self, *args, **kwargs):
		'''
		Return self.
		'''
		super(Map, self).update(*args, **kwargs)
		return self

	def apply(self, func, ignored=set()):
		for key in self:
			if key in ignored:
				continue

			if isinstance(self[key], Map):
				self[key].apply(func, ignored=ignored)
			else:
				self[key] = func(self[key])
