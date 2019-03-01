# -*- coding: utf-8 -*-

from __future__ import print_function

from ..actions import action

import logging

logger = logging.getLogger(__name__)

@action('nuvlabox_state_check')
class NuvlaBoxStateCheckJob(object):
    def __init__(self, executor, job):
        self.job = job
        self.ss_api = job.ss_api

    def get_activated_nuvlabox_records_by_id(self):
        filter = 'state="activated" and formFactor!="nano"' # TODO: remove formFactor condition
        return {nb.id: nb.json for nb in self.ss_api.cimi_search('nuvlaboxRecords', filter=filter).resources()}

    def get_newly_offline_nuvlabox_record_ids(self, nb_records_by_id):
        if not nb_records_by_id:
            return []

        # Build the CIMI query filter
        fmt = '(nuvlabox/href="{}" and updated < "now-{}m" and state!="offline")'
        filter_parts = [fmt.format(id, nb.get('notificationDelay', 60)) for id, nb in nb_records_by_id.items()]
        filter = ' or '.join(filter_parts)

        return [i.json['nuvlabox']['href'] for i in self.ss_api.cimi_search('nuvlaboxStates', filter=filter).resources()]

    def set_nuvlabox_offline(self, nb_records_ids):
        for nb_record_id in nb_records_ids:
            self.ss_api.cimi_edit(nb_record_id, {'state': 'offline'})

    def nuvlabox_state_check(self):
        logger.info('NuvlaBox state check job started.')

        nb_records_by_id = self.get_activated_nuvlabox_records_by_id()
        self.job.set_progress(30)
        logger.debug('nb_records_by_id: {}'.format(nb_records_by_id.keys()))

        nb_records_ids_offline = self.get_newly_offline_nuvlabox_record_ids(nb_records_by_id)
        self.job.set_progress(60)
        logger.debug('nb_records_ids_offline: {}'.format(nb_records_ids_offline))

        msg = 'No NuvlaBox newly offline'
        if nb_records_ids_offline:
            nuvlabox_offlines = [nb_records_by_id[i].get('name', i) for i in nb_records_ids_offline]
            msg = 'NB offlines: {}'.format(nuvlabox_offlines)
        self.job.set_status_message(msg)
        logger.info(msg)

        nb_states_ids_offline = [nb_records_by_id[i]['info']['href'] for i in nb_records_ids_offline
                                 if nb_records_by_id[i].get('info',{}).get('href')]
        self.set_nuvlabox_offline(nb_states_ids_offline)

        return 0

    def do_work(self):
        self.nuvlabox_state_check()
