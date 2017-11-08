# -*- coding: utf-8 -*-

from __future__ import print_function

from ..util import classlogger
from ..actions import action

import datetime

@classlogger
@action('cleanup_jobs')
class JobsCleanupJob(object):
    def __init__(self, job):
        self.job = job
        self.ss_api = job.ss_api

    def cleanup_jobs(self):
        self.logger.info('Cleanup of completed jobs started.')
        date_minus_7_days = (datetime.datetime.utcnow() - datetime.timedelta(7)).isoformat() + 'Z'
        filter_jobs_str = '(state="SUCCESS" or state="FAILED") and created<"{}"'.format(date_minus_7_days)
        old_jobs = self.ss_api.cimi_search('jobs', filter=filter_jobs_str)
        progress_set_every = int(old_jobs.count / 100) + 1
        progress = 1
        for i, old_job in enumerate(old_jobs.resources_list):
            self.logger.debug('Cleanup of job {}.'.format(old_job.json.get('id')))
            self.ss_api.cimi_delete(old_job.json.get('id'))
            if i > (progress_set_every * progress):
                self.job.set_progress(progress)
                progress += 1
        self.logger.info('Cleanup of completed jobs finished.')
        return 10000

    def do_work(self):
        self.cleanup_jobs()
