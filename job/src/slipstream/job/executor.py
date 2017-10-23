# -*- coding: utf-8 -*-

from __future__ import print_function

import logging
from threading import Thread

import time

from .actions import get_action, ActionNotImplemented
from .base import Base
from .job import Job
from .util import classlogger
from .util import override


@classlogger
class Executor(Base):
    def __init__(self):
        super(Executor, self).__init__()

    @override
    def _set_command_specific_options(self, parser):
        parser.add_argument('--threads', dest='number_of_thread', default=1,
                            metavar='#', type=int, help='Number of worker threads to start')

    def _process_jobs(self, thread_name):
        while True:
            job_uri = None
            try:
                job_uri = self._queue.get()
                job = Job(self.ss_api, job_uri)

                if job is None:
                    self.logger.debug(self._log_msg('No job available. Waiting ...'))
                    time.sleep(0.1)
                    continue

                self.logger.info(self._log_msg('Executing job "{}" ...'.format(job_uri), name=thread_name))

                try:
                    return_code = self.job_processor(job)
                except ActionNotImplemented as e:
                    self.logger.warning(self._log_msg('Action "{}" not implemented'.format(str(e))))
                    self._queue.release()
                except Exception as e:
                    msg = 'Failed to process job {}'.format(job_uri)
                    self.logger.exception(self._log_msg(msg))
                    self._queue.consume()
                    status_message = '{}: {}'.format(msg, str(e))
                    job.update_job(state='FAILED', status_message=status_message)
                    time.sleep(0.1)
                else:
                    job.update_job(state='SUCCESS', return_code=return_code)
                    self._queue.consume()
                    self.logger.info(self._log_msg('Job "{}" finished'.format(job_uri), name=thread_name))
            except:
                self.logger.exception('Fatal error when trying to handle job "{}"'.format(job_uri))

    def job_processor(self, job):
        if not job or 'action' not in job:
            logging.warning('Invalid job: {}'.format(job))

        action_name = job.get('action')
        action = get_action(action_name)

        if not action:
            raise ActionNotImplemented(action_name)

        self.logger.debug(self._log_msg('Processing job {}'.format(job.job_uri)))
        job.set_state('RUNNING')
        try:
            return action(job)
        except:
            self.logger.exception(self._log_msg('Job failed while processing it'))
            # TODO: Fail the job or raise something so that the caller fail the job
            raise

    @override
    def do_work(self):
        threads = {}

        for i in range(1, self.args.number_of_thread + 1):
            th_name = 'job_processor_{}'.format(i)
            th = Thread(target=self._process_jobs, name=th_name, args=th_name)
            th.daemon = True
            th.start()
            threads[th_name] = th

            # for thread in threads.values():
            #    thread.join()

        while True:
            time.sleep(1)
