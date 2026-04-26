"""数据库模型定义"""
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import json

db = SQLAlchemy()

class TestData(db.Model):
    """测试数据表"""
    __tablename__ = 'test_data'
    
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.String(100), unique=True, nullable=False, index=True)
    label = db.Column(db.String(100))  # 数据集标签，例如 "CVM 内置测试" / "火山云 Ark"
    raw_data = db.Column(db.Text, nullable=False)  # JSON 字符串
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关联的报告
    reports = db.relationship('Report', backref='test_data', lazy=True)

    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'task_id': self.task_id,
            'label': self.label,
            'data': json.loads(self.raw_data) if self.raw_data else {},
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
    
    def get_data(self):
        """获取解析后的 JSON 数据"""
        try:
            return json.loads(self.raw_data)
        except:
            return {}

class Report(db.Model):
    """报告表"""
    __tablename__ = 'reports'
    
    id = db.Column(db.Integer, primary_key=True)
    test_data_id = db.Column(db.Integer, db.ForeignKey('test_data.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    file_type = db.Column(db.String(20), nullable=False)  # 'pdf' 或 'md'
    file_path = db.Column(db.String(500), nullable=False)
    file_size = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'test_data_id': self.test_data_id,
            'filename': self.filename,
            'file_type': self.file_type,
            'file_size': self.file_size,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class Analysis(db.Model):
    """对比分析结果表（A/B 性能对比图表数据）"""
    __tablename__ = 'analysis'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False, index=True)  # 例如 'cvm_vs_ark'
    label = db.Column(db.String(200))  # 例如 'jvsclaw vs Ark_lightweight'
    raw_data = db.Column(db.Text, nullable=False)  # 完整 analysis JSON 字符串
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'key': self.key,
            'label': self.label,
            'data': json.loads(self.raw_data) if self.raw_data else {},
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class TestRecord(db.Model):
    """测试记录表（用于存储解析后的指标数据）"""
    __tablename__ = 'test_records'
    
    id = db.Column(db.Integer, primary_key=True)
    test_data_id = db.Column(db.Integer, db.ForeignKey('test_data.id'), nullable=False)
    category = db.Column(db.String(100), nullable=False)  # 测试类别
    metric_name = db.Column(db.String(255), nullable=False)  # 指标名称
    metric_value = db.Column(db.Float, nullable=False)  # 指标数值
    unit = db.Column(db.String(50))  # 单位
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'category': self.category,
            'metric_name': self.metric_name,
            'metric_value': self.metric_value,
            'unit': self.unit,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }