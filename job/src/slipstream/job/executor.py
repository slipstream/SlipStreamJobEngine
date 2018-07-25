# -*- coding: utf-8 -*-

from __future__ import print_function

import logging
from threading import Thread

from elasticsearch import Elasticsearch

from .actions import get_action, ActionNotImplemented
from .base import Base
from .job import Job
from .util import classlogger, override
import stopit


@classlogger
class Executor(Base):
    def __init__(self):
        super(Executor, self).__init__()
        self.es = None
        self._init_logger('job_executor.log')

    @override
    def _set_command_specific_options(self, parser):
        parser.add_argument('--threads', dest='number_of_thread', default=1,
                            metavar='#', type=int, help='Number of worker threads to start (default: 1)')
        parser.add_argument('--es-hosts-list', dest='es_hosts_list', default=['localhost'],
                            nargs='+', metavar='HOST', help='Elasticsearch list of hosts (default: [localhost])')

    @staticmethod
    def thread_log_msg(thread_name):
        def log_msg(msg):
            return ' {} - {}'.format(thread_name, msg)
        return log_msg

    def _process_jobs(self, thread_name):
        queue = self._kz.LockingQueue('/job')
        thread_log_fn = Executor.thread_log_msg(thread_name)

        while not self.stop_event.is_set():
            job = Job(self.ss_api, queue, thread_log_fn)

            if job.nothing_to_do:
                continue

            self.logger.info(self._log_msg('Got new {}.'.format(job.id), name=thread_name))

            try:
                return_code = self.job_processor(job, thread_log_fn)
            except ActionNotImplemented as e:
                self.logger.exception(thread_log_fn('Action "{}" not implemented'.format(str(e))))
                # Consume not implemented action to avoid queue to be filled with not implemented actions
                msg = 'Not implemented action'.format(job.id)
                status_message = '{}: {}'.format(msg, str(e))
                job.update_job(state='FAILED', status_message=status_message)
            except Exception as e:
                msg = 'Failed to process {}.'.format(job.id)
                self.logger.exception(thread_log_fn(msg))
                status_message = '{}: {}'.format(msg, str(e))
                job.update_job(state='FAILED', status_message=status_message)
                self.stop_event.wait(0.1)
            else:
                job.update_job(state='SUCCESS', return_code=return_code)
                self.logger.info(thread_log_fn('Successfully finished {}.'.format(job.id)))
        self.logger.info(thread_log_fn('Thread properly stopped.'))

    def job_processor(self, job, thread_log_fn):
        if not job or 'action' not in job:
            logging.warning(thread_log_fn('Invalid job: {}.'.format(job)))

        action_name = job.get('action')
        action = get_action(action_name)

        if not action:
            raise ActionNotImplemented(action_name)

        self.logger.debug(thread_log_fn('Processing {}.'.format(job.id)))
        job.set_state('RUNNING')
        try:
            action_instance = action(self, job, thread_log_fn)
            with stopit.ThreadingTimeout(action_instance.timeout, swallow_exc=False):
                return action_instance.do_work()
        except stopit.TimeoutException:
            self.logger.exception(thread_log_fn('Timeout during execution of {}.'.format(job.id)))
            raise Exception('Timeout during execution.')
        except:
            self.logger.exception(thread_log_fn('Processing failed for {}.'.format(job.id)))
            raise

    @override
    def do_work(self):
        self.logger.info(self._log_msg('I am executor {}.'.format(self.name)))
        self.es = Elasticsearch(self.args.es_hosts_list)
        for i in range(1, self.args.number_of_thread + 1):
            th_name = 'job_processor_{}_{}'.format(self.name, i)
            th = Thread(target=self._process_jobs, name=th_name, args=(th_name,))
            th.start()
