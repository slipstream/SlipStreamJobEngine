# -*- coding: utf-8 -*-

from __future__ import print_function

from ..util import classlogger
from ..actions import action


@classlogger
@action('cleanup_nb_state_snaps')
class NuvlaboxStateSnapshotsCleanupJob(object):
    def __init__(self, executor, job):
        self.job = job
        self.es = executor.es
        self.timeout = 30  # seconds job should terminate in maximum 30 seconds

    def cleanup_snapshots(self):
        self.logger.info('Cleanup of old nuvlabox state snapshots started.')

        number_of_days_back = 30
        query_string = 'created:<now-{}d'.format(number_of_days_back)
        query_old_snapshots = {'query': {'query_string': {'query': query_string}}}
        result = self.es.delete_by_query(index='slipstream-nuvlabox-state-snapshot',
                                         doc_type='_doc', body=query_old_snapshots)

        if result['timed_out'] or result['failures']:
            error_msg = 'Cleanup of old nuvlabox state snapshots have some failures: {}'.format(result)
            self.logger.warning(error_msg)
            self.job.set_status_message(error_msg)
        else:
            msg = 'Cleanup of old nuvlabox state snapshots finished. Removed {} snapshots.'.format(result['deleted'])
            self.logger.info(msg)
            self.job.set_status_message(msg)

        return 10000

    def do_work(self):
        self.cleanup_snapshots()
