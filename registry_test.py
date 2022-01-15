from .registry import create_registry

from unittest import TestCase


class TestRegistry(TestCase):

    def test_register(self):
        reg = create_registry('test')
        @reg.register
        class Test1:
            x: int = 1

        @reg.register
        class Test2(Test1):
            y: str = 'test'

        self.assertIs(reg['Test1'], Test1)
        self.assertIs(reg['Test2'], Test2)
