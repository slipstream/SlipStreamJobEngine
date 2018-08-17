# -*- coding: utf-8 -*-

from __future__ import print_function

from ..actions import action


@action('cleanup_jobs')
class JobsCleanupJob(object):
    def __init__(self, executor, job):
        self.job = job
        self.es = executor.es
        self.logger = job.logger
        self.timeout = 30  # seconds job should terminate in maximum 30 seconds

    def cleanup_jobs(self):
        self.logger.info('Cleanup of completed jobs started.')

        number_of_days_back = 7
        query_string = 'state:(SUCCESS OR FAILED) AND created:<now-{}d'.format(number_of_days_back)
        query_old_completed_jobs = {'query': {'query_string': {'query': query_string}}}
        result = self.es.delete_by_query(index='slipstream-job', doc_type='_doc', body=query_old_completed_jobs)

        if result['timed_out'] or result['failures']:
            error_msg = 'Cleanup of completed jobs have some failures: {}.'.format(result)
            self.logger.warning(error_msg)
            self.job.set_status_message(error_msg)
        else:
            msg = 'Cleanup of completed jobs finished. Removed {} jobs.'.format(result['deleted'])
            self.logger.info(msg)
            self.job.set_status_message(msg)

        return 10000

    def do_work(self):
        self.cleanup_jobs()
