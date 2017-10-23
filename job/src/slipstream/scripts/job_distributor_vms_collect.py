#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function

import time
from slipstream.job.base import main
from slipstream.job.distributor import Distributor
from slipstream.job.util import classlogger
from slipstream.job.util import override


@classlogger
class CollectDistributor(Distributor):
    def __init__(self):
        super(CollectDistributor, self).__init__()
        self.collect_interval = 60.0

    def _get_credentials(self):
        response = self.ss_api.cimi_search('credentials', filter='type^="cloud-cred"')
        return response.json.get('credentials')

    @staticmethod
    def _time_spent(start_time):
        return time.time() - start_time

    def _time_left(self, start_time):
        return self.collect_interval - self._time_spent(start_time)

    @override
    def _job_generator(self):
        while True:
            start_time = time.time()

            credentials = self._get_credentials()
            nb_credentials = len(credentials)

            yield_interval = float(self.collect_interval) / max(float(nb_credentials), 1) * 0.6

            for credential in credentials:
                job = {'action': 'collect_virtual_machines',
                       'targetResource': {'href': credential['id']}}
                yield job

                time.sleep(yield_interval)
            time.sleep(self._time_left(start_time))

    @override
    def _get_jobs_type(self):
        return 'collect_virtual_machines'


if __name__ == '__main__':
    main(CollectDistributor)
