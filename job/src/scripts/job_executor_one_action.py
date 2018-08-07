#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function
from slipstream.job.base import main, Base

from slipstream.job.actions import get_action
from slipstream.job.util import classlogger, override


@classlogger
class OneActionExecutor(Base):
    def __init__(self):
        super(OneActionExecutor, self).__init__()
        self.es = None
        self._init_logger('one_action_executor.log')

    @override
    def do_work(self):
        self.logger.info(self._log_msg('I am one action executor {}.'.format(self.name)))

        action_name = 'start-deployment'
        action = get_action(action_name)
        action_instance = action(self, None)

        try:
            action_instance.do_work()
        except Exception as e:
            self.logger.exception('Failed to process {}.'.format(e))


if __name__ == '__main__':
    main(OneActionExecutor)
