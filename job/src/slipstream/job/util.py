# -*- coding: utf-8 -*-

from __future__ import print_function


import sys
import time
import random
import logging

from threading import Thread, Event

PY2 = sys.version_info[0] == 2

def str_to_bytes(string):
    return string if PY2 else bytes(string, 'utf8')

def random_sleep(secs_min, secs_max):
    time.sleep(random.uniform(secs_min, secs_max))

def classlogger(c):
    """
    A decorator that add a 'log' attribute to the class.
    The log attribute contain a logger with the name:
        <module_name>.<class_name>
    """
    setattr(c, 'logger', logging.getLogger('%s.%s' % (c.__module__, c.__name__)))
    return c


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


