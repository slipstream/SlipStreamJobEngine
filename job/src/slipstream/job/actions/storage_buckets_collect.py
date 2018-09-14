# -*- coding: utf-8 -*-

from __future__ import print_function

import boto3

import logging

try:
    from itertools import izip as zip  # PY2
except ImportError:
    pass  # PY3

from ..util import random_wait

from ..actions import action

from slipstream.api import SlipStreamError


@action('collect_storage_buckets')
class StorageBucketsCollectJob(object):
    def __init__(self, executor, job):
        self.job = job
        self.ss_api = job.ss_api

        self._cloud_name = None
        self._cloud_credential = None
        self._cloud_configuration = None
        self._connector_s3_endpoint = None

    def _get_cloud_credential(self):
        return self.ss_api.cimi_get(self.job['targetResource']['href']).json

    def _get_cloud_configuration(self):
        return self.ss_api.cimi_get(self.cloud_name).json

    def _get_existing_storage_bucket(self, bucket_name):
        return self.ss_api.cimi_search('storageBuckets', filter='credentials/href="{}" and bucketName="{}"'
                                       .format(self.cloud_credential['id'], bucket_name))

    def _get_service_offer(self):
        return self.ss_api.cimi_search('serviceOffers',
                                       filter='resource:storage!=null and resource:platform="S3" and connector/href="{}"'
                                       .format(self.cloud_name.replace("connector/", ""))).resources_list

    @property
    def cloud_credential(self):
        if self._cloud_credential is None:
            self._cloud_credential = self._get_cloud_credential()
        return self._cloud_credential

    @property
    def cloud_name(self):
        return self.cloud_credential['connector']['href']

    @property
    def connector_s3_endpoint(self):
        if self._connector_s3_endpoint is None and "objectStoreEndpoint" in self.cloud_configuration:
            self._connector_s3_endpoint = self.cloud_configuration["objectStoreEndpoint"]
        return self._connector_s3_endpoint

    @property
    def cloud_configuration(self):
        if self._cloud_configuration is None:
            self._cloud_configuration = self._get_cloud_configuration()
        return self._cloud_configuration

    def cred_exist_already(self, exiting_sb):
        for cred in exiting_sb['credentials']:
            if cred['href'] == self.cloud_credential['id']:
                return True
        return False

    @staticmethod
    def dict2tuple(d, *keys):
        return tuple([d[k] for k in keys])

    @staticmethod
    def _get_bucket_size(client, bucket_name):
        size = 0
        for obj in client.Bucket(bucket_name).objects.all():
            # default size is in binary bytes
            # the size we want is in KB
            size += int(obj.size / 1024)

        return size

    @classmethod
    def combine_acl_rules(cls, *rules_args):
        rule_attrs = ('type', 'principal', 'right')
        rules_set = {cls.dict2tuple(r, *rule_attrs) for rules in rules_args for r in rules}
        return [dict(zip(rule_attrs, r)) for r in rules_set]

    def get_cloud_credentials(self, credentials_ids):
        cimi_filter = ' or '.join(['id="{}"'.format(id) for id in credentials_ids])
        cimi_filter = 'type^="cloud-cred-" and ({})'.format(cimi_filter)
        cimi_response = self.ss_api.cimi_search('credentials', filter=cimi_filter)
        return [credential.json for credential in cimi_response.resources()]

    def acl_rules_from_managers(self, extra_cloud_credentials=None):
        rules = []

        cloud_credentials = [self.cloud_credential]
        if extra_cloud_credentials:
            cloud_credentials += extra_cloud_credentials

        for cloud_credential in cloud_credentials:
            managers = cloud_credential.get('managers', [])
            for manager in managers:
                rules.append(dict(right='VIEW', **manager))

        return rules

    def create_storage_bucket(self, json_resource):
        try:
            cimi_storage_bucket_id = self.ss_api.cimi_add('storageBuckets', json_resource).json.get('resource-id')
            logging.info('Added new storage bucket: {}.'.format(cimi_storage_bucket_id))
        except SlipStreamError as e:
            if e.response.status_code == 409:
                cimi_storage_bucket_id = e.response.json()['resource-id']
                logging.info('Storage bucket {} creation issue due to {}.'.format(cimi_storage_bucket_id, e))
            else:
                raise e

        return cimi_storage_bucket_id

    def update_storage_bucket(self, json_resource, existing_storage_bucket):
        existing_sb = existing_storage_bucket.resources_list[0].json
        sb_id = existing_sb['id']
        sb_credentials = existing_sb['credentials'][:]

        cimi_cloud_credentials = self.get_cloud_credentials([c['href'] for c in sb_credentials])

        json_resource['acl']['rules'] = self.combine_acl_rules(json_resource['acl']['rules'],
                                                               self.acl_rules_from_managers(cimi_cloud_credentials))

        # Remove credentials that don't exist anymore
        new_credentials = [{'href': c['id']} for c in cimi_cloud_credentials]

        if not self.cred_exist_already(existing_sb):
            logging.debug(
                'Credential {} will be appended to existing storage bucket {}.'.format(self.cloud_credential['id'],
                                                                                       sb_id))
            new_credentials.append({'href': self.cloud_credential['id']})

        json_resource['credentials'] = new_credentials

        logging.info('Update existing storage bucket: {}.'.format(sb_id))
        try:
            self.ss_api.cimi_edit(sb_id, json_resource)
        except SlipStreamError as e:
            if e.response.status_code == 409:
                # Could happen when sb is beeing updated at same time by different thread
                logging.info('Storage bucket update conflict of {}.').format(sb_id)
                random_wait(0.5, 5.0)
                self.update_storage_bucket(json_resource,
                                           self._get_existing_storage_bucket(json_resource["bucketName"]))
                # retry recursion is stopped by the job executor after self.timeout
        return sb_id

    def create_storage_bucket_resource(self, bucket_name, bucket_size):
        description = 'obj store usage for bucket {}, from credential {} in {}' \
            .format(bucket_name, self.cloud_credential["id"], self.cloud_name)
        name = 'bucket {} size in {}'.format(bucket_name, self.cloud_name)
        credentials = [{"href": self.cloud_credential["id"]}]
        connector = {'href': self.cloud_name}

        acl = {'owner': {'type': 'ROLE', 'principal': 'ADMIN'},
               'rules': [{'principal': 'ADMIN', 'right': 'ALL', 'type': 'ROLE'},
                         {'principal': self.cloud_credential['acl']['owner']['principal'], 'right': 'VIEW',
                          'type': self.cloud_credential['acl']['owner']['type']}]}

        service_offer = self._get_service_offer()

        if len(service_offer) > 0:
            so = {'href': service_offer[0].json['id'],
                  'resource:storage': service_offer[0].json['resource:storage'],
                  'resource:host': service_offer[0].json['resource:host'],
                  'price:currency': service_offer[0].json['price:currency'],
                  'price:unitCost': service_offer[0].json['price:unitCost'],
                  'resource:platform': service_offer[0].json['resource:platform'],
                  'resource:type': service_offer[0].json['resource:type'],
                  'price:billingUnit': service_offer[0].json['price:billingUnit']}
        else:
            so = {'href': "service-offer/unknown"}

        sb_resource = {'resourceURI': 'http://sixsq.com/slipstream/1/StorageBucket',
                       'description': description,
                       'name': name,
                       'acl': acl,
                       'connector': connector,
                       'credentials': credentials,
                       'usageInKiB': bucket_size,
                       'bucketName': bucket_name,
                       'serviceOffer': so}

        return sb_resource

    def handle_cimi_storage_bucket(self, bucket_name, bucket_size):
        existing_storage_bucket = self._get_existing_storage_bucket(bucket_name)
        sb_resource = self.create_storage_bucket_resource(bucket_name, bucket_size)

        if existing_storage_bucket.count == 0:
            cimi_sb_id = self.create_storage_bucket(sb_resource)
        else:
            cimi_sb_id = self.update_storage_bucket(sb_resource, existing_storage_bucket)

        self.job.add_affected_resource(cimi_sb_id)

    def collect_storage_buckets(self):
        logging.info('Collect storage buckets started for {}.'.format(self.cloud_credential['id']))

        s3_endpoint = self.connector_s3_endpoint

        self.job.set_progress(10)

        if not s3_endpoint:
            self.job.set_status_message(
                "No object store endpoint associated with {}".format(self.cloud_credential['id']))
            return 10000

        s3_client = boto3.resource(service_name='s3',
                                   aws_access_key_id=self.cloud_credential["key"],
                                   aws_secret_access_key=self.cloud_credential["secret"],
                                   endpoint_url=s3_endpoint)

        self.job.set_progress(20)

        all_buckets = s3_client.buckets.all()
        nbuckets = len(list(all_buckets))

        progress = 20
        for i, bucket in enumerate(all_buckets):
            bucket_size = self._get_bucket_size(s3_client, bucket.name)
            if bucket_size > 0:
                self.handle_cimi_storage_bucket(bucket.name, bucket_size)

            self.job.set_progress(progress + (i + 1) * (100 - progress) / nbuckets)

        return 10000

    def do_work(self):
        self.collect_storage_buckets()
