# -*- coding: utf-8 -*-

from __future__ import print_function

import logging
import random
import warnings
from threading import Thread, Event

import sys
import time

PY2 = sys.version_info[0] == 2


def random_sleep(secs_min, secs_max):
    time.sleep(random.uniform(secs_min, secs_max))


def classlogger(c):
    """
    A decorator that add a 'log' attribute to the class.
    The log attribute contain a logger with the name:
        <module_name>.<class_name>
    """
    if len(logging.getLogger().handlers) < 1:
        logging.basicConfig(level=logging.DEBUG)
    setattr(c, 'logger', logging.getLogger('%s.%s' % (c.__module__, c.__name__)))
    return c


def print_stack():
    import traceback
    traceback.print_stack()


class InterruptException(Exception):
    pass


class StoppableThread(Thread):

    def __init__(self, group=None, target=None, name=None, queue=None, args=(), kwargs={}):
        args = (self,) + args
        super(StoppableThread, self).__init__(group, target, name, args, kwargs)
        self.interrupt = Event()
        self.queue = queue
        self.contains_target = target is not None

    def stop(self):
        self.interrupt.set()
        if self.queue is not None:
            self.queue.put(None)

    def queue_get(self, *args, **kwargs):
        item = self.queue.get(*args, **kwargs)
        if item is None:
            raise InterruptException()
        return item

    def sleep(self, secs=None):
        self.interrupt.wait(secs)
        if self.interrupt.is_set():
            raise InterruptException()

    def run(self):
        try:
            if self.contains_target:
                super(StoppableThread, self).run()
            else:
                self.run_stoppable()
        except InterruptException:
            return

    def run_stoppable(self):
        raise NotImplemented


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
