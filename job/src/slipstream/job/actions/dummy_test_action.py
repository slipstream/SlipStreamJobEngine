# -*- coding: utf-8 -*-

from __future__ import print_function
from ..util import random_wait

from ..actions import action


@action('dummy_test_action')
class DummyTestActionJob(object):
    def __init__(self, executor, job):
        self.job = job
        self.ss_api = job.ss_api
        self.logger = job.logger
        self.timeout = 15  # seconds job should terminate in maximum 15 seconds

    @staticmethod
    def work_hard():
        random_wait(3, 30)

    def do_work(self):
        self.work_hard()
