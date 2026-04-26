# Skill-Info 接口文档

## 本地存储路径

所有下载的文件保存在：
```
skill_info/data/downloads/
```

## 文件名格式

```
{vendor}_{spec}_{machine_id}_{date}.tar.gz

示例：
- qcloud_SA5_test-001_20260115.tar.gz
- aliyun_ecs.g8a.8xlarge_srv-01_20260115.tar.gz
```

## 其他项目调用方式

### 直接文件路径

下载完成后，其他项目可以直接访问：

```python
import os

# 构建路径
data_dir = "../skill_info/data/downloads"
filename = "qcloud_SA5_test-001_20260115.tar.gz"
filepath = os.path.join(data_dir, filename)

# 检查文件存在
if os.path.exists(filepath):
    # 使用文件
    print(f"找到测试数据: {filepath}")
```

### 按规则查找

```python
import os
import glob

def find_test_data(vendor=None, spec=None, date=None):
    """按条件查找测试数据"""
    data_dir = "../skill_info/data/downloads"
    
    pattern = "*.tar.gz"
    if vendor:
        pattern = f"{vendor}_*.tar.gz"
    if spec:
        pattern = f"{vendor}_{spec}_*.tar.gz" if vendor else f"*_*.tar.gz"
    
    files = glob.glob(os.path.join(data_dir, pattern))
    return files

# 示例：查找腾讯云所有数据
files = find_test_data(vendor="qcloud")

# 示例：查找 SA5 规格数据
files = find_test_data(vendor="qcloud", spec="SA5")
```

## 下载命令参考

### CentOS

```bash
scp root@1.2.3.4:/tmp/TENCENTBENCH/20260115/tb_result/xxx.tar.gz \
  skill_info/data/downloads/qcloud_SA5_test-001_20260115.tar.gz
```

### Ubuntu

```bash
# 先远程压缩
ssh ubuntu@1.2.3.4 "cd /tmp/TENCENTBENCH/20260115/tb_result && sudo tar -czvf xxx.tar.gz xxx"

# 再下载
scp ubuntu@1.2.3.4:/tmp/TENCENTBENCH/20260115/tb_result/xxx.tar.gz \
  skill_info/data/downloads/qcloud_SA5_test-001_20260115.tar.gz
```
