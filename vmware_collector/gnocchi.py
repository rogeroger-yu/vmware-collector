import logging

from gnocchiclient import exceptions as gnocchi_exc
from gnocchiclient import client

from vmware_collector import nova
from vmware_collector import keystone

from vmware_collector import utils


LOG = logging.getLogger(__name__)


def get_gnocchiclient(conf):
    session = keystone.get_session(conf)
    return client.Client('1', session=session)


class GnocchiHelper(object):

    def __init__(self, conf):
        self.conf = conf
        self.client = get_gnocchiclient(self.conf)
        self.novaclient = nova.get_nova_client(self.conf)
        self._resource_cache = {}
        self._instance_cache = {}

    def handler_instance_stats(self, stats):
        measures = {}
        for instance_id, info in stats.items():
            try:
                measures.update(self._handle_instance_stat(instance_id, info))
            except Exception:
                LOG.warning('Can not handle %s', instance_id)
        __import__('ipdb').set_trace()
        self.client.metric.batch_resources_metrics_measures(
                measures,
                create_metrics=True)
        LOG.info('Pushed measures for instance: %s', stats)

    def _handle_instance_stat(self, instance_id, info):
        metrics = {}
        # handle instance resource
        instance_resource = self.get_or_create_instance_resource(instance_id)
        metrics[instance_resource['id']] = {
            'cpu_util': [{
                'value': info.get('cpu_util', 0),
                'timestamp': utils.format_date(utils.now())
            }],
            'memory.usage': [{
                'value': info.get('memory_usage', 0),
        }
        return metrics

    def get_server_info(self, uuid):
        server = self._instance_cache.get(uuid)
        if not server:
            server = self.novaclient.servers.get(uuid)
            self._instance_cache[uuid] = server
        return server

    def get_or_create_instance_resource(self, instance_id):

        server = self.get_server_info(instance_id)
        params = {
            'id': server.id,
            'display_name': server.name,
            'flavor_name': server.flavor['id'],
            'flavor_id': server.flavor['id'],
            'host': getattr(server, 'OS-EXT-SRV-ATTR:host'),
            'image_ref': server.image['id'],
            'server_group': ''  # TODO
        }
        return self._get_or_create_resource(instance_id, 'instance', params)

    def get_or_create_instance_disk_resource(self, instance_id, name):
        params = {
            'instance_id': instance_id,
            'name': name
        }
        return self._get_or_create_resource(instance_id,
                                            'instance_disk',
                                            params)

    def get_or_create_instance_network_resource(self, instance_id, name):
        params = {
            'instance_id': instance_id,
            'name': name
        }
        return self._get_or_create_resource(instance_id,
                                            'instance_network_interface',
                                            params)

    def _get_or_create_resource(self, resource_id, resource_type, params):
        res = self._resource_cache.get(resource_id)
        if not res:
            LOG.debug('Creating resource: %s %s', resource_id, params)
            try:
                res = self.client.resource.create(resource_type, params)
            except gnocchi_exc.ResourceAlreadyExists:
                res = self.client.resource.get(resource_type, resource_id)
            self._resource_cache[resource_id] = res
        return res

    def get_metric(self, metric_name,  instance_stat):
        resource = self.get_resource(instance_stat)
        if resource.get(metric_name):
            return resource.get(metric_name)

        try:
            metric = self.client.metric.create(name=metric_name,
                                               resource_id=instance_stat.uuid)
        except gnocchi_exc.NamedMetricAlreadyExists:
            metric = self.client.metric.get(metric_name,
                                            resource_id=instance_stat.uuid)
        resource[metric_name] = metric
        return metric
