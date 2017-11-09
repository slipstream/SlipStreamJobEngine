#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function

import time
from slipstream.job.base import main
from slipstream.job.distributor import Distributor
from slipstream.job.util import classlogger
from slipstream.job.util import override


@classlogger
class CleanupJobsDistributor(Distributor):
    ACTION_NAME = 'cleanup_jobs'

    def __init__(self):
        super(CleanupJobsDistributor, self).__init__()
        self.collect_interval = 86400.0  # 1 day

    @override
    def job_generator(self):
        while True:
            job = {'action': CleanupJobsDistributor.ACTION_NAME,
                   'targetResource': {'href': 'jobs'}}
            yield job
            time.sleep(self.collect_interval)

    @override
    def _get_jobs_type(self):
        return 'cleanup_jobs'


if __name__ == '__main__':
    main(CleanupJobsDistributor)
