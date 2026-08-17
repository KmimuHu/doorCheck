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
        """加载所有测试记录（每个SN每个测试项只取最新一条）"""
        try:
            import json
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT t.* FROM test_records t
                INNER JOIN (
                    SELECT sn, test_type, MAX(update_time) as max_time
                    FROM test_records GROUP BY sn, test_type
                ) latest ON t.sn = latest.sn AND t.test_type = latest.test_type AND t.update_time = latest.max_time
                ORDER BY t.update_time DESC
            ''')
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

    def get_records_by_sn(self, sn: str) -> List[Dict]:
        """获取指定设备的所有测试记录"""
        try:
            import json
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM test_records WHERE sn = ? ORDER BY update_time DESC', (sn,))
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
                    'duration': row[6],
                    'steps': json.loads(row[7]) if row[7] else []
                })
            return records
        except Exception as e:
            logger.error(f"获取设备测试记录失败: {e}")
            return []

    def search_records(self, sn_keyword: str = '', status_filter: str = 'all', 
                      start_date: str = '', end_date: str = '') -> List[Dict]:
        """搜索测试记录（每个SN每个测试项只取最新一条）
        
        Args:
            sn_keyword: SN关键字模糊查询
            status_filter: 状态筛选 ('all', 'passed', 'failed')
            start_date: 起始日期 'YYYY-MM-DD' 或 'YYYY-MM-DD HH:MM:SS'
            end_date: 结束日期 'YYYY-MM-DD' 或 'YYYY-MM-DD HH:MM:SS'
        """
        try:
            import json
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()

            where_clauses = []
            params = []

            if sn_keyword:
                where_clauses.append('t.sn LIKE ?')
                params.append(f'%{sn_keyword}%')

            if status_filter != 'all':
                where_clauses.append('t.result = ?')
                params.append(status_filter)

            if start_date:
                # 如果只有日期没有时间，添加00:00:00
                if len(start_date) == 10:
                    start_date = f"{start_date} 00:00:00"
                where_clauses.append('t.update_time >= ?')
                params.append(start_date)

            if end_date:
                # 如果只有日期没有时间，添加23:59:59
                if len(end_date) == 10:
                    end_date = f"{end_date} 23:59:59"
                where_clauses.append('t.update_time <= ?')
                params.append(end_date)

            where_sql = ('WHERE ' + ' AND '.join(where_clauses)) if where_clauses else ''

            query = f'''
                SELECT t.* FROM test_records t
                INNER JOIN (
                    SELECT sn, test_type, MAX(update_time) as max_time
                    FROM test_records GROUP BY sn, test_type
                ) latest ON t.sn = latest.sn AND t.test_type = latest.test_type AND t.update_time = latest.max_time
                {where_sql}
                ORDER BY t.update_time DESC
            '''

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

    def upsert_record(self, record: Dict) -> bool:
        """保存测试记录：存在则更新，不存在则插入（按 sn+test_type 唯一）"""
        try:
            import json
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute('SELECT id FROM test_records WHERE sn = ? AND test_type = ?',
                           (record.get('device_sn', ''), record.get('test_type', '')))
            row = cursor.fetchone()
            steps_json = json.dumps(record.get('steps', []), ensure_ascii=False)
            if row:
                cursor.execute(
                    'UPDATE test_records SET update_time=?, result=?, duration=?, steps=? WHERE id=?',
                    (now, record.get('status', 'failed'), record.get('duration', 0), steps_json, row[0])
                )
            else:
                cursor.execute(
                    'INSERT INTO test_records (id, sn, create_time, update_time, test_type, result, duration, steps) VALUES (?,?,?,?,?,?,?,?)',
                    (str(uuid.uuid4()), record.get('device_sn', ''), now, now,
                     record.get('test_type', ''), record.get('status', 'failed'),
                     record.get('duration', 0), steps_json)
                )
            conn.commit()
            conn.close()
            logger.info(f"测试记录已保存: {record.get('device_sn')} - {record.get('test_type')}")
            return True
        except Exception as e:
            logger.error(f"保存测试记录失败: {e}")
            return False

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
