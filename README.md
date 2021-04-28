# 阿里云 Exporter

阿里云云监控的 Prometheus Exporter. 
基于github开源项目，增加了cdn的回源带宽和回源状态码的监控数据抓取。
之后希望可以利用Flask-PluginKit改写成插件式增加/删减metrics。

## 安装

```bash
pip3 install aliyun-exporter
```

## 使用

首先需要在配置文件中写明阿里云的 `Access Key` 以及需要拉取的云监控指标，例子如下：

```yaml
credential:
  access_key_id: <YOUR_ACCESS_KEY_ID>
  access_key_secret: <YOUR_ACCESS_KEY_SECRET>
  region_id: <REGION_ID>

metrics:
  acs_cdn:
  - name: QPS
  acs_mongodb:
  - name: CPUUtilization
    period: 300
```

启动 Exporter

```bash
> aliyun-exporter -p 9525 -c aliyun-exporter.yml
```

访问 [localhost:9525/metrics](http://localhost:9525/metrics) 查看指标抓取是否成功


## Grafana 看板

预配置了一些 Grafana 看板. 见[Screenshots](#screenshots)

## 配置

```yaml
rate_limit: 5 # 限流配置，每秒请求次数. 默认值: 10
credential:
  access_key_id: <YOUR_ACCESS_KEY_ID> # 必填
  access_key_secret: <YOUR_ACCESS_KEY_SECRET> # 必填
  region_id: <REGION_ID> # 默认值: 'cn-hangzhou'
  
metrics: # 必填, 目标指标配置
  acs_cdn: # 必填，云监控中定义的 Project 名字
  - name: QPS # 必填, 云监控中定义的指标名字
    rename: qps # 选填，定义对应的 Prometheus 指标名字，默认与云监控指标名字一致
    period: 60 # 选填，默认 60
    measure: Average # 选填，响应体中的指标值字段名，默认 'Average'
```

提示：

* [云监控-预设监控项参考](https://help.aliyun.com/document_detail/28619.html?spm=a2c4g.11186623.6.670.4cb92ea7URJUmT) 可以查询 Project 与对应的指标
* 云监控 API 有限流，假如被限流了可以调整限流配置
* 云监控 API 每月调用量前 500 万次免费，需要计划好用量

> 假如配置了 50 个指标，再配置 Prometheus 60秒 抓取一次 Exporter，那么 30 天大约会用掉 2,160,000 次请求

## 特殊的 Project

有一些指标没有在云监控 API 中暴露, 为了保持配置的一致性, 我们定义了一些特殊 Project 来配置这些指标.

所有的特殊 Project:

* `rds_performance`: RDS 的详细性能数据, 可选的指标名可以在这里找到: [性能参数表](https://help.aliyun.com/document_detail/26316.html?spm=a2c4g.11186623.4.3.764b2c01QbzUdY)
* `cdn_performance`: CDN 的详细性能数据, 可选的指标名可以在这里找到: [性能参数表](https://help.aliyun.com/document_detail/106661.html?spm=a2c4g.11186623.6.734.175f45c3ZiX4xv)


## 自监控

`cloudmonitor_request_latency_seconds` 和 `cloudmonitor_failed_request_latency_seconds` 中记录了对 CloudMonitor API 的调用情况。

每一个 CloudMonitor 指标都有一个对应的 `aliyun_{project}_{metric}_up` 来表明该指标是否拉取成功。


## 扩展与高可用

假如机器很多，云监控 API 可能比较慢，这时候可以把指标分拆多个 Exporter 实例中去。

HA 和 Prometheus 本身的 HA 方案一样，就是搭完全相同的两套监控。每套部署一台 Prometheus 加上对应的 Exporter。或者直接交给底下的 PaaS 设施来做 Standby。

> 部署两套会导致请求量会翻倍，要注意每月 API 调用量
