'''
Modified from MUSE
'''

import logging
import time
from datetime import timedelta
from functools import wraps
from inspect import signature

from colorlog import TTYColoredFormatter


# From https://stackoverflow.com/questions/2183233/how-to-add-a-custom-loglevel-to-pythons-logging-facility.
def addLoggingLevel(levelName, levelNum, methodName=None):
    """
    Comprehensively adds a new logging level to the `logging` module and the
    currently configured logging class.

    `levelName` becomes an attribute of the `logging` module with the value
    `levelNum`. `methodName` becomes a convenience method for both `logging`
    itself and the class returned by `logging.getLoggerClass()` (usually just
    `logging.Logger`). If `methodName` is not specified, `levelName.lower()` is
    used.

    To avoid accidental clobberings of existing attributes, this method will
    raise an `AttributeError` if the level name is already an attribute of the
    `logging` module or if the method name is already present

    Example
    -------
    >>> addLoggingLevel('TRACE', logging.DEBUG - 5)
    >>> logging.getLogger(__name__).setLevel("TRACE")
    >>> logging.getLogger(__name__).trace('that worked')
    >>> logging.trace('so did this')
    >>> logging.TRACE
    5

    """
    if not methodName:
        methodName = levelName.lower()

    if hasattr(logging, levelName):
        raise AttributeError('{} already defined in logging module'.format(levelName))
    if hasattr(logging, methodName):
        raise AttributeError('{} already defined in logging module'.format(methodName))
    if hasattr(logging.getLoggerClass(), methodName):
        raise AttributeError('{} already defined in logger class'.format(methodName))

    # This method was inspired by the answers to Stack Overflow post
    # http://stackoverflow.com/q/2183233/2988730, especially
    # http://stackoverflow.com/a/13638084/2988730
    def logForLevel(self, message, *args, **kwargs):
        if self.isEnabledFor(levelNum):
            self._log(levelNum, message, args, **kwargs)

    def logToRoot(message, *args, **kwargs):
        logging.log(levelNum, message, *args, **kwargs)

    logging.addLevelName(levelNum, levelName)
    setattr(logging, levelName, levelNum)
    setattr(logging.getLoggerClass(), methodName, logForLevel)
    setattr(logging, methodName, logToRoot)


addLoggingLevel('IMP', 25)


class LogFormatter(TTYColoredFormatter):

    def __init__(self, *args, **kwargs):  # , color=False):
        fmt = '%(log_color)s%(levelname)s - %(time)s - %(elapsed)s at %(filename)s:%(lineno)d - %(message)s'
        super(LogFormatter, self).__init__(
            fmt,
            log_colors={
                'DEBUG': 'white',
                'INFO': 'green',
                'IMP': 'cyan',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'red,bg_white'},
            *args,
            **kwargs)
        self.start_time = time.time()

    def format(self, record):
        # only need to set timestamps once -- all changes are stored in the record object
        if not hasattr(record, 'elapsed'):
            record.elapsed = timedelta(seconds=round(record.created - self.start_time))
            record.time = time.strftime('%x %X')
            # if self.colored:
            prefix = "%s - %s - %s at %s:%d" % (
                record.levelname,
                record.time,
                record.elapsed,
                record.filename,
                record.lineno
            )
            message = record.getMessage()
            # If a message starts with a line break, we will keep the original line break without autoindentation.
            if not message.startswith('\n'):
                message = message.replace('\n', '\n' + ' ' * (len(prefix) + 3))
            record.msg = message
            record.args = ()  # NOTE avoid evaluating the message again duing getMessage call.
        x = super(LogFormatter, self).format(record)
        return x


def create_logger(filepath=None, log_level='INFO'):
    """
    Create a logger.
    """
    # create console handler and set level to info
    console_handler = logging.StreamHandler()
    # create log formatter
    colorlog_formatter = LogFormatter(stream=console_handler.stream)
    console_handler.setLevel(getattr(logging, log_level))
    console_handler.setFormatter(colorlog_formatter)

    # create logger and set level to debug
    logger = logging.getLogger()
    logger.handlers = []
    logger.setLevel(log_level)
    logger.propagate = False
    logger.addHandler(console_handler)
    if filepath:
        # create file handler and set level to debug
        file_handler = logging.FileHandler(filepath, "a", encoding="utf-8")
        file_handler.setLevel(log_level)
        log_formatter = LogFormatter(stream=file_handler.stream)
        file_handler.setFormatter(log_formatter)
        logger.addHandler(file_handler)

    # reset logger elapsed time
    def reset_time():
        log_formatter.start_time = time.time()
    logger.reset_time = reset_time

    return logger


def log_this(log_level='DEBUG', msg='', arg_list=None):
    """
    A decorator that logs the functionality, the beginning and the end of the function.
    It can optionally print out arg values in arg_list.
    """

    def decorator(func):
        new_msg = msg or func.__name__
        new_arg_list = arg_list or list()
        def log_func(msg): return logging.log(getattr(logging, log_level), msg)

        @wraps(func)
        def wrapper(*args, **kwargs):
            log_func(f'*STARTING* {new_msg}')

            if new_arg_list:

                func_sig = signature(func)
                bound = func_sig.bind(*args, **kwargs)
                bound.apply_defaults()
                all_args = bound.arguments

                arg_msg = {name: all_args[name] for name in new_arg_list}
                log_func(f'*ARG_LIST* {arg_msg}')

            ret = func(*args, **kwargs)
            log_func(f'*FINISHED* {new_msg}')
            return ret

        return wrapper

    return decorator


def log_pp(obj):
    '''
    Log ``obj`` with better indentations.
    '''
    logging.info(('\n' + str(obj)).replace('\n', '\n' + ' ' * 10))
