# -*- coding: utf-8 -*-

from __future__ import print_function

from ..util import classlogger
from ..actions import action


@classlogger
@action('cleanup_jobs')
class JobsCleanupJob(object):
    def __init__(self, executor, job):
        self.job = job
        self.es = executor.es

    def cleanup_jobs(self):
        self.logger.info('Cleanup of completed jobs started.')
        number_of_days_back = 7
        query_old_completed_jobs = \
            {'query':
                 {'query_string':
                      {'query': 'state:(SUCCESS OR FAILED) AND created:<now-{}d'.format(number_of_days_back)}}}
        result = self.es.delete_by_query(index='resources-index', doc_type='job', body=query_old_completed_jobs)
        self.logger.debug(result)
        if result['timed_out'] or result['failures']:
            error_msg = 'Cleanup of completed jobs have some failures: {}'.format(result)
            self.logger.warning(error_msg)
            self.job.set_status_message(error_msg)
        else:
            msg = 'Cleanup of completed jobs finished. Removed {} jobs.'.format(result['deleted'])
            self.logger.info(msg)
            self.job.set_status_message(msg)
        return 10000

    def do_work(self):
        self.cleanup_jobs()
