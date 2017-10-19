# -*- coding: utf-8 -*-

from __future__ import print_function

import time
import random

from threading import Thread

from kazoo.client import KazooClient

from .job import Job
from .util import StoppableThread, classlogger

from slipstream.api import Api, SlipStreamError

names = ['Cartman', 'Kenny', 'Stan', 'Kyle', 'Butters', 'Token', 'Timmy']


class ActionNotImplemented(Exception):
    pass


@classlogger
class JobController(object):

    def __init__(self, ss_username, ss_password, name=None, **kwargs):
        self.name = name if name is not None else names[int(random.uniform(1, len(names)-1))]
        
        zookeeper_args = self._get_kwargs_for(kwargs, 'zk')
        zookeeper_args.setdefault('hosts', '127.0.0.1:2181')

        slipstream_args = self._get_kwargs_for(kwargs, 'ss')

        #unknown_args = set(kwargs.keys()) - set(zookeeper_args.keys())
        #if unknown_args:
        #    warnings.warn('The following arguments doesn\'t exist and '\
        #                  'have been ignored: {}'.format(', '.join(unknown_args)))

        self.ss_api = Api(**slipstream_args)
        self.ss_api.login_internal(ss_username, ss_password)

        self._kz = KazooClient(**zookeeper_args)
        self._queue = self._kz.LockingQueue('/job')
        self.logger.info(self._log_msg('I am {}'.format(self.name)))

        self._kz.start()

    @staticmethod
    def _get_kwargs_for(kwargs, name):
        prefix = '{}_'.format(name)
        return {k[len(prefix):]: v for k, v in kwargs.items() if k.startswith(prefix)}

    def _log_msg(self, message, name=None):
        return '{} - {}'.format(name or self.name, message)

    def _job_distributor(self, job_generator):
        self.logger.info(self._log_msg('I ({}) am the leader (I have been elected)'.format(self.name)))
        while True:
            for cimi_job in job_generator():
                try:
                    self.logger.info(self._log_msg('Distribute job: {}'.format(cimi_job)))
                    #self._queue.put(str_to_bytes(job)) # TOTO: Use SS Python API to push to
                    self.ss_api.cimi_add('jobs', cimi_job)
                except:
                    self.logger.exception(self._log_msg('Failed to distribute job: {}'.format(cimi_job)))
                    time.sleep(0.1)

    def distribute_jobs(self, job_type, job_generator):
        election = self._kz.Election('/election/{}'.format(job_type), self.name)
        while True:
            self.logger.info(self._log_msg('STARTING ELECTION'))
            election.run(self._job_distributor, job_generator)

    def _process_jobs(self, job_processor, thread_name):
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
                    return_code = job_processor(job)
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

    def process_jobs(self, job_processor, number_of_thread=1):
        threads = {}

        for i in range(1, number_of_thread+1):
            th_name = 'job_processor_{}'.format(i)
            th = Thread(target=self._process_jobs, name=th_name, args=(job_processor, th_name))
            th.daemon = True
            th.start()
            threads[th_name] = th

        #for thread in threads.values():
        #    thread.join()

        while True:
            time.sleep(1)

