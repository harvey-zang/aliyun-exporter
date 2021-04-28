import json
import time
import datetime

from aliyunsdkcore.client import AcsClient
from cachetools import cached, TTLCache
from prometheus_client.metrics_core import GaugeMetricFamily

import aliyunsdkecs.request.v20140526.DescribeInstancesRequest as DescribeECS
import aliyunsdkrds.request.v20140815.DescribeDBInstancesRequest as DescribeRDS
import aliyunsdkr_kvstore.request.v20150101.DescribeInstancesRequest as DescribeRedis
import aliyunsdkslb.request.v20140515.DescribeLoadBalancersRequest as DescribeSLB
import aliyunsdkslb.request.v20140515.DescribeLoadBalancerAttributeRequest as DescribeSLBAttr
import aliyunsdkslb.request.v20140515.DescribeLoadBalancerTCPListenerAttributeRequest as DescribeSLBTcpAttr
import aliyunsdkslb.request.v20140515.DescribeLoadBalancerHTTPListenerAttributeRequest as DescribeSLBHttpAttr
import aliyunsdkslb.request.v20140515.DescribeLoadBalancerHTTPSListenerAttributeRequest as DescribeSLBHttpsAttr
import aliyunsdkdds.request.v20151201.DescribeDBInstancesRequest as Mongodb
import aliyunsdkcdn.request.v20180510.DescribeUserDomainsRequest as DescribeCDN

from aliyun_exporter.utils import try_or_else

cache = TTLCache(maxsize=100, ttl=3600)

