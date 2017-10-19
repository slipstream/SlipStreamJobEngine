# -*- coding: utf-8 -*-

from __future__ import print_function

import time
import random
import logging

from threading import Thread

from kazoo.client import KazooClient

from util import PY2, StoppableThread, classlogger, str_to_bytes

from slipstream.api import Api, SlipStreamError

names = ['Cartman', 'Kenny', 'Stan', 'Kyle', 'Butters', 'Token', 'Timmy']


@classlogger
class Job(dict):

    def __init__(self, ss_api, job_uri):
        self.ss_api = ss_api
        self.job_uri = job_uri

        cimi_job = self.ss_api.cimi_get(job_uri).json
        dict.__init__(self, cimi_job)

    def set_progress(self, progress):
        if not isinstance(progress, int):
            raise TypeError('progress should be int not {}'.format(type(progress)))

        if not (0 <= progress <= 100):
            raise ValueError('progress shoud be between 0 and 100 not {}'.format(progress))

        self._edit_job('progress', progress, raise_on_error=False)

    def set_status_message(self, status_message):
        self._edit_job('statusMessage', str(status_message), raise_on_error=False)

    def set_return_code(self, return_code):
        if not isinstance(return_code, int):
            raise TypeError('return_code should be int not {}'.format(type(return_code)))

        self._edit_job('returnCode', return_code)

    def set_state(self, state):
        states = ('QUEUED', 'RUNNING', 'FAILED', 'SUCCESS', 'STOPPING', 'STOPPED')
        if state not in states:
            raise ValueError('state should be one of {}'.format(states))

        self._edit_job('state', state)

    def add_affected_resource(self, affected_resource):
        self.add_affected_resources([affected_resource])

    def add_affected_resources(self, affected_resources):
        has_to_update = False
        current_affected_resources = self.get('affectedResources', [])

        for affected_resource in affected_resources:
            if affected_resource not in current_affected_resources:
                current_affected_resources.append(affected_resource)
                has_to_update = True

        if has_to_update:
            self._edit_job('affectedResources', current_affected_resources)

    def update_job(self, state=None, return_code=None, status_message=None):
        attributes = {}

        if state is not None:
            attributes['state'] = state

        if return_code is not None:
            attributes['returnCode'] = return_code

        if status_message is not None:
            attributes['statusMessage'] = status_message

        if attributes:
            self._edit_job_multi(attributes)

    def _edit_job(self, attribute_name, attribute_value, raise_on_error=True):
        try:
            response = self.ss_api.cimi_edit(self.job_uri, {attribute_name: attribute_value})
        except SlipStreamError:
            self.logger.exception('Failed to update job attribute "{}" for job "{}"'.format(attribute_name,
                                                                                            self.job_uri))
            if raise_on_error:
                raise
        else:
            self.update(response.json)

    def _edit_job_multi(self, attributes):
        try:
            response = self.ss_api.cimi_edit(self.job_uri, attributes)
        except SlipStreamError:
            self.logger.exception('Failed to update the following attributes "{}" for job {}'.format(attributes,
                                                                                                     self.job_uri))
        else:
            self.update(response.json)

    def __setitem(self, key, value):
        dict.__setitem__(self, key, value)

    def __setattr__(self, key, value):
        raise TypeError(" '{}' does not support attribute assignment".format(self.__class__.__name__))

    def __delattr__(self, item):
        raise TypeError(" '{}' does not support attribute deletion".format(self.__class__.__name__))

    def __setitem__(self, key, value):
        raise TypeError(" '{}' does not support item assignment".format(self.__class__.__name__))

    def __delitem__(self, item):
        raise TypeError(" '{}' does not support item deletion".format(self.__class__.__name__))

    __getattr__ = dict.__getitem__



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

        self._ss_api = Api(**slipstream_args)
        self._ss_api.login_internal(ss_username, ss_password)

        self._kz = KazooClient(**zookeeper_args)
        self._queue = self._kz.LockingQueue('/job')
        self._log('I am {}'.format(self.name))

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
            job = None
            for job in job_generator():
                try:
                    self.logger.info(self._log_msg('Distribute job {}'.format(job)))
                    #self._queue.put(str_to_bytes(job)) # TOTO: Use SS Python API to push to
                    self._ss_api.cimi_add('jobs', job)
                except:
                    self.logger.exception(self._log_msg('Failed to distribute job {}'.format(job)))
                    time.sleep(0.1)

    def distribute_jobs(self, job_type, job_generator):
        election = self._kz.Election('/election/{}'.format(job_type), self.name)
        while True:
            self.logger.info(self._log_msg('STARTING ELECTION'))
            election.run(self._job_distributor, job_generator)

    def _process_jobs(self, thread, job_processor):
        while True:
            job_uri = self._queue.get()
            job = Job(self._ss_api, job_uri)

            self.ss_api.cimi_get(job_uri)

            if job is None:
                self.logger.debug(self._log_msg('No job available. Waiting ...'))
                self.sleep(0.1)
                break

            self.logger.info(self._log_msg('Executing job "{}" ...'.format(job), name=thread.name))

            try:
                return_code = job_processor(job)
            except ActionNotImplemented as e:
                self.logger.warning(self._log_msg('Action "{}" not implemented'.format(str(e))))
                self._queue.release()
            except Exception as e:
                msg = 'Failed to process job {}'.format(job)
                self.logger.exception(self._log_msg(msg))
                self._queue.consume()
                status_message = '{}: {}'.format(msg, str(e))
                job.update_job(state='FAILED', status_message=status_message)
                self.sleep(0.1)
            else:
                job.update_job(state='SUCCESS', return_code=return_code)
                self._queue.consume()
                self.logger.info(self._log_msg('Job "{}" finished'.format(job)), logging.DEBUG, thread.name)

    def process_jobs(self, job_processor, number_of_thread=1):
        for i in range(1, number_of_thread+1):
            th_name = 'job_processor_{}'.format(i)
            th = StoppableThread(target=self._process_jobs, name=th_name, args=(job_processor,))
            th.daemon = True
            th.start()

        while True:
            time.sleep(1)

