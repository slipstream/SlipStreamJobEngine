#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function

import time
from slipstream.job.base import main
from slipstream.job.distributor import Distributor
from slipstream.job.util import override

####
####
# JUST WORKING FOR EXOSCALE AT THE MOMENT
# WAITING FOR https://github.com/slipstream/SlipStreamServer/issues/1639
####
####

credential_types = {
    'exoscale': 'cloud-cred-exoscale'
}


class CollectStorageBucketsDistributor(Distributor):
    ACTION_NAME = 'collect_storage_buckets'

    def __init__(self):
        super(CollectStorageBucketsDistributor, self).__init__()
        self.collect_interval = 60.0

    def _get_credentials(self):
        response = self.ss_api.cimi_search('credentials',
                                           filter='type^="%s"' % '" or type^="'.join(credential_types.values()))
        return response.json.get('credentials')

    @staticmethod
    def _time_spent(start_time):
        return time.time() - start_time

    def _time_left(self, start_time):
        return self.collect_interval - self._time_spent(start_time)

    @override
    def job_generator(self):
        while True:
            start_time = time.time()

            credentials = self._get_credentials()
            nb_credentials = len(credentials)

            yield_interval = float(self.collect_interval) / max(float(nb_credentials), 1) * 0.6

            #################
            # Hack for Exoscale, where different endpoints seem to point to the same buckets
            # just use a single key and endpoint
            #################
            special_cloud = "cloud-cred-exoscale"
            special_endpoint = "https://sos-ch-dk-2.exo.io"
            api_key_list = []

            for credential in credentials:
                endpoint = None
                if credential["type"] == special_cloud:
                    # This workaround is because Exoscale does not seem to 
                    # distinguish the buckets between different endpoints, so we'll just use one
                    endpoint = special_endpoint
                    if credential["key"] in api_key_list:
                        continue
                    else:
                        api_key_list.append(credential["key"])

                pending_jobs = \
                    self.ss_api.cimi_search('jobs', filter='action="{}" and targetResource/href="{}" and state="QUEUED"'
                                            .format(CollectStorageBucketsDistributor.ACTION_NAME, credential['id']),
                                            last=0)
                if pending_jobs.json['count'] == 0:
                    # TODO: waiting for https://github.com/slipstream/SlipStreamServer/issues/1639
                    # to define endpoint dynamically, from the connector resource
                    #
                    # endpoint = ....

                    if not endpoint:
                        continue

                    job = {'action': CollectStorageBucketsDistributor.ACTION_NAME,
                           'targetResource': {'href': credential['id']}}
                    yield job
                else:
                    logging.debug('Action {} already queued, will not create a new job for {}.'
                                  .format(CollectStorageBucketsDistributor.ACTION_NAME, credential['id']))

                time.sleep(yield_interval)
            time.sleep(self._time_left(start_time))

    @override
    def _get_jobs_type(self):
        return 'collect_storage_buckets'


if __name__ == '__main__':
    main(CollectStorageBucketsDistributor)
