#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function

import time
import logging
from slipstream.job.base import main
from slipstream.job.distributor import Distributor
from slipstream.job.util import override

credential_types = {
    'exoscale': 'cloud-cred-exoscale'
}


class CollectQuotasDistributor(Distributor):
    ACTION_NAME = 'collect_quotas'

    def __init__(self):
        super(CollectQuotasDistributor, self).__init__()
        self.collect_interval = 1800

    def _get_credentials(self):
        response = self.ss_api.cimi_search('credentials',
                                           filter='type^="%s"' % '" or type^="'.join(credential_types.values()))
        return response.json.get('credentials')

    @override
    def job_generator(self):
        while True:
            start_time = time.time()
            credentials = self._get_credentials()

            for cred in credentials:
                pending_jobs = \
                    self.ss_api.cimi_search('jobs', filter='action="{}" and targetResource/href="{}" and state="QUEUED"'
                                            .format(CollectQuotasDistributor.ACTION_NAME, cred['id']), last=0)

                if pending_jobs.json['count'] == 0:
                    job = {'action': CollectQuotasDistributor.ACTION_NAME,
                           'targetResource': {'href': cred['id']}}
                    yield job
                else:
                    logging.debug('Action {} already queued, will not create a new job for {}.'
                                  .format(CollectQuotasDistributor.ACTION_NAME, cred['id']))

            time.sleep(self.collect_interval - (time.time() - start_time))

    @override
    def _get_jobs_type(self):
        return 'collect_quotas'


if __name__ == '__main__':
    main(CollectQuotasDistributor)
