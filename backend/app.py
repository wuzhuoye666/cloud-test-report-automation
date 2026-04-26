"""Flask 应用主程序"""
import os
import sys
import json
import subprocess
import uuid
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory, current_app
from flask_cors import CORS
from werkzeug.utils import secure_filename

from config import config
from models import db, TestData, Report, Analysis

def create_app(config_name='default'):
    """应用工厂函数"""
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    
    # 初始化扩展
    db.init_app(app)
    CORS(app, resources={r"/api/*": {"origins": "*"}})
    
    # 确保目录存在
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)
    
    # 注册路由
    register_routes(app)
    
    # 创建数据库表
    with app.app_context():
        db.create_all()
    
    return app


def register_routes(app):
    """注册路由"""
    
    @app.route('/api/upload', methods=['POST'])
    def upload_data():
        """接收 JSON 测试数据并存入数据库"""
        try:
            data = request.get_json()
            if not data:
                return jsonify({'success': False, 'message': '未收到数据'}), 400
            
            # 获取或生成 task_id
            task_id = data.get('task_id') or f"task_{uuid.uuid4().hex[:12]}"
            label = data.get('label') or data.get('_label')

            # 检查是否已存在
            existing = TestData.query.filter_by(task_id=task_id).first()
            if existing:
                # 更新现有数据
                existing.raw_data = json.dumps(data, ensure_ascii=False)
                if label:
                    existing.label = label
                existing.updated_at = datetime.utcnow()
                db.session.commit()
                return jsonify({
                    'success': True,
                    'message': '数据已更新',
                    'data': existing.to_dict()
                }), 200
            else:
                # 创建新记录
                test_data = TestData(
                    task_id=task_id,
                    label=label,
                    raw_data=json.dumps(data, ensure_ascii=False)
                )
                db.session.add(test_data)
                db.session.commit()
                return jsonify({
                    'success': True,
                    'message': '数据上传成功',
                    'data': test_data.to_dict()
                }), 201
                
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': str(e)}), 500
    
    @app.route('/api/report-data', methods=['GET'])
    def get_report_data():
        """从数据库读取测试数据"""
        try:
            task_id = request.args.get('task_id')
            
            if task_id:
                # 按 task_id 查询
                test_data = TestData.query.filter_by(task_id=task_id).first()
                if not test_data:
                    return jsonify({'success': False, 'message': '未找到数据'}), 404
                return jsonify({
                    'success': True,
                    'data': test_data.to_dict()
                }), 200
            else:
                # 返回所有数据
                all_data = TestData.query.order_by(TestData.created_at.desc()).all()
                return jsonify({
                    'success': True,
                    'data': [td.to_dict() for td in all_data]
                }), 200
                
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 500
    
    @app.route('/api/generate', methods=['POST'])
    def generate_report():
        """调用 generate_report.py 生成报告"""
        try:
            req_data = request.get_json()
            task_id = req_data.get('task_id')
            file_format = req_data.get('format', 'both')  # 'pdf', 'md', 'both'
            
            if not task_id:
                return jsonify({'success': False, 'message': '缺少 task_id'}), 400
            
            # 获取测试数据
            test_data = TestData.query.filter_by(task_id=task_id).first()
            if not test_data:
                return jsonify({'success': False, 'message': '未找到测试数据'}), 404
            
            # 创建临时数据文件
            output_dir = os.path.join(current_app.config['OUTPUT_FOLDER'], task_id)
            os.makedirs(output_dir, exist_ok=True)
            
            data_file = os.path.join(output_dir, 'input_data.json')
            with open(data_file, 'w', encoding='utf-8') as f:
                f.write(test_data.raw_data)
            
            # 调用 generate_report.py
            script_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                'scripts', 'generate_report.py'
            )
            
            cmd = [sys.executable, script_path, '--input', data_file, '--output-dir', output_dir]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                encoding='utf-8',
                errors='replace'
            )
            
            if result.returncode != 0:
                return jsonify({
                    'success': False,
                    'message': '报告生成失败',
                    'error': result.stderr
                }), 500
            
            # 保存报告记录
            reports = []
            
            md_path = os.path.join(output_dir, 'report.md')
            pdf_path = os.path.join(output_dir, 'report.pdf')
            
            if file_format in ['md', 'both'] and os.path.exists(md_path):
                report = Report(
                    test_data_id=test_data.id,
                    filename='report.md',
                    file_type='md',
                    file_path=md_path,
                    file_size=os.path.getsize(md_path)
                )
                db.session.add(report)
                reports.append(report)
            
            if file_format in ['pdf', 'both'] and os.path.exists(pdf_path):
                report = Report(
                    test_data_id=test_data.id,
                    filename='report.pdf',
                    file_type='pdf',
                    file_path=pdf_path,
                    file_size=os.path.getsize(pdf_path)
                )
                db.session.add(report)
                reports.append(report)
            
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': '报告生成成功',
                'reports': [r.to_dict() for r in reports],
                'output_dir': output_dir
            }), 200
            
        except subprocess.TimeoutExpired:
            return jsonify({'success': False, 'message': '报告生成超时'}), 504
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': str(e)}), 500
    
    @app.route('/api/download/<filename>', methods=['GET'])
    def download_file(filename):
        """下载报告文件"""
        try:
            # 安全检查
            filename = secure_filename(filename)
            
            # 支持的目录
            task_id = request.args.get('task_id')
            if task_id:
                directory = os.path.join(current_app.config['OUTPUT_FOLDER'], task_id)
            else:
                directory = current_app.config['OUTPUT_FOLDER']
            
            file_path = os.path.join(directory, filename)
            
            if not os.path.exists(file_path):
                return jsonify({'success': False, 'message': '文件不存在'}), 404
            
            return send_from_directory(
                directory,
                filename,
                as_attachment=True,
                download_name=filename
            )
            
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 500
    
    @app.route('/api/reports', methods=['GET'])
    def get_reports():
        """获取报告列表"""
        try:
            task_id = request.args.get('task_id')
            
            query = Report.query
            if task_id:
                test_data = TestData.query.filter_by(task_id=task_id).first()
                if test_data:
                    query = query.filter_by(test_data_id=test_data.id)
                else:
                    return jsonify({'success': True, 'data': []}), 200
            
            reports = query.order_by(Report.created_at.desc()).all()
            return jsonify({
                'success': True,
                'data': [r.to_dict() for r in reports]
            }), 200
            
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 500
    
    @app.route('/api/report/generate-from-data', methods=['POST', 'OPTIONS'])
    def generate_report_from_data():
        """一站式接口：直接接收 HTML 传来的 JSON 测试数据 → 调用 generate_report.py → 返回下载 URL"""
        if request.method == 'OPTIONS':
            return ('', 204)
        try:
            data = request.get_json(silent=True)
            if not data or not isinstance(data, dict):
                return jsonify({'success': False, 'message': '请求体必须是 JSON 测试数据'}), 400

            task_id = data.get('task_id') or f"task_{uuid.uuid4().hex[:12]}"

            output_dir = os.path.join(current_app.config['OUTPUT_FOLDER'], task_id)
            os.makedirs(output_dir, exist_ok=True)

            data_file = os.path.join(output_dir, 'input_data.json')
            with open(data_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)

            script_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                'scripts', 'generate_report.py'
            )

            result = subprocess.run(
                [sys.executable, script_path, '--input', data_file, '--output-dir', output_dir],
                capture_output=True, text=True, timeout=300,
                encoding='utf-8', errors='replace'
            )

            if result.returncode != 0:
                return jsonify({
                    'success': False,
                    'message': '报告生成失败',
                    'stderr': result.stderr[-1000:],
                    'stdout': result.stdout[-1000:]
                }), 500

            pdf_path = os.path.join(output_dir, 'report.pdf')
            md_path = os.path.join(output_dir, 'report.md')

            return jsonify({
                'success': True,
                'message': '报告生成成功',
                'task_id': task_id,
                'pdf_url': f'/api/download/report.pdf?task_id={task_id}' if os.path.exists(pdf_path) else None,
                'md_url': f'/api/download/report.md?task_id={task_id}' if os.path.exists(md_path) else None,
                'output_dir': output_dir
            }), 200

        except subprocess.TimeoutExpired:
            return jsonify({'success': False, 'message': '报告生成超时(>300s)'}), 504
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 500

    @app.route('/api/health', methods=['GET'])
    def health_check():
        """健康检查"""
        return jsonify({'status': 'ok', 'timestamp': datetime.now().isoformat()}), 200

    @app.route('/api/analysis', methods=['GET'])
    def list_analysis():
        """列出所有对比分析记录。"""
        rows = Analysis.query.order_by(Analysis.created_at.asc()).all()
        return jsonify({
            'success': True,
            'analysis': [r.to_dict() for r in rows]
        }), 200

    @app.route('/api/analysis/<key>', methods=['GET'])
    def get_analysis(key):
        """按 key 取一份对比分析数据。"""
        row = Analysis.query.filter_by(key=key).first()
        if not row:
            return jsonify({'success': False, 'message': f'未找到 analysis key={key}'}), 404
        return jsonify({'success': True, 'data': row.to_dict()}), 200

    @app.route('/api/analysis', methods=['POST'])
    def upload_analysis():
        """写入/更新一份对比分析数据。"""
        try:
            payload = request.get_json(silent=True)
            if not payload or not isinstance(payload, dict):
                return jsonify({'success': False, 'message': '需要 JSON 对象 {key, label?, data}'}), 400
            key = payload.get('key')
            data = payload.get('data')
            if not key or not isinstance(data, dict):
                return jsonify({'success': False, 'message': '缺少 key 或 data'}), 400
            label = payload.get('label')
            raw = json.dumps(data, ensure_ascii=False)
            existing = Analysis.query.filter_by(key=key).first()
            if existing:
                existing.raw_data = raw
                if label:
                    existing.label = label
                existing.updated_at = datetime.utcnow()
            else:
                db.session.add(Analysis(key=key, label=label, raw_data=raw))
            db.session.commit()
            return jsonify({'success': True}), 200
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': str(e)}), 500

    @app.route('/api/datasets', methods=['GET'])
    def get_all_datasets():
        """从数据库返回所有测试数据集，每行 test_data = 一份报告。"""
        rows = TestData.query.order_by(TestData.created_at.asc()).all()
        result = []
        for row in rows:
            data = row.get_data()
            # 兼容 visualizations.raw_details 嵌套结构
            vis = data.get('visualizations', {}) or {}
            if isinstance(vis, dict) and 'raw_details' in vis:
                data['visualizations'] = vis.get('raw_details') or {}
            result.append({
                'label': row.label or row.task_id,
                'task_id': row.task_id,
                'data': data,
            })
        return jsonify({'success': True, 'datasets': result}), 200


# 创建应用实例
app = create_app(os.environ.get('FLASK_ENV', 'default'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
