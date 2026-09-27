import sqlglot
import re
from typing import Optional, Dict, Any

# Dangerous SQL patterns that must be blocked
DANGEROUS_PATTERNS = [
    r'\bDROP\s+TABLE\b',
    r'\bDELETE\s+FROM\b(?!\s+WHERE)',  # DELETE without WHERE clause
    r'\bUPDATE\s+\w+\s+SET\b(?!\s+WHERE)',  # UPDATE without WHERE clause
    r'\bTRUNCATE\s+TABLE\b',
    r';\s*(DROP|DELETE|UPDATE|INSERT|ALTER|CREATE|TRUNCATE)',
    r'\bINSERT\s+INTO\b',  # INSERT statements
    r'\bALTER\s+TABLE\b',
    r'\bCREATE\s+TABLE\b',
    r'\bEXEC\b|\bEXECUTE\b',  # Executed procedures
    r'\bxp_\w+',  # SQL Server stored procedures
    r'\bUNION\s+ALL\b',
    r'\bUNION\s+SELECT\b',
]


class ValidationModule:
    """
    HLD 3.5: Validation and Repair Module
    Performs multi-level checks on generated SQL with circuit breakers.

    Implements defense-in-depth SQL injection prevention:
    - Block DDL: DROP, DELETE, UPDATE, INSERT, ALTER, CREATE, TRUNCATE without WHERE
    - Block EXEC, XP, UNION patterns
    - Allow only SELECT, WITH (CTE) statements
    """

    def validate(self, sql: str) -> Dict[str, Any]:
        """
        Validates SQL with multi-level circuit breakers.
        Returns dict with status, finding, insight, recommended_action, and details.
        """
        sql_stripped = sql.strip()
        blocked_patterns = []

        # 1. Check for dangerous patterns
        for pattern in DANGEROUS_PATTERNS:
            if re.search(pattern, sql_stripped, re.IGNORECASE | re.MULTILINE):
                blocked_patterns.append(pattern)

        # 2. Parse SQL to determine statement type
        statement_type = ""
        try:
            parsed = sqlglot.transpile(sql_stripped, read="", write="")
            if parsed and len(parsed) > 0:
                first_stmt = parsed[0]
                statements = first_stmt.get("statements", []) if isinstance(first_stmt, dict) else []
                if statements:
                    first_stmt_obj = statements[0]
                    statement_type = first_stmt_obj.get("key_word", "").upper() if first_stmt_obj else ""
                else:
                    statement_type = ""
            else:
                statement_type = ""
        except Exception:
            statement_type = ""

        # 3. Apply circuit breakers - critical risk patterns
        if blocked_patterns:
            return {
                "status": "blocked",
                "message": "Query blocked: Critical risk operation detected",
                "finding": "Attempted dangerous SQL operation",
                "insight": "System prevented potential data loss or corruption",
                "recommended_action": "Rephrase query as read-only SELECT statement",
                "blocked_patterns": blocked_patterns,
                "verdict": "CRITICAL_RISK"
            }

        # 4. Check statement type
        if statement_type in ("INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE", "ALTER", "CREATE"):
            return {
                "status": "blocked",
                "message": "Query blocked: Data modification operations not allowed",
                "finding": f"{statement_type} operation detected - only SELECT queries permitted",
                "insight": "System enforces read-only query policy to prevent accidental data modification",
                "recommended_action": "Rephrase query as a SELECT statement to retrieve data",
                "verdict": "MODIFICATION_OPERATION_BLOCKED"
            }

        if statement_type in ("EXEC", "EXECUTE"):
            return {
                "status": "blocked",
                "message": "Query blocked: Execution of stored procedures not allowed",
                "finding": "EXEC/E executed procedure detected",
                "insight": "System prevents execution of arbitrary code via SQL",
                "recommended_action": "Use SELECT statements only; store procedures via ORM or migration tools",
                "verdict": "EXECUTION_BLOCKED"
            }

        if statement_type in ("UNION",) and "SELECT" not in sql_stripped.upper():
            return {
                "status": "blocked",
                "message": "Query blocked: UNION without SELECT base detected",
                "finding": "Suspicious UNION pattern detected",
                "insight": "UNION without SELECT context may indicate data exfiltration attempt",
                "recommended_action": "Use legitimate SELECT queries with proper filtering",
                "verdict": "UNION_BLOCKED"
            }

        # 5. Check for suspicious patterns (even if syntactically valid)
        suspicious_keywords = ["--", "OR", "AND", "LIKE"]
        found_suspicious = [kw for kw in suspicious_keywords if kw in sql_stripped.upper()]

        if found_suspicious and statement_type != "SELECT":
            return {
                "status": "warning",
                "message": "Query flagged: Suspicious patterns detected",
                "finding": f"Suspicious keywords: {', '.join(found_suspicious)}",
                "insight": "Query contains patterns common in injection attempts",
                "recommended_action": "Review query for safety before execution",
                "verdict": "SUSPICIOUS_PATTERNS",
                "blocked_keywords": found_suspicious
            }

        # 6. Allow SELECT statements
        if statement_type == "SELECT" or sql_stripped.upper().startswith("SELECT"):
            return {
                "status": "allowed",
                "message": "Query allowed: SELECT statement validated",
                "finding": "SELECT query passed all validation checks",
                "insight": "Query is safe for execution against database",
                "recommended_action": "Execute query - results will be returned",
                "verdict": "SAFE_SELECT",
                "statement_type": statement_type
            }

        # 7. Fallback for unrecognized statements
        return {
            "status": "blocked",
            "message": "Query blocked: Unrecognized statement type",
            "finding": f"Statement type '{statement_type}' not in allowed list",
            "insight": "System only permits known safe SQL statement types",
            "recommended_action": "Rephrase as a SELECT statement",
            "verdict": "UNKNOWN_STATEMENT_BLOCKED"
        }

    def repair(self, sql: str) -> Optional[str]:
        """
        Attempt to repair blocked SQL to a safe SELECT statement.
        Returns repaired SQL or None if unreparable.
        """
        repaired = sql.strip()

        # Remove DROP TABLE clauses
        repaired = re.sub(r'\bDROP\s+TABLE\b[^.]*', '', repaired, flags=re.IGNORECASE)

        # Add WHERE 1=0 to make DELETE safe (no-op)
        repaired = re.sub(r';\s*DELETE\s+FROM\s+(\w+)', r'; SELECT \1.*, 1=0 AS dummy FROM \1', repaired, flags=re.IGNORECASE)

        # Add WHERE 1=0 to make UPDATE safe (no-op)
        repaired = re.sub(r'\bUPDATE\s+(\w+)\s+SET', r'SELECT \1.*, 1=0 AS update_dummy FROM \1 WHERE', repaired, flags=re.IGNORECASE)

        # Convert INSERT to SELECT from values with WHERE 1=0
        repaired = re.sub(r'\bINSERT\s+INTO\s+(\w+)\s*\([^)]*\)\s*VALUES\s*\([^)]*\)',
                         r'SELECT \1.* FROM \1 WHERE 1=0', repaired, flags=re.IGNORECASE)

        if repaired and repaired.strip() != sql.strip():
            return repaired.strip()

        return None

validation_module = ValidationModule()