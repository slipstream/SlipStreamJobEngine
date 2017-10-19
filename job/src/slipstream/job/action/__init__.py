# -*- coding: utf-8 -*-

from __future__ import print_function

"""
This package contains code to be executed to process jobs.

Use the @action decorator to register a callable as the processor for a specific action.

The callable will receive a `controller.Job` object as parameter.
The callable can use the method `job.set_progress` to update the progress of the job.
If the job fail to process, the callable should throw an exception.

Examples:
"""

import glob

from os.path import dirname, basename, isfile

modules = glob.glob(dirname(__file__)+"/*.py")

__all__ = [ basename(f)[:-3] for f in modules if isfile(f) and not f.endswith('__init__.py')]

from . import *

@classlogger
class Actions(object):

    actions = {}

    @classmethod
    def get_action(cls, action_name):
        return cls.actions.get(action_name)

    @classmethod
    def register_action(cls, action_name, action):
        cls.actions[action_name] = action

    @classmethod
    def action(cls, action_name=None):

        def decorator(f):
            if not action_name:
                action_name = f.__name__

            if action_name in cls.actions:
                cls.logger.error('Action "{}" is already defined'.format(action_name))
            else:
                cls.register_action(action_name, f)

            return f

        return decorator


action = Actions.action
get_action = Actions.get_action
register_action = Actions.register_action

