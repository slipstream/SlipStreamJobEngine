#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function

import time
from slipstream.job.base import main
from slipstream.job.distributor import Distributor
from slipstream.job.util import override


class NuvlaBoxStateCheckDistributor(Distributor):
    ACTION_NAME = 'nuvlabox_state_check'

    def __init__(self):
        super(NuvlaBoxStateCheckDistributor, self).__init__()
        self.distribute_interval = 600.0  # 10 minutes

    @override
    def job_generator(self):
        while True:
            job = {'action': NuvlaBoxStateCheckDistributor.ACTION_NAME,
                   'targetResource': {'href': 'job'}}
            yield job
            time.sleep(self.distribute_interval)

    @override
    def _get_jobs_type(self):
        return 'nuvlabox_state_check'


if __name__ == '__main__':
    main(NuvlaBoxStateCheckDistributor)
