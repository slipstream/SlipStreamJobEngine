# -*- coding: utf-8 -*-

from __future__ import print_function

from slipstream.api import SlipStreamError

from .util import classlogger


class NonexistentJobError(Exception):
    def __init__(self, reason):
        super(NonexistentJobError, self).__init__(reason)
        self.reason = reason


@classlogger
class Job(dict):

    final_states = ['SUCCESS', 'FAILED']

    def __init__(self, ss_api, job_uri):
        self.ss_api = ss_api
        self.job_uri = job_uri

        try:
            cimi_job = self.ss_api.cimi_get(job_uri).json
            dict.__init__(self, cimi_job)
        except SlipStreamError as e:
            if e.response.status_code == 404:
                raise NonexistentJobError(e.reason)
            else:
                raise e

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
        current_affected_resources_ids = [resource['href'] for resource in self.get('affectedResources', [])]

        for affected_resource in affected_resources:
            if affected_resource not in current_affected_resources_ids:
                current_affected_resources_ids.append(affected_resource)
                has_to_update = True

        if has_to_update:
            self._edit_job('affectedResources', [{'href': id} for id in current_affected_resources_ids])

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

    def __setitem__(self, key, value):
        raise TypeError(" '{}' does not support item assignment".format(self.__class__.__name__))

    def __delitem__(self, item):
        raise TypeError(" '{}' does not support item deletion".format(self.__class__.__name__))

    __getattr__ = dict.__getitem__