'''
InfoProvider provides the information of cloud resources as metric.

The result from alibaba cloud API will be cached for an hour. 

Different resources should implement its own 'xxx_info' function. 

Different resource has different information structure, and most of
them are nested, for simplicity, we map the top-level attributes to the
labels of metric, and handle nested attribute specially. If a nested
attribute is not handled explicitly, it will be dropped.
'''
class InfoProvider():

    def __init__(self, client: AcsClient):
        self.client = client

    @cached(cache)
    def get_metrics(self, resource: str) -> GaugeMetricFamily:
        return {
            'ecs': lambda : self.ecs_info(),
            'rds': lambda : self.rds_info(),
            'cdn': lambda : self.cdn_info(),
            'redis': lambda : self.redis_info(),
            'slb':lambda : self.slb_info(),
            'mongodb':lambda : self.mongodb_info(),
        }[resource]()

    def ecs_info(self) -> GaugeMetricFamily:
        req = DescribeECS.DescribeInstancesRequest()
        nested_handler = {
            'InnerIpAddress': lambda obj : try_or_else(lambda : obj['IpAddress'][0], ''),
            'PublicIpAddress': lambda obj : try_or_else(lambda : obj['IpAddress'][0], ''),
            'VpcAttributes': lambda obj : try_or_else(lambda : obj['PrivateIpAddress']['IpAddress'][0], ''),
        }
        return self.info_template(req, 'aliyun_meta_ecs_info', nested_handler=nested_handler)

    def rds_info(self) -> GaugeMetricFamily:
        req = DescribeRDS.DescribeDBInstancesRequest()
        return self.info_template(req, 'aliyun_meta_rds_info', to_list=lambda data: data['Items']['DBInstance'])

    def redis_info(self) -> GaugeMetricFamily:
        req = DescribeRedis.DescribeInstancesRequest()
        return self.info_template(req, 'aliyun_meta_redis_info', to_list=lambda data: data['Instances']['KVStoreInstance'])

    def slb_info(self) -> GaugeMetricFamily:
        req = DescribeSLB.DescribeLoadBalancersRequest()
        gauge = self.info_template(req, 'aliyun_meta_slb_info', to_list=lambda data: data['LoadBalancers']['LoadBalancer'])
        gauge_slb_info = None
        for s in gauge.samples:
            slb_id = s.labels['LoadBalancerId']
            req_slb_attr = DescribeSLBAttr.DescribeLoadBalancerAttributeRequest()
            req_slb_attr.set_LoadBalancerId(slb_id)
            slb_attrs_resp = self.client.do_action_with_exception(req_slb_attr)
            slb_attrs_info = json.loads(slb_attrs_resp)
            for protocol_info in slb_attrs_info['ListenerPortsAndProtocol']['ListenerPortAndProtocol']:
                protocol = protocol_info['ListenerProtocol']
                port = protocol_info['ListenerPort']
                req_slb_proto = None
                if protocol == 'tcp':
                    req_slb_proto = DescribeSLBTcpAttr.DescribeLoadBalancerTCPListenerAttributeRequest()
                elif protocol == 'http':
                    req_slb_proto = DescribeSLBHttpAttr.DescribeLoadBalancerHTTPListenerAttributeRequest()
                elif protocol == 'https':
                    req_slb_proto = DescribeSLBHttpsAttr.DescribeLoadBalancerHTTPSListenerAttributeRequest()
                req_slb_proto.set_LoadBalancerId(slb_id)
                req_slb_proto.set_ListenerPort(int(port))
                slb_protocol_resp = self.client.do_action_with_exception(req_slb_proto)
                slb_protocol_info: dict = json.loads(slb_protocol_resp)
                if 'ForwardCode' in slb_protocol_info.keys():
                    continue
                Bandwidth = slb_protocol_info['Bandwidth']
                if gauge_slb_info is None:
                    gauge_slb_info = GaugeMetricFamily('aliyun_meta_slb_proto_bandwidth', 'protocolBandwidth', labels=['instanceId', 'ListenerProtocol', 'ListenerPort'])
                gauge_slb_info.add_metric([slb_id, protocol, str(port)], value=float(Bandwidth))
        return gauge_slb_info

    def mongodb_info(self) -> GaugeMetricFamily:
        req = Mongodb.DescribeDBInstancesRequest()
        return self.info_template(req, 'aliyun_meta_mongodb_info', to_list=lambda data: data['DBInstances']['DBInstance'])

    def cdn_info(self) -> GaugeMetricFamily:
        req = DescribeCDN.DescribeUserDomainsRequest()
        req.set_DomainStatus('online')
        nested_handler = {
            'DomainName': lambda obj: try_or_else(lambda: obj['DomainName'], ''),
        }
        return self.info_template(req, 'aliyun_meta_cdn_info', to_list=lambda data: data['Domains']['PageData'])

    '''
    Template method to retrieve resource information and transform to metric.
    '''
    def info_template(self,
                      req,
                      name,
                      desc='',
                      page_size=100,
                      page_num=1,
                      nested_handler=None,
                      to_list=(lambda data: data['Instances']['Instance'])) -> GaugeMetricFamily:
        gauge = None
        label_keys = None
        for instance in self.pager_generator(req, page_size, page_num, to_list):
            if gauge is None:
                label_keys = self.label_keys(instance, nested_handler)
                gauge = GaugeMetricFamily(name, desc, labels=label_keys)
            gauge.add_metric(labels=self.label_values(instance, label_keys, nested_handler), value=1.0)
        return gauge

    def info_template_bytime(self,
                      req,
                      name,
                      desc='',
                      label_keys=None,
                      nested_handler=None,
                      to_value=(lambda data: data['Instances']['Instance'])) -> GaugeMetricFamily:

        value = self.generator_by_time(req, to_value)
        gauge = GaugeMetricFamily(name, desc, labels=label_keys)
        gauge.add_metric(labels=[value], value=1.0)
        return gauge

    def pager_generator(self, req, page_size, page_num, to_list):
        req.set_PageSize(page_size)
        while True:
            req.set_PageNumber(page_num)
            resp = self.client.do_action_with_exception(req)
            data = json.loads(resp)
            instances = to_list(data)
            for instance in instances:
                if 'test' not in instance.get('DomainName'):
                    yield instance
            if len(instances) < page_size:
                break
            page_num += 1

    def generator_by_time(self, req, to_value):
        now = time.time() - 60
        start_time = datetime.datetime.utcfromtimestamp(now-120).strftime("%Y-%m-%dT%H:%M:%SZ")
        end_time = datetime.datetime.utcfromtimestamp(now).strftime("%Y-%m-%dT%H:%M:%SZ")
        req.set_accept_format('json')
        req.set_StartTime(start_time)
        req.set_EndTime(end_time)
        resp = self.client.do_action_with_exception(req)
        value = to_value(resp)
        return value

    def label_keys(self, instance, nested_handler=None):
        if nested_handler is None:
            nested_handler = {}
        return [k for k, v in instance.items()
                if k in nested_handler or isinstance(v, str) or isinstance(v, int)]

    def label_values(self, instance, label_keys, nested_handler=None):
        if nested_handler is None:
            nested_handler = {}
        return map(lambda k: str(nested_handler[k](instance[k])) if k in nested_handler else try_or_else(lambda: str(instance[k]), ''),
                   label_keys)


