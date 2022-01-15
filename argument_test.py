from unittest import TestCase

from .argument import Argument, FormatError


class TestArgument(TestCase):

    def test_str(self):
        a = Argument('--x')
        self.assertEqual(str(a), '--x')
        a = Argument('--x', '-x')
        self.assertEqual(str(a), '--x -x')
        a = Argument('--x', '-x', default=1, dtype=int)
        self.assertEqual(str(a), '--x -x (int) [DEFAULT = 1]')
        a = Argument('--x', '-x', default=1, dtype=int, help='test')
        self.assertEqual(str(a), '--x -x (int): test [DEFAULT = 1]')

    def test_format(self):
        with self.assertRaises(FormatError):
            Argument('-option1')
        with self.assertRaises(FormatError):
            Argument('--option1', '--o1')
        with self.assertRaises(FormatError):
            Argument('option1')
        with self.assertRaises(FormatError):
            Argument('--option1', 'o1')

    def test_bool_format(self):
        a = Argument('--use_default', default=True, dtype=bool)
        with self.assertRaises(FormatError):
            Argument('--no_use_default', default=True, dtype=bool)
