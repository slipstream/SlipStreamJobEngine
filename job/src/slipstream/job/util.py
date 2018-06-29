# -*- coding: utf-8 -*-

from __future__ import print_function

import logging
import random
import warnings
from threading import Event

import sys

PY2 = sys.version_info[0] == 2


def random_wait(secs_min, secs_max):
    e = Event()
    e.wait(timeout=random.uniform(secs_min, secs_max))


def classlogger(c):
    """
    A decorator that add a 'log' attribute to the class.
    The log attribute contain a logger with the name:
        <module_name>.<class_name>
    """
    if len(logging.getLogger().handlers) < 1:
        logging.basicConfig(level=logging.INFO)
    setattr(c, 'logger', logging.getLogger('%s.%s' % (c.__module__, c.__name__)))
    return c


def print_stack():
    import traceback
    traceback.print_stack()


class InterruptException(Exception):
    pass


def override(func):
    """This is a decorator which can be used to check that a method override a method of the base class.
    If not the case it will result in a warning being emitted."""

    def overrided_func(self, *args, **kwargs):
        bases_functions = []
        for base in self.__class__.__bases__:
            bases_functions += dir(base)

        if func.__name__ not in bases_functions:
            warnings.warn("The method '%s' should override a method of the base class '%s'." %
                          (func.__name__, self.__class__.__bases__[0].__name__), category=SyntaxWarning, stacklevel=2)
        return func(self, *args, **kwargs)

    return overrided_func


def load_module(module_name):
    namespace = ''
    name = module_name
    if name.find('.') != -1:
        # There's a namespace so we take it into account
        namespace = '.'.join(name.split('.')[:-1])

    return __import__(name, fromlist=namespace)
