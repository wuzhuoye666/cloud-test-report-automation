"""把 references/*.json 一次性写入数据库。

用法：
    cd skills/skill_report/backend
    python seed_db.py

幂等：按 task_id 去重，存在则更新 raw_data + label。
"""
import os
import sys
import json

from app import create_app
from models import db, TestData, Analysis

REFERENCES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'references',
)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

SEED_DATASETS = [
    {'label': '阿里云',      'file': 'test-data.json'},
    {'label': '火山云 Ark',  'file': 'ark_lightweight.json'},
]

SEED_ANALYSIS = [
    {
        'key':  'cvm_vs_ark',
        'label':'jvsclaw vs Ark_lightweight',
        # 优先在 references/ 下找，其次到项目根
        # 候选位置：skill_report/references/ 或 项目根(.codebuddy/)
        'paths':[
            os.path.join(REFERENCES_DIR, 'analysis.json'),
            'analysis.json',
        ],
    },
]


def _ensure_label_column():
    """SQLite 上为旧表加 label 列（幂等）。"""
    from sqlalchemy import text
    with db.engine.connect() as conn:
        cols = [r[1] for r in conn.execute(text("PRAGMA table_info(test_data)"))]
        if 'label' not in cols:
            conn.execute(text("ALTER TABLE test_data ADD COLUMN label VARCHAR(100)"))
            conn.commit()
            print("[migrate] 已为 test_data 添加 label 列")


def seed():
    app = create_app()
    with app.app_context():
        db.create_all()
        _ensure_label_column()
        for entry in SEED_DATASETS:
            path = os.path.join(REFERENCES_DIR, entry['file'])
            if not os.path.exists(path):
                print(f"[skip] 找不到 {path}")
                continue
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            task_id = data.get('task_id') or entry['file'].rsplit('.', 1)[0]
            raw_data = json.dumps(data, ensure_ascii=False)

            existing = TestData.query.filter_by(task_id=task_id).first()
            if existing:
                existing.raw_data = raw_data
                existing.label = entry['label']
                action = '更新'
            else:
                db.session.add(TestData(
                    task_id=task_id,
                    label=entry['label'],
                    raw_data=raw_data,
                ))
                action = '插入'
            print(f"[{action}] task_id={task_id}  label={entry['label']}")
        db.session.commit()
        total = TestData.query.count()
        print(f"\ntest_data 共 {total} 行。")

        for entry in SEED_ANALYSIS:
            src_path = None
            for rel in entry['paths']:
                cand = rel if os.path.isabs(rel) else os.path.join(PROJECT_ROOT, rel)
                if os.path.exists(cand):
                    src_path = cand
                    break
            if not src_path:
                print(f"[skip] 找不到 analysis 源文件: {entry['paths']}")
                continue
            with open(src_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            raw = json.dumps(data, ensure_ascii=False)
            existing = Analysis.query.filter_by(key=entry['key']).first()
            if existing:
                existing.raw_data = raw
                existing.label = entry['label']
                action = '更新'
            else:
                db.session.add(Analysis(key=entry['key'], label=entry['label'], raw_data=raw))
                action = '插入'
            print(f"[{action}] analysis key={entry['key']}  label={entry['label']}  src={os.path.relpath(src_path, PROJECT_ROOT)}")
        db.session.commit()
        print(f"analysis 共 {Analysis.query.count()} 行。")


if __name__ == '__main__':
    seed()
