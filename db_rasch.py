import os

import asyncpg
from aiogram.types.input_file import BufferedInputFile
from asyncpg.pool import Pool
from typing import List, Dict, Optional
from datetime import datetime
import json
import logging
from config import DB_CONFIG  # Your database configuration
import pandas as pd
from io import BytesIO

logger = logging.getLogger(__name__)


class Database:
    _pool: Pool = None

    @classmethod
    async def get_pool(cls) -> Pool:
        """Initialize and return a connection pool"""
        if not cls._pool:
            try:
                ssl_mode = 'require' if os.getenv('RAILWAY_ENVIRONMENT') else None
                cls._pool = await asyncpg.create_pool(
                    **DB_CONFIG,
                    min_size=5,
                    max_size=20,
                    command_timeout=60,
                    server_settings={
                        'application_name': 'rasch_bot',
                        'jit': 'off'  # Better for OLTP workloads
                    }
                )
                logger.info("Database connection pool created")
            except Exception as e:
                logger.error(f"Database connection failed: {e}")
                raise
        return cls._pool

    @classmethod
    async def close(cls):
        """Close all connections in the pool"""
        if cls._pool:
            await cls._pool.close()
            cls._pool = None
            logger.info("Database connection pool closed")


class TestManager:

    @staticmethod
    async def initialize_database():
        """Create required tables if they don't exist"""
        pool = await Database.get_pool()
        async with pool.acquire() as conn:
            try:
                # Check if table exists first
                exists = await conn.fetchval(
                    "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'tests')"
                )

                if not exists:
                    await conn.execute('''
                            CREATE TABLE tests (
                                id SERIAL PRIMARY KEY,
                                test_id VARCHAR(50) UNIQUE NOT NULL,
                                answers_1_35 TEXT NOT NULL,       -- Stores answers for questions 1-35 (e.g., "ABCDE...")
                                answers_36_45 JSONB NOT NULL,     -- Stores structured answers for 36-45
                                status VARCHAR(20) NOT NULL,
                                max_grade INTEGER NOT NULL,
                                created_at TIMESTAMP DEFAULT NOW()
                            );

                            CREATE INDEX idx_tests_test_id ON tests(test_id);
                            CREATE INDEX idx_tests_status ON tests(status);
                        ''')
                    logger.info("Created tests table and indexes")
                else:
                    logger.info("Tests table already exists")
            except Exception as e:
                logger.error(f"Database initialization failed: {e}")
                raise

    @staticmethod
    async def save_single_test(
            test_id: str,
            answers: str,
            status: str,
            max_grade: int
    ) -> bool:
        """
        Save a single test to database with proper 45-question format
        Returns True if successful
        """
        # Validate and parse answers
        try:
            parsed_answers = TestManager._parse_answers(answers)
        except ValueError as e:
            logger.error(f"Invalid answer format for test {test_id}: {e}")
            raise

        pool = await Database.get_pool()
        try:
            async with pool.acquire() as conn:
                result = await conn.execute('''
                        INSERT INTO tests (test_id, answers_1_35, answers_36_45, status, max_grade)
                        VALUES ($1, $2, $3, $4, $5)
                        ON CONFLICT (test_id) DO UPDATE SET
                            answers_1_35 = EXCLUDED.answers_1_35,
                            answers_36_45 = EXCLUDED.answers_36_45,
                            status = EXCLUDED.status,
                            max_grade = EXCLUDED.max_grade,
                            created_at = NOW()
                        RETURNING id
                    ''',
                                            test_id,
                                            parsed_answers['answers_1_35'],
                                            json.dumps(parsed_answers['answers_36_45']),
                                            status,
                                            max_grade)

                if result:
                    logger.info(f"Test {test_id} saved/updated")
                    return True
                return False
        except Exception as e:
            logger.error(f"Error saving test {test_id}: {e}")
            raise

    @staticmethod
    async def bulk_insert_tests(tests: List[Dict]) -> int:
        """
        Bulk insert tests with proper 45-question format
        Returns number of inserted tests
        """
        if not tests:
            return 0

        # Parse all tests first
        parsed_tests = []
        for test in tests:
            try:
                parsed = TestManager._parse_answers(test['answers'])
                parsed_tests.append((
                    test['test_id'],
                    parsed['answers_1_35'],
                    json.dumps(parsed['answers_36_45']),
                    test['status'],
                    test['max_grade']
                ))
            except ValueError as e:
                logger.error(f"Skipping test {test.get('test_id', '?')}: {e}")
                continue

        pool = await Database.get_pool()
        try:
            async with pool.acquire() as conn:
                # Start transaction
                async with conn.transaction():
                    # Use COPY for maximum performance
                    result = await conn.copy_records_to_table(
                        'tests',
                        records=parsed_tests,
                        columns=['test_id', 'answers_1_35', 'answers_36_45', 'status', 'max_grade']
                    )

                    logger.info(f"Bulk inserted {len(parsed_tests)} tests")
                    return len(parsed_tests)
        except Exception as e:
            logger.error(f"Bulk insert failed: {e}")
            raise

    @staticmethod
    def _parse_answers(answer_string: str) -> Dict:
        """
        Parse answer string into structured format for 45 questions
        Format: "ABCD...XYZ;a36;b36;a37;b37;...;a45;b45"
        """
        parts = answer_string.split(';')
        if len(parts) < 21:  # 1 for Q1-35 + 20 for Q36-45 (a36,b36...a45,b45)
            raise ValueError("Invalid answer format. Expected 35 letters + 20 math answers separated by semicolons")

        # Parse Q1-35 (first part before semicolon)
        answers_1_35 = parts[0].strip().upper()
        if len(answers_1_35) != 35:
            raise ValueError(f"Expected 35 letters for Q1-35, got {len(answers_1_35)}")

        # Validate Q1-35 contains only A-F
        valid_letters = {'A', 'B', 'C', 'D', 'E', 'F'}
        for letter in answers_1_35:
            if letter not in valid_letters:
                raise ValueError(f"Invalid answer letter '{letter}'. Only A-F allowed for Q1-35")

        # Parse Q36-45 (remaining parts after semicolon)
        math_parts = parts[1:21]  # Should be exactly 20 parts (a36,b36...a45,b45)
        if len(math_parts) != 20:
            raise ValueError(f"Expected 20 math answers for Q36-45, got {len(math_parts)}")

        answers_36_45 = {}
        for i in range(36, 46):
            a_idx = (i - 36) * 2
            b_idx = a_idx + 1

            answers_36_45[str(i)] = {
                'a': math_parts[a_idx].strip(),
                'b': math_parts[b_idx].strip()
            }

        return {
            'answers_1_35': answers_1_35,
            'answers_36_45': answers_36_45
        }

    @staticmethod
    async def get_test(test_id: str) -> Dict:
        """
        Retrieve a test with parsed answers
        """
        pool = await Database.get_pool()
        try:
            async with pool.acquire() as conn:
                row = await conn.fetchrow('''
                        SELECT test_id, answers_1_35, answers_36_45, status, max_grade
                        FROM tests WHERE test_id = $1
                    ''', test_id)

                if not row:
                    return None

                return {
                    'test_id': row['test_id'],
                    'answers_1_35': row['answers_1_35'],
                    'answers_36_45': json.loads(row['answers_36_45']),
                    'status': row['status'],
                    'max_grade': row['max_grade']
                }
        except Exception as e:
            logger.error(f"Error fetching test {test_id}: {e}")
            raise

    @staticmethod
    async def get_all_tests(limit: int = 100) -> List[dict]:
        """Retrieve all tests from database"""
        pool = await Database.get_pool()
        try:
            async with pool.acquire() as conn:
                records = await conn.fetch(
                    'SELECT test_id, answers, status, max_grade, created_at '
                    'FROM tests ORDER BY created_at DESC LIMIT $1',
                    limit
                )
                return [dict(r) for r in records]
        except Exception as e:
            logger.error(f"Error getting all tests: {e}")
            return []

    @staticmethod
    async def get_all_tests(limit: int = 100) -> List[dict]:
        """Retrieve all tests from database with proper 45-question format"""
        pool = await Database.get_pool()
        try:
            async with pool.acquire() as conn:
                records = await conn.fetch(
                    '''SELECT test_id, answers_1_35, answers_36_45, status, 
                       max_grade, created_at 
                       FROM tests 
                       ORDER BY created_at DESC 
                       LIMIT $1''',
                    limit
                )

                tests = []
                for r in records:
                    test = dict(r)
                    # Combine answers for backward compatibility
                    test['answers'] = (
                            test['answers_1_35'] + ";" +
                            ";".join(
                                f"{v['a']};{v['b']}"
                                for k, v in sorted(
                                    json.loads(test['answers_36_45']).items(),
                                    key=lambda x: int(x[0])
                                )
                            )
                    )
                    tests.append(test)
                return tests

        except Exception as e:
            logger.error(f"Error getting all tests: {e}")
            return []

    @staticmethod
    async def update_test(
            test_id: str,
            status: Optional[str] = None,
            answers: Optional[str] = None,
            max_grade: Optional[int] = None
    ) -> bool:
        """Update test fields"""
        pool = await Database.get_pool()
        updates = []
        params = []

        if status:
            updates.append("status = $1")
            params.append(status)
        if answers:
            updates.append("answers = $1" if not status else f"answers = ${len(params) + 1}")
            params.append(answers)
        if max_grade:
            updates.append("max_grade = $1" if not (status or answers) else f"max_grade = ${len(params) + 1}")
            params.append(max_grade)

        if not updates:
            return False

        query = f"""
            UPDATE tests 
            SET {', '.join(updates)}, created_at = NOW()
            WHERE test_id = ${len(params) + 1}
            RETURNING id
        """
        params.append(test_id)

        try:
            async with pool.acquire() as conn:
                result = await conn.execute(query, *params)
                return bool(result)
        except Exception as e:
            logger.error(f"Error updating test {test_id}: {e}")
            raise

    @staticmethod
    async def delete_test(test_id: str) -> bool:
        """Delete a test by test_id"""
        pool = await Database.get_pool()
        try:
            async with pool.acquire() as conn:
                result = await conn.execute(
                    'DELETE FROM tests WHERE test_id = $1 RETURNING id',
                    test_id
                )
                return bool(result)
        except Exception as e:
            logger.error(f"Error deleting test {test_id}: {e}")
            raise



    @staticmethod
    async def create_user_answers_table(test_id: str) -> bool:
        """
        Create a table for storing user answers for a specific test if it doesn't exist
        Returns True if table exists or was created successfully
        """
        table_name = f"test_{test_id}_answers"
        pool = await Database.get_pool()
        try:
            async with pool.acquire() as conn:
                # Check if table exists
                exists = await conn.fetchval(
                    "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = $1)",
                    table_name
                )

                if not exists:
                    await conn.execute(f"""
                        CREATE TABLE IF NOT EXISTS {table_name} (
                            id SERIAL PRIMARY KEY,
                            user_id BIGINT NOT NULL,
                            first_name TEXT NOT NULL,
                            second_name TEXT NOT NULL,
                            third_name TEXT NOT NULL,
                            region TEXT NOT NULL,
                            answers JSONB NOT NULL,
                            submission_time TIMESTAMP DEFAULT NOW(),
                            UNIQUE(user_id)
                            )
                        """)

                    # Create index
                    await conn.execute(f"""
                        CREATE INDEX IF NOT EXISTS idx_{table_name}_user_id ON {table_name}(user_id)
                        """)

                    logger.info(f"Created new user answers table: {table_name}")
                else:
                    logger.info(f"User answers table already exists: {table_name}")
                return True
        except Exception as e:
            logger.error(f"Error creating/checking user answers table {table_name}: {e}")
            raise

    @staticmethod
    async def save_user_answers(
            test_id: str,
            user_id: int,
            user_data: dict,
            answers: list
    ) -> bool:
        """
        Save user answers to the test-specific table
        Automatically handles existing tables
        Returns True if successful
        """
        table_name = f"test_{test_id}_answers"
        pool = await Database.get_pool()
        try:
            async with pool.acquire() as conn:

                # First ensure table exists (won't recreate if exists)
                await TestManager.create_user_answers_table(test_id)

                # Check if user already has an entry
                existing_entry = await conn.fetchval(
                    f"SELECT 1 FROM {table_name} WHERE user_id = $1",
                    user_id
                )

                if existing_entry:
                    # Update existing entry
                    result = await conn.execute(f"""
                        UPDATE {table_name} SET
                            answers = $1,
                            submission_time = NOW()
                        WHERE user_id = $2
                        RETURNING id
                    """,
                                                json.dumps(answers),
                                                user_id)
                else:
                    # Insert new entry
                    result = await conn.execute(f"""
                        INSERT INTO {table_name} (
                            user_id, first_name, second_name, 
                            third_name, region, answers
                        )
                        VALUES ($1, $2, $3, $4, $5, $6)
                        RETURNING id
                    """,
                                                user_id,
                                                user_data.get('first_name', ''),
                                                user_data.get('second_name', ''),
                                                user_data.get('third_name', ''),
                                                user_data.get('region', ''),
                                                json.dumps(answers)
                                                )

                return bool(result)
        except Exception as e:
            logger.error(f"Error saving answers for user {user_id} in test {test_id}: {e}")
            raise

    @staticmethod
    async def get_test_user_data(test_id: str, user_id: int) -> Optional[dict]:
        """
        Get a specific user's test data from the test answers table
        Returns None if user not found
        """
        table_name = f"test_{test_id}_answers"
        pool = await Database.get_pool()
        try:
            async with pool.acquire() as conn:
                # First check if table exists
                table_exists = await conn.fetchval(
                    "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = $1)",
                    table_name
                )

                if not table_exists:
                    return None

                row = await conn.fetchrow(
                    f"""
                    SELECT 
                        user_id, first_name, second_name, third_name, region,
                        answers, submission_time
                    FROM {table_name}
                    WHERE user_id = $1
                    """,
                    user_id
                )

                if not row:
                    return None

                return {
                    'user_id': row['user_id'],
                    'first_name': row['first_name'],
                    'second_name': row['second_name'],
                    'third_name': row['third_name'],
                    'region': row['region'],
                    'answers': json.loads(row['answers']),
                    'submission_time': row['submission_time']
                }
        except Exception as e:
            logger.error(f"Error getting user {user_id} data from test {test_id}: {e}")
            raise

    @staticmethod
    async def get_all_test_users(test_id: str, limit: int = 100) -> List[dict]:
        """
        Get all users' data from a specific test answers table
        Returns empty list if table doesn't exist
        """
        table_name = f"test_{test_id}_answers"
        pool = await Database.get_pool()
        try:
            async with pool.acquire() as conn:
                # First check if table exists
                table_exists = await conn.fetchval(
                    "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = $1)",
                    table_name
                )

                if not table_exists:
                    return []

                rows = await conn.fetch(
                    f"""
                    SELECT 
                        user_id, first_name, second_name, third_name, region,
                        answers, submission_time
                    FROM {table_name}
                    ORDER BY submission_time ASC
                    LIMIT $1
                    """,
                    limit
                )

                return [{
                    'user_id': row['user_id'],
                    'first_name': row['first_name'],
                    'second_name': row['second_name'],
                    'third_name': row['third_name'],
                    'region': row['region'],
                    'answers': json.loads(row['answers']),
                    'submission_time': row['submission_time']
                } for row in rows]
        except Exception as e:
            logger.error(f"Error getting all users from test {test_id}: {e}")
            raise

    @staticmethod
    async def delete_test_answers_table(test_id: str) -> bool:
        """
        Delete the user answers table for a specific test
        Returns True if table was deleted or didn't exist
        Returns False if deletion failed
        """
        table_name = f"test_{test_id}_answers"
        pool = await Database.get_pool()
        try:
            async with pool.acquire() as conn:
                # First check if table exists
                table_exists = await conn.fetchval(
                    "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = $1)",
                    table_name
                )

                if not table_exists:
                    logger.info(f"Table {table_name} doesn't exist, nothing to delete")
                    return True

                # Drop the table
                await conn.execute(f"DROP TABLE {table_name}")
                logger.info(f"Successfully deleted table {table_name}")
                return True

        except Exception as e:
            logger.error(f"Error deleting table {table_name}: {e}")
            return False

    @staticmethod
    async def export_test_results(test_id: str) -> BufferedInputFile:
        """
        Export test results to Excel file with 1/0 scoring
        Returns InputFile ready to be sent via Telegram
        """
        # Get test correct answers
        test = await TestManager.get_test(test_id)
        if not test:
            raise ValueError("Test not found")

        correct_answers = test['answers_1_35']

        # Get all user answers
        table_name = f"test_{test_id.lower()}_answers"
        pool = await Database.get_pool()

        async with pool.acquire() as conn:
            # Check if table exists
            exists = await conn.fetchval(
                "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = $1)",
                table_name
            )
            if not exists:
                raise ValueError("No submissions for this test yet")

            # Get all user data
            records = await conn.fetch(f"""
                SELECT first_name, second_name, third_name, region, answers
                FROM {table_name}
                ORDER BY second_name, first_name
            """)

        # Process data for Excel - collect ALL users first
        data = []
        count = 1
        for record in records:
            user_answers = json.loads(record['answers'])
            row = {
                '№': count,
                'F.I.O': record['first_name'] + ' ' + record['second_name'] + ' ' + record['third_name'] + ' ' + '(' + record['region'] + ')',
                'Duris': 7
            }
            count += 1
            # Add 1/0 for each question
            for i in range(len(user_answers)):
                question_num = i + 1
                is_correct = (i < len(correct_answers)) and (user_answers[i].upper() == correct_answers[i].upper())
                row[f"{question_num}"] = 1 if is_correct else 0

            data.append(row)

        # Create DataFrame after collecting ALL users
        df = pd.DataFrame(data)
        cols = ['№'] + ['F.I.O'] + ['Duris'] + [f"{i + 1}" for i in range(len(correct_answers))]
        df = df[cols]

        # Create Excel file in memory
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Natijalar')

            # Auto-adjust columns' width
            worksheet = writer.sheets['Natijalar']
            for i, col in enumerate(df.columns):
                max_len = max(df[col].astype(str).map(len).max(), len(col)) + 2
                worksheet.set_column(i, i, max_len)

        output.seek(0)
        return BufferedInputFile(output.getvalue(), filename=f"test_{test_id}_results.xlsx")
# Initialize tables when module is imported
async def initialize_db():
    try:
        await TestManager.create_tables()
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise
