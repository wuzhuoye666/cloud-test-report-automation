# 厂商配置参数参考

## 厂商标识对照

| 中文名 | 标识 | 规格示例 |
|--------|------|----------|
| 腾讯云 | qcloud | SA5, ITA4, S8 |
| 火山云 | volcengine | ecs.g3i.xlarge |
| 阿里云 | aliyun | ecs.g8a.8xlarge |
| 华为云 | huaweiyun | c7.xlarge.2 |
| 百度云 | bdcloud | bc.g5.xlarge |
| 金山云 | jscloud | km.gn6i.xlarge |
| 微软云 | azure | Standard_D4s_v5 |
| 亚马逊云 | aws | m6i.xlarge |
| 谷歌云 | gcp | n2-standard-4 |

## default.cfg 修改字段

```ini
[name]
tag = {机器ID}          ← 修改为机器标识

[area]
area = {地域代码}        ← 修改为 gz/sh/bj 等

[sold_type]
类型 = {规格名称}        ← 腾讯云用大写，其他用完整规格

[vendor]
厂商 = {厂商标识}        ← 如 qcloud, aliyun 等

[port]
port = 22

[role]
client = 
server = 
other = 
```

## 地域代码

| 地域 | 代码 |
|------|------|
| 广州 | gz |
| 上海 | sh |
| 北京 | bj |
| 南京 | nj |
| 成都 | cd |
| 香港 | hk |
| 新加坡 | sg |

## 测试用例组

| 系统 | 用例组 |
|------|--------|
| CentOS | benchmark.compet_single_centos |
| Ubuntu | benchmark.compet_single |

## 常见问题

1. **AlexNet 报错**: 检查 default.cfg 中的 username/password
2. **Ubuntu 压缩失败**: 手动执行 `tar -czvf {规格}.tar.gz {结果目录}`
3. **权限不足**: 确保 SSH 用户有 sudo 权限
