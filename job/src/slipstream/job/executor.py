# -*- coding: utf-8 -*-

from __future__ import print_function

import os
import logging
from threading import Thread, currentThread

from elasticsearch import Elasticsearch
from slipstream.api import Api

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
        self._init_logger('executor.log')

    @override
    def _set_command_specific_options(self, parser):
        parser.add_argument('--threads', dest='number_of_thread', default=1,
                            metavar='#', type=int, help='Number of worker threads to start (default: 1)')
        parser.add_argument('--es-hosts-list', dest='es_hosts_list', default=['localhost'],
                            nargs='+', metavar='HOST', help='Elasticsearch list of hosts (default: [localhost])')

    def _process_jobs(self):
        queue = self._kz.LockingQueue('/job')
        cookie_file_thread = os.path.expanduser('~/.slipstream/{}_cookies.txt'.format(currentThread().getName()))
        api = Api(endpoint=self.args.ss_url, insecure=self.args.ss_insecure, reauthenticate=True,
                  cookie_file=cookie_file_thread)
        api.login_internal(self.args.ss_user, self.args.ss_pass)

        while not self.stop_event.is_set():
            job = Job(api, queue)

            if job.nothing_to_do:
                continue

            self.logger.info(self._log_msg('Got new {}.'.format(job.id)))

            try:
                return_code = self.job_processor(job)
            except ActionNotImplemented as e:
                self.logger.exception('Action "{}" not implemented'.format(str(e)))
                # Consume not implemented action to avoid queue to be filled with not implemented actions
                msg = 'Not implemented action'.format(job.id)
                status_message = '{}: {}'.format(msg, str(e))
                job.update_job(state='FAILED', status_message=status_message)
            except Exception as e:
                self.logger.exception('Failed to process {}.'.format(job.id))
                status_message = '{}'.format(str(e))
                job.update_job(state='FAILED', status_message=status_message)
            else:
                job.update_job(state='SUCCESS', return_code=return_code)
                self.logger.info('Successfully finished {}.'.format(job.id))
        self.logger.info('Thread properly stopped.')

    def job_processor(self, job):
        if not job or 'action' not in job:
            logging.warning('Invalid job: {}.'.format(job))

        action_name = job.get('action')
        action = get_action(action_name)

        if not action:
            raise ActionNotImplemented(action_name)

        self.logger.debug('Processing {}.'.format(job.id))
        job.set_state('RUNNING')
        try:
            action_instance = action(self, job)
            with stopit.ThreadingTimeout(action_instance.timeout, swallow_exc=False):
                return action_instance.do_work()
        except stopit.TimeoutException:
            self.logger.exception('Timeout during execution of {}.'.format(job.id))
            raise Exception('Timeout during execution.')
        except:
            self.logger.exception('Processing failed for {}.'.format(job.id))
            raise

    @override
    def do_work(self):
        self.logger.info(self._log_msg('I am executor {}.'.format(self.name)))
        self.es = Elasticsearch(self.args.es_hosts_list)
        for i in range(1, self.args.number_of_thread + 1):
            th_name = 'job_processor_{}_{}'.format(self.name, i)
            th = Thread(target=self._process_jobs, name=th_name)
            th.start()
