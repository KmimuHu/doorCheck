import sqlite3
import os
import time
import uuid
from typing import List, Dict, Optional
from datetime import datetime
from ..utils.paths import get_app_dir
from ..utils.logger import logger


class TestRecordStorage:
    def __init__(self):
        self.db_file = os.path.join(get_app_dir(), 'test_records.db')
        self._init_database()

    def _init_database(self):
        """初始化数据库表"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS test_records (
                id TEXT PRIMARY KEY,
                sn TEXT NOT NULL,
                create_time TEXT NOT NULL,
                update_time TEXT NOT NULL,
                test_type TEXT NOT NULL,
                result TEXT NOT NULL,
                duration REAL,
                steps TEXT
            )
        ''')
        conn.commit()
        conn.close()

    def save_record(self, record: Dict):
        """保存测试记录"""
        try:
            import json
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()

            record_id = record.get('id', str(uuid.uuid4()))
            cursor.execute('''
                INSERT INTO test_records (id, sn, create_time, update_time, test_type, result, duration, steps)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                record_id,
                record.get('device_sn', ''),
                record.get('create_time', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
                record.get('test_time', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
                record.get('test_type', '一键测试'),
                record.get('status', 'failed'),
                record.get('duration', 0),
                json.dumps(record.get('steps', []), ensure_ascii=False)
            ))

            conn.commit()
            conn.close()
            logger.info(f"测试记录已保存: {record.get('device_sn')}")
            return True
        except Exception as e:
            logger.error(f"保存测试记录失败: {e}")
            return False

    def load_all_records(self) -> List[Dict]:
        """加载所有测试记录"""
        try:
            import json
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM test_records ORDER BY update_time DESC')
            rows = cursor.fetchall()
            conn.close()

            records = []
            for row in rows:
                records.append({
                    'id': row[0],
                    'device_sn': row[1],
                    'create_time': row[2],
                    'test_time': row[3],
                    'test_type': row[4],
                    'status': row[5],
                    'status_text': '✅ 通过' if row[5] == 'passed' else '❌ 失败',
                    'duration': row[6],
                    'steps': json.loads(row[7]) if row[7] else []
                })
            return records
        except Exception as e:
            logger.error(f"加载测试记录失败: {e}")
            return []

    def search_records(self, sn_keyword: str = '', status_filter: str = 'all') -> List[Dict]:
        """搜索测试记录"""
        try:
            import json
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()

            query = 'SELECT * FROM test_records WHERE 1=1'
            params = []

            if sn_keyword:
                query += ' AND sn LIKE ?'
                params.append(f'%{sn_keyword}%')

            if status_filter != 'all':
                query += ' AND result = ?'
                params.append(status_filter)

            query += ' ORDER BY update_time DESC'

            cursor.execute(query, params)
            rows = cursor.fetchall()
            conn.close()

            records = []
            for row in rows:
                records.append({
                    'id': row[0],
                    'device_sn': row[1],
                    'create_time': row[2],
                    'test_time': row[3],
                    'test_type': row[4],
                    'status': row[5],
                    'status_text': '✅ 通过' if row[5] == 'passed' else '❌ 失败',
                    'duration': row[6],
                    'steps': json.loads(row[7]) if row[7] else []
                })
            return records
        except Exception as e:
            logger.error(f"搜索测试记录失败: {e}")
            return []

    def delete_record(self, record_id: str) -> bool:
        """删除测试记录"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute('DELETE FROM test_records WHERE id = ?', (record_id,))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"删除测试记录失败: {e}")
            return False

    def clear_all_records(self) -> bool:
        """清空所有测试记录"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute('DELETE FROM test_records')
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"清空测试记录失败: {e}")
            return False
