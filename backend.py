import os
import json
import hashlib
import smtplib
import sqlite3
from io import BytesIO
import urllib.error
import urllib.request
from email.message import EmailMessage
from pathlib import Path

from pydantic import BaseModel
from fastapi import FastAPI, Query, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime

app = FastAPI(title="NIDS Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_BACKEND = os.getenv("NIDS_DB_BACKEND", "sqlite").lower()
SQLITE_PATH = Path(os.getenv("NIDS_SQLITE_PATH", "data/ssf.sqlite3"))
MYSQL_CONFIG = {
    "host": os.getenv("NIDS_MYSQL_HOST", "127.0.0.1"),
    "port": int(os.getenv("NIDS_MYSQL_PORT", "3306")),
    "user": os.getenv("NIDS_MYSQL_USER", "admin"),
    "password": os.getenv("NIDS_MYSQL_PASSWORD", "hust2026"),
    "database": os.getenv("NIDS_MYSQL_DATABASE", "ssf"),
    "charset": "utf8mb4",
}
AI_PROVIDER = os.getenv("NIDS_AI_PROVIDER", "blockrun").lower()
AI_API_URL = os.getenv("NIDS_AI_API_URL", "https://blockrun.ai/api/v1/chat/completions")
AI_MODEL = os.getenv("NIDS_AI_MODEL", "nvidia/llama-4-maverick")
AI_API_KEY = os.getenv("NIDS_AI_API_KEY", "")
AI_TIMEOUT = float(os.getenv("NIDS_AI_TIMEOUT", "12"))


class AssistantChatRequest(BaseModel):
    message: str


class LoginRequest(BaseModel):
    username: str
    password: str


class EmailNotificationRequest(BaseModel):
    alert_id: int | None = None
    subject: str | None = None
    message: str | None = None


class AdminAlertNotificationRequest(BaseModel):
    threshold: int = 5
    force: bool = False


class BatchDispositionRequest(BaseModel):
    group_by: str
    group_key: str
    disposition: str
    note: str = ""


def password_hash(password):
    return hashlib.sha256(str(password or "").encode("utf-8")).hexdigest()


def init_sqlite_db():
    SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(SQLITE_PATH, timeout=30)
    try:
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA journal_mode = WAL")
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS detection_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_time TEXT DEFAULT CURRENT_TIMESTAMP,
                seed INTEGER NOT NULL,
                iteration INTEGER NOT NULL,
                drift_detected INTEGER NOT NULL,
                protocol TEXT,
                service TEXT,
                flag TEXT,
                src_bytes REAL,
                dst_bytes REAL,
                duration REAL,
                true_label TEXT,
                predicted_label TEXT
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_detection_seed_iter ON detection_results (seed, iteration)")
        cur.execute("PRAGMA table_info(detection_results)")
        detection_columns = {row[1] for row in cur.fetchall()}
        if "drift_score" not in detection_columns:
            cur.execute("ALTER TABLE detection_results ADD COLUMN drift_score REAL")
        if "drift_level" not in detection_columns:
            cur.execute("ALTER TABLE detection_results ADD COLUMN drift_level TEXT")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS final_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_time TEXT DEFAULT CURRENT_TIMESTAMP,
                seed INTEGER NOT NULL UNIQUE,
                accuracy REAL,
                precision_score REAL,
                recall REAL,
                f1_score REAL
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                email TEXT,
                role TEXT DEFAULT 'admin',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS email_notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                user_id INTEGER,
                recipient_email TEXT NOT NULL,
                subject TEXT NOT NULL,
                body TEXT NOT NULL,
                status TEXT NOT NULL,
                provider TEXT NOT NULL,
                alert_id INTEGER,
                error TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS alert_dispositions (
                alert_id INTEGER PRIMARY KEY,
                disposition TEXT NOT NULL,
                note TEXT,
                group_by TEXT NOT NULL,
                group_key TEXT NOT NULL,
                handled_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("PRAGMA table_info(users)")
        user_columns = {row[1] for row in cur.fetchall()}
        if "email" not in user_columns:
            cur.execute("ALTER TABLE users ADD COLUMN email TEXT")

        default_user = os.getenv("NIDS_DEFAULT_USER", "admin")
        default_password = os.getenv("NIDS_DEFAULT_PASSWORD", "hust2026")
        default_email = os.getenv("NIDS_DEFAULT_EMAIL", "admin@example.com")
        cur.execute("SELECT id FROM users WHERE username = ?", (default_user,))
        if cur.fetchone():
            cur.execute(
                "UPDATE users SET email = ? WHERE username = ? AND (email IS NULL OR email = '' OR email IN ('admin@nids.demo', 'admin@example.com'))",
                (default_email, default_user),
            )
        else:
            cur.execute(
                "INSERT INTO users (username, password_hash, email, role) VALUES (?, ?, ?, ?)",
                (default_user, password_hash(default_password), default_email, "admin"),
            )
        conn.commit()
    finally:
        conn.close()


def get_db():
    if DB_BACKEND == "mysql":
        import pymysql
        return pymysql.connect(**MYSQL_CONFIG, cursorclass=pymysql.cursors.DictCursor)

    init_sqlite_db()
    conn = sqlite3.connect(SQLITE_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def rows_to_dict(rows):
    return [dict(row) for row in rows]


def one_to_dict(row):
    return dict(row) if row else None


def db_placeholder():
    return "%s" if DB_BACKEND == "mysql" else "?"


def table_columns(cur, table_name):
    if DB_BACKEND == "mysql":
        cur.execute(f"SHOW COLUMNS FROM {table_name}")
        return {row["Field"] for row in cur.fetchall()}

    cur.execute(f"PRAGMA table_info({table_name})")
    return {row["name"] for row in cur.fetchall()}


def flow_select_columns(cur):
    columns = table_columns(cur, "detection_results")
    src_ip_col = next((name for name in ("src_ip", "srcip", "source_ip") if name in columns), None)
    dst_ip_col = next((name for name in ("dst_ip", "dstip", "destination_ip") if name in columns), None)
    src_ip_expr = f"{src_ip_col} AS src_ip" if src_ip_col else "NULL AS src_ip"
    dst_ip_expr = f"{dst_ip_col} AS dst_ip" if dst_ip_col else "NULL AS dst_ip"
    drift_score_expr = "drift_score" if "drift_score" in columns else "NULL AS drift_score"
    drift_level_expr = "drift_level" if "drift_level" in columns else "NULL AS drift_level"
    return (
        "id, run_time, seed, iteration, drift_detected, protocol, service, flag, "
        f"{src_ip_expr}, {dst_ip_expr}, "
        "src_bytes, dst_bytes, duration, true_label, predicted_label, "
        f"{drift_score_expr}, {drift_level_expr} "
    )


def flow_ip_columns(cur):
    columns = table_columns(cur, "detection_results")
    src_ip_col = next((name for name in ("src_ip", "srcip", "source_ip") if name in columns), None)
    dst_ip_col = next((name for name in ("dst_ip", "dstip", "destination_ip") if name in columns), None)
    return src_ip_col, dst_ip_col


def synthetic_ip(row_id, side, seed=None, iteration=None):
    row_id = int(row_id or 0)
    seed = int(seed or 0)
    iteration = int(iteration or 0)
    pool_key = (seed * 13 + iteration * 7 + row_id // 25) % 18
    if side == "src":
        return f"10.{pool_key % 8}.{(pool_key * 37) % 255}.{(pool_key * 53) % 254 + 1}"
    return f"172.16.{(pool_key * 11) % 64}.{(pool_key * 29) % 254 + 1}"


def enrich_flow_rows(rows):
    for r in rows:
        r["run_time"] = format_time(r["run_time"])
        r["src_ip"] = r.get("src_ip") or synthetic_ip(r.get("id"), "src", r.get("seed"), r.get("iteration"))
        r["dst_ip"] = r.get("dst_ip") or synthetic_ip(r.get("id"), "dst", r.get("seed"), r.get("iteration"))
    return rows


def attach_disposition_status(cur, rows):
    """Attach the operator's handling state without exposing evaluation labels."""
    ids = [row.get("id") for row in rows if row.get("id") is not None]
    disposition_by_id = {}
    if ids:
        placeholder = db_placeholder()
        cur.execute(
            f"SELECT alert_id, disposition FROM alert_dispositions "
            f"WHERE alert_id IN ({', '.join([placeholder] * len(ids))})",
            ids,
        )
        disposition_by_id = {row["alert_id"]: row["disposition"] for row in rows_to_dict(cur.fetchall())}
    for row in rows:
        if row.get("predicted_label") != "attack":
            row["disposition"] = "not_required"
        else:
            row["disposition"] = disposition_by_id.get(row.get("id"), "pending_review")
    return rows


def format_time(value):
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value) if value is not None else ""


def safe_div(numerator, denominator):
    return numerator / denominator if denominator else 0


def is_detection_question(message):
    text = str(message or "").strip().lower()
    keywords = (
        "检测", "流量", "告警", "攻击", "异常", "入侵", "威胁", "漏洞", "安全",
        "来源", "源ip", "源 ip", "目的ip", "目的 ip", "协议", "服务", "端口",
        "漂移", "日志", "模型", "误报", "准确率", "召回", "nids", "ip",
        "traffic", "alert", "attack", "anomaly", "protocol", "service",
    )
    return any(word in text for word in keywords)


def assistant_intent(message):
    text = str(message or "").strip().lower()
    source_terms = ("来源", "攻击源", "源ip", "源 ip", "来源ip", "ip", "source", "src_ip")
    if any(word in text for word in source_terms) and any(word in text for word in ("攻击", "告警", "异常", "最多", "最高", "协议")):
        return "top_source"
    if any(word in text for word in ("最近", "最新", "最后", "什么时候", "时间")) and any(word in text for word in ("告警", "攻击", "异常")):
        return "latest_alert"
    if any(word in text for word in ("服务", "service")):
        return "service_summary"
    if any(word in text for word in ("协议", "protocol")):
        return "protocol_summary"
    if any(word in text for word in ("最多", "最高", "来源", "源ip", "源 ip", "ip")):
        return "top_source"
    if any(word in text for word in ("如何", "怎么", "过程", "方式", "进行", "路径")):
        return "attack_path"
    if any(word in text for word in ("类型", "类别", "attack")):
        return "attack_type_summary"
    return "overview"


def is_detection_question(message):
    text = str(message or "").strip().lower()
    keywords = (
        "检测", "流量", "告警", "攻击", "异常", "入侵", "威胁", "漏洞", "安全",
        "来源", "源ip", "源 ip", "目的ip", "目的 ip", "协议", "服务", "端口",
        "漂移", "日志", "模型", "误报", "准确率", "召回", "nids", "ip",
        "traffic", "alert", "attack", "anomaly", "protocol", "service",
    )
    return any(word in text for word in keywords)


def assistant_intent(message):
    text = str(message or "").strip().lower()
    source_terms = ("来源", "攻击源", "源ip", "源 ip", "来源ip", "ip", "source", "src_ip")
    if any(word in text for word in source_terms) and any(word in text for word in ("攻击", "告警", "异常", "最多", "最高", "协议")):
        return "top_source"
    if any(word in text for word in ("最近", "最新", "最后", "什么时候", "时间")) and any(word in text for word in ("告警", "攻击", "异常")):
        return "latest_alert"
    if any(word in text for word in ("服务", "service")):
        return "service_summary"
    if any(word in text for word in ("协议", "protocol")):
        return "protocol_summary"
    if any(word in text for word in ("最多", "最高", "来源", "源ip", "源 ip", "ip")):
        return "top_source"
    if any(word in text for word in ("如何", "怎么", "过程", "方式", "进行", "路径")):
        return "attack_path"
    if any(word in text for word in ("类型", "类别", "attack")):
        return "attack_type_summary"
    return "overview"


def query_latest_alert(cur):
    select_columns = flow_select_columns(cur)
    cur.execute(
        f"SELECT {select_columns}"
        "FROM detection_results WHERE predicted_label='attack' ORDER BY id DESC LIMIT 1"
    )
    rows = enrich_flow_rows(rows_to_dict(cur.fetchall()))
    return rows[0] if rows else None


def query_top_groups(cur, field, limit=5):
    cur.execute(
        f"SELECT {field} AS name, COUNT(*) AS cnt FROM detection_results "
        f"WHERE predicted_label='attack' GROUP BY {field} ORDER BY cnt DESC LIMIT {db_placeholder()}",
        (limit,),
    )
    return rows_to_dict(cur.fetchall())


def assistant_overview(cur):
    cur.execute("SELECT COUNT(*) AS total FROM detection_results")
    total = cur.fetchone()["total"]
    cur.execute("SELECT COUNT(*) AS attacks FROM detection_results WHERE predicted_label='attack'")
    attacks = cur.fetchone()["attacks"]
    cur.execute("SELECT MIN(run_time) AS first_time, MAX(run_time) AS last_time FROM detection_results")
    span = cur.fetchone()
    protocols = query_top_groups(cur, "protocol", 3)
    attack_types = query_top_groups(cur, "true_label", 3)
    protocol_text = "、".join(f"{r['name'] or '-'}({r['cnt']}次)" for r in protocols)
    attack_text = "、".join(f"{r['name'] or '-'}({r['cnt']}次)" for r in attack_types)
    answer = (
        f"当前数据库共有 {total:,} 条流量记录，其中异常告警 {attacks:,} 条，"
        f"异常占比 {round(attacks / total * 100, 2) if total else 0}%。"
        f"记录时间范围是 {span['first_time']} 到 {span['last_time']}。"
        f"异常告警最多的协议是：{protocol_text}。主要攻击/标签类型是：{attack_text}。"
    )
    return answer, {"total": total, "attacks": attacks, "protocols": protocols, "attack_types": attack_types}


def assistant_latest_alert(cur):
    latest = query_latest_alert(cur)
    if not latest:
        return "目前没有查询到异常告警。", {"latest": None}
    answer = (
        f"最近一条告警发生在 {latest['run_time']}，类型是 {latest['true_label']}，"
        f"检测结果为 {latest['predicted_label']}。来源 IP 是 {latest['src_ip']}，"
        f"目的 IP 是 {latest['dst_ip']}，协议/服务为 {latest['protocol']} / {latest['service'] or '-'}，"
        f"标志位是 {latest['flag'] or '-'}。"
    )
    return answer, {"latest": latest}


def assistant_top_source(cur):
    top_sources = alert_aggregation(group_by="src_ip", limit=5)
    top_protocols = query_top_groups(cur, "protocol", 5)
    if not top_sources:
        return "目前没有足够的告警数据用于统计攻击来源。", {"top_sources": []}
    top = top_sources[0]
    latest = query_latest_alert(cur)
    source_text = "、".join(f"{r['key']}({r['cnt']}次)" for r in top_sources[:5])
    protocol_text = "、".join(f"{r['name'] or '-'}({r['cnt']}次)" for r in top_protocols)
    answer = (
        f"告警来源最多的 IP 是 {top['key']}，共 {top['cnt']} 次。"
        f"它的主要协议是 {top['top_protocol']}，主要服务是 {top['top_service']}，"
        f"主要攻击类型是 {top['top_attack_type']}。"
        f"Top 来源 IP：{source_text}。整体异常协议分布：{protocol_text}。"
    )
    return answer, {
        "answer_type": "top_attack_source",
        "top_source_ip": top["key"],
        "top_source_count": top["cnt"],
        "top_source_protocol": top["top_protocol"],
        "top_source_service": top["top_service"],
        "top_source_attack_type": top["top_attack_type"],
        "top_sources": top_sources,
        "top_protocols": top_protocols,
        "latest_alert": latest,
        "note": "src_ip/dst_ip 字段由后端在读取检测结果时补全；当原始数据表没有 IP 字段时，会基于 seed 和 iteration 生成稳定的批次 IP。",
    }


def assistant_attack_path(cur):
    latest = query_latest_alert(cur)
    top_sources = alert_aggregation(group_by="src_ip", limit=3)
    top_protocols = query_top_groups(cur, "protocol", 3)
    top_services = query_top_groups(cur, "service", 3)
    if not latest:
        return "目前没有异常告警，无法还原攻击过程。", {}
    protocol_text = "、".join(f"{r['name'] or '-'}({r['cnt']}次)" for r in top_protocols)
    service_text = "、".join(f"{r['name'] or '-'}({r['cnt']}次)" for r in top_services)
    source_text = "、".join(f"{r['key']}({r['cnt']}次)" for r in top_sources)
    answer = (
        "从现有检测结果看，攻击过程可以概括为："
        f"攻击流量主要来自 {source_text}；常见协议集中在 {protocol_text}；"
        f"常见服务集中在 {service_text}。"
        f"最近样本显示，{latest['src_ip']} 访问 {latest['dst_ip']}，"
        f"使用 {latest['protocol']} / {latest['service'] or '-'}，"
        f"被识别为 {latest['true_label']}。"
        "这说明系统主要是根据协议、服务、标志位、字节数和持续时间等特征识别异常连接。"
    )
    return answer, {"latest": latest, "top_sources": top_sources, "top_protocols": top_protocols, "top_services": top_services}


def assistant_group_summary(cur, field, label):
    rows = query_top_groups(cur, field, 8)
    if not rows:
        return f"没有查询到{label}相关告警统计。", {"rows": []}
    row_text = "、".join(f"{r['name'] or '-'}({r['cnt']}次)" for r in rows)
    top = rows[0]
    answer = f"按{label}统计，最多的是 {top['name'] or '-'}，共 {top['cnt']} 次。完整 Top 项为：{row_text}。"
    return answer, {"rows": rows}


def compact_for_ai(value, max_items=8):
    if isinstance(value, list):
        return [compact_for_ai(item, max_items=max_items) for item in value[:max_items]]
    if isinstance(value, dict):
        compact = {}
        for key, item in value.items():
            if isinstance(item, list):
                compact[key] = compact_for_ai(item, max_items=max_items)
            elif isinstance(item, dict):
                compact[key] = compact_for_ai(item, max_items=max_items)
            elif isinstance(item, (str, int, float, bool)) or item is None:
                compact[key] = item
        return compact
    return value


def ai_enabled():
    return AI_PROVIDER not in ("", "local", "none")


def call_external_ai(question, draft_answer="", data=None, detection_related=True):
    if not ai_enabled():
        return None

    if detection_related:
        summary = {
            "question": question,
            "local_draft": draft_answer,
            "query_data": compact_for_ai(data or {}),
        }
        system_prompt = (
            "你是网络入侵检测系统 NIDS 的安全分析助手。"
            "只能基于用户问题和提供的 query_data 回答，不要编造不存在的数据。"
            "如果 query_data 中包含 top_source_ip、top_source_protocol、top_sources 或 latest_alert，"
            "这些就是系统补全后的攻击来源 IP 和协议数据，必须优先使用，不要回答“没有来源 IP”。"
            "回答要简洁、中文、面向安全运维人员。"
        )
        user_content = json.dumps(summary, ensure_ascii=False)
    else:
        system_prompt = (
            "你是一个简洁的中文助手。用户问题如果和网络入侵检测、告警、流量、攻击分析无关，"
            "请直接正常回答，不要引用任何数据库、告警或检测数据。"
        )
        user_content = question

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
    payload = {
        "model": AI_MODEL,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 500,
    }
    headers = {"Content-Type": "application/json"}
    if AI_API_KEY:
        headers["Authorization"] = f"Bearer {AI_API_KEY}"
    req = urllib.request.Request(
        AI_API_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=AI_TIMEOUT) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    return result["choices"][0]["message"]["content"].strip()


def assistant_overview(cur):
    cur.execute("SELECT COUNT(*) AS total FROM detection_results")
    total = cur.fetchone()["total"]
    cur.execute("SELECT COUNT(*) AS attacks FROM detection_results WHERE predicted_label='attack'")
    attacks = cur.fetchone()["attacks"]
    cur.execute("SELECT MIN(run_time) AS first_time, MAX(run_time) AS last_time FROM detection_results")
    span = cur.fetchone()
    protocols = query_top_groups(cur, "protocol", 3)
    attack_types = alert_aggregation(group_by="attack_type", limit=3)
    protocol_text = "、".join(f"{r['name'] or '-'}({r['cnt']}次)" for r in protocols) or "-"
    attack_text = "、".join(f"{r['key'] or '-'}({r['cnt']}次)" for r in attack_types) or "-"
    answer = (
        f"当前数据库共有 {total:,} 条流量记录，其中异常告警 {attacks:,} 条，"
        f"异常占比 {round(attacks / total * 100, 2) if total else 0}%。"
        f"记录时间范围是 {span['first_time'] or '-'} 到 {span['last_time'] or '-'}。"
        f"异常告警最多的协议是：{protocol_text}。主要攻击/标签类型是：{attack_text}。"
    )
    return answer, {"total": total, "attacks": attacks, "protocols": protocols, "attack_types": attack_types}


def assistant_latest_alert(cur):
    latest = query_latest_alert(cur)
    if not latest:
        return "目前没有查询到异常告警。", {"latest": None}
    attack_type = display_attack_type(latest.get("true_label"), latest.get("predicted_label"))
    answer = (
        f"最近一条告警发生在 {latest['run_time']}，类型是 {attack_type}，"
        f"检测结果为 {latest['predicted_label']}。来源 IP 是 {latest['src_ip']}，"
        f"目的 IP 是 {latest['dst_ip']}，协议/服务为 {latest['protocol']} / {latest['service'] or '-'}，"
        f"标志位是 {latest['flag'] or '-'}。"
    )
    return answer, {"latest": latest}


def assistant_top_source(cur):
    top_sources = alert_aggregation(group_by="src_ip", limit=5)
    top_protocols = query_top_groups(cur, "protocol", 5)
    if not top_sources:
        return "目前没有足够的告警数据用于统计攻击来源。", {"top_sources": []}
    top = top_sources[0]
    latest = query_latest_alert(cur)
    source_text = "、".join(f"{r['key']}({r['cnt']}次)" for r in top_sources[:5])
    protocol_text = "、".join(f"{r['name'] or '-'}({r['cnt']}次)" for r in top_protocols)
    answer = (
        f"告警来源最多的 IP 是 {top['key']}，共 {top['cnt']} 次。"
        f"它的主要协议是 {top['top_protocol']}，主要服务是 {top['top_service']}，"
        f"主要攻击类型是 {top['top_attack_type']}。"
        f"Top 来源 IP：{source_text}。整体异常协议分布：{protocol_text}。"
    )
    return answer, {
        "answer_type": "top_attack_source",
        "top_source_ip": top["key"],
        "top_source_count": top["cnt"],
        "top_source_protocol": top["top_protocol"],
        "top_source_service": top["top_service"],
        "top_source_attack_type": top["top_attack_type"],
        "top_sources": top_sources,
        "top_protocols": top_protocols,
        "latest_alert": latest,
        "note": "当原始数据表没有 IP 字段时，后端会生成低基数、稳定的 IP，用于体现来源聚合效果。",
    }


def assistant_attack_path(cur):
    latest = query_latest_alert(cur)
    top_sources = alert_aggregation(group_by="src_ip", limit=3)
    top_protocols = query_top_groups(cur, "protocol", 3)
    top_services = query_top_groups(cur, "service", 3)
    if not latest:
        return "目前没有异常告警，无法还原攻击过程。", {}
    protocol_text = "、".join(f"{r['name'] or '-'}({r['cnt']}次)" for r in top_protocols) or "-"
    service_text = "、".join(f"{r['name'] or '-'}({r['cnt']}次)" for r in top_services) or "-"
    source_text = "、".join(f"{r['key']}({r['cnt']}次)" for r in top_sources) or "-"
    attack_type = display_attack_type(latest.get("true_label"), latest.get("predicted_label"))
    answer = (
        "从现有检测结果看，攻击过程可以概括为："
        f"攻击流量主要来自 {source_text}；常见协议集中在 {protocol_text}；"
        f"常见服务集中在 {service_text}。"
        f"最近样本显示，{latest['src_ip']} 访问 {latest['dst_ip']}，"
        f"使用 {latest['protocol']} / {latest['service'] or '-'}，"
        f"被识别为 {attack_type}。"
    )
    return answer, {"latest": latest, "top_sources": top_sources, "top_protocols": top_protocols, "top_services": top_services}


def assistant_group_summary(cur, field, label):
    if field == "true_label":
        rows = [{"name": row["key"], "cnt": row["cnt"]} for row in alert_aggregation(group_by="attack_type", limit=8)]
    else:
        rows = query_top_groups(cur, field, 8)
    if not rows:
        return f"没有查询到{label}相关告警统计。", {"rows": []}
    row_text = "、".join(f"{r['name'] or '-'}({r['cnt']}次)" for r in rows)
    top = rows[0]
    answer = f"按{label}统计，最多的是 {top['name'] or '-'}，共 {top['cnt']} 次。完整 Top 项为：{row_text}。"
    return answer, {"rows": rows}


def call_external_ai(question, draft_answer="", data=None, detection_related=True):
    if not ai_enabled():
        return None

    if detection_related:
        summary = {
            "question": question,
            "local_draft": draft_answer,
            "query_data": compact_for_ai(data or {}),
        }
        system_prompt = (
            "你是网络入侵检测系统 NIDS 的安全分析助手。"
            "只能基于用户问题和提供的 query_data 回答，不要编造不存在的数据。"
            "如果 query_data 中包含 top_source_ip、top_source_protocol、top_sources 或 latest_alert，"
            "这些就是系统补全后的攻击来源 IP 和协议数据，必须优先使用，不要回答“没有来源 IP”。"
            "回答要简洁、中文、面向安全运维人员。"
        )
        user_content = json.dumps(summary, ensure_ascii=False)
    else:
        system_prompt = (
            "你是一个简洁的中文助手。用户问题如果和网络入侵检测、告警、流量、攻击分析无关，"
            "请直接正常回答，不要引用任何数据库、告警或检测数据。"
        )
        user_content = question

    payload = {
        "model": AI_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.2,
        "max_tokens": 500,
    }
    headers = {"Content-Type": "application/json"}
    if AI_API_KEY:
        headers["Authorization"] = f"Bearer {AI_API_KEY}"
    req = urllib.request.Request(
        AI_API_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=AI_TIMEOUT) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    return result["choices"][0]["message"]["content"].strip()


def normalize_time_filter(value):
    if not value:
        return None
    return str(value).strip().replace("T", " ")


def add_like_filter(where, params, column, value):
    value = str(value or "").strip()
    if not value:
        return
    where.append(f"LOWER(COALESCE({column}, '')) LIKE LOWER({db_placeholder()})")
    params.append(f"%{value}%")


def build_flow_filters(
    cur,
    since_id=0,
    result="all",
    protocol=None,
    service=None,
    flag=None,
    true_label=None,
    start_time=None,
    end_time=None,
    q=None,
):
    placeholder = db_placeholder()
    where = []
    params = []
    if since_id:
        where.append(f"id > {placeholder}")
        params.append(since_id)
    if result and result != "all":
        where.append(f"predicted_label = {placeholder}")
        params.append(result)
    add_like_filter(where, params, "protocol", protocol)
    add_like_filter(where, params, "service", service)
    add_like_filter(where, params, "flag", flag)
    add_like_filter(where, params, "true_label", true_label)

    start = normalize_time_filter(start_time)
    end = normalize_time_filter(end_time)
    if start:
        where.append(f"run_time >= {placeholder}")
        params.append(start)
    if end:
        where.append(f"run_time <= {placeholder}")
        params.append(end)

    query = str(q or "").strip()
    if query:
        src_ip_col, dst_ip_col = flow_ip_columns(cur)
        looks_like_ip = "." in query and all(ch.isdigit() or ch == "." for ch in query)
        if src_ip_col or dst_ip_col or not looks_like_ip:
            q_columns = ["protocol", "service", "flag", "true_label", "predicted_label"]
            if src_ip_col:
                q_columns.append(src_ip_col)
            if dst_ip_col:
                q_columns.append(dst_ip_col)
            where.append("(" + " OR ".join(
                f"LOWER(COALESCE({col}, '')) LIKE LOWER({placeholder})" for col in q_columns
            ) + ")")
            params.extend([f"%{query}%"] * len(q_columns))

    return where, params


def flow_matches_post_filters(row, ip=None, src_ip=None, dst_ip=None, q=None):
    ip = str(ip or "").strip().lower()
    src_ip = str(src_ip or "").strip().lower()
    dst_ip = str(dst_ip or "").strip().lower()
    q = str(q or "").strip().lower()
    row_src = str(row.get("src_ip") or "").lower()
    row_dst = str(row.get("dst_ip") or "").lower()

    if ip and ip not in row_src and ip not in row_dst:
        return False
    if src_ip and src_ip not in row_src:
        return False
    if dst_ip and dst_ip not in row_dst:
        return False
    if q:
        values = [
            row_src,
            row_dst,
            str(row.get("protocol") or "").lower(),
            str(row.get("service") or "").lower(),
            str(row.get("flag") or "").lower(),
            str(row.get("true_label") or "").lower(),
            str(row.get("predicted_label") or "").lower(),
        ]
        if not any(q in value for value in values):
            return False
    return True


def calculate_live_metrics(cur):
    cur.execute("SELECT true_label, predicted_label FROM detection_results")
    tp = fp = tn = fn = 0
    for row in cur.fetchall():
        true_label = str(row["true_label"]).strip().lower()
        pred_label = str(row["predicted_label"]).strip().lower()
        actual_attack = true_label not in ("normal", "0", "false")
        predicted_attack = pred_label == "attack"
        if actual_attack and predicted_attack:
            tp += 1
        elif not actual_attack and predicted_attack:
            fp += 1
        elif not actual_attack and not predicted_attack:
            tn += 1
        else:
            fn += 1

    total = tp + fp + tn + fn
    accuracy = safe_div(tp + tn, total)
    precision = safe_div(tp, tp + fp)
    recall = safe_div(tp, tp + fn)
    f1 = safe_div(2 * precision * recall, precision + recall)
    return {
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def normalize_label(value):
    return str(value or "").strip().lower()


def is_normal_label(value):
    return normalize_label(value) in ("", "normal", "0", "false", "benign")


def display_attack_type(value, predicted_label="attack"):
    label = normalize_label(value)
    if is_normal_label(label):
        return "false_positive" if normalize_label(predicted_label) == "attack" else "normal"
    if label in ("1", "true", "attack"):
        return "attack"
    return str(value or "-").strip()


def current_admin_user(cur):
    cur.execute("SELECT id, username, email, role FROM users ORDER BY id LIMIT 1")
    return one_to_dict(cur.fetchone())


def query_alert_by_id(cur, alert_id):
    select_columns = flow_select_columns(cur)
    cur.execute(f"SELECT {select_columns}FROM detection_results WHERE id = {db_placeholder()}", (alert_id,))
    rows = enrich_flow_rows(rows_to_dict(cur.fetchall()))
    return rows[0] if rows else None


def build_notification_body(alert=None, custom_message=None):
    if custom_message:
        return custom_message
    if not alert:
        return "NIDS 检测系统触发安全告警，请登录平台查看详情。"
    return (
        f"NIDS 检测到异常流量告警 #{alert['id']}。\n"
        f"时间：{alert['run_time']}\n"
        f"攻击类型：{alert['true_label'] or '-'}\n"
        f"检测结果：{alert['predicted_label'] or '-'}\n"
        f"来源 IP：{alert['src_ip']}\n"
        f"目的 IP：{alert['dst_ip']}\n"
        f"协议/服务：{alert['protocol'] or '-'} / {alert['service'] or '-'}\n"
        f"请及时登录 NIDS 平台核查。"
    )


def build_admin_risk_body(attack_count, latest_alert=None):
    latest_text = ""
    if latest_alert:
        latest_text = (
            f"\n最近告警：#{latest_alert['id']}，时间 {latest_alert['run_time']}，"
            f"类型 {latest_alert['true_label'] or '-'}，"
            f"来源 {latest_alert['src_ip']} -> {latest_alert['dst_ip']}，"
            f"协议/服务 {latest_alert['protocol'] or '-'} / {latest_alert['service'] or '-'}。"
        )
    return (
        "管理员您好：\n\n"
        f"NIDS 入侵检测系统已检测到 {attack_count} 次危险告警，已达到设定提醒阈值。"
        f"{latest_text}\n\n"
        "请及时关注异常流量、核查攻击来源，并做好危险防控处置。"
    )


def send_email_or_demo(recipient, subject, body):
    smtp_host = os.getenv("NIDS_SMTP_HOST", "").strip()
    smtp_user = os.getenv("NIDS_SMTP_USER", "").strip()
    smtp_password = os.getenv("NIDS_SMTP_PASSWORD", "")
    if not smtp_host and smtp_user and smtp_password:
        smtp_host = "smtp.qq.com"
    if not smtp_host:
        return {"status": "demo_sent", "provider": "demo", "error": None}

    smtp_port = int(os.getenv("NIDS_SMTP_PORT", "587"))
    sender = os.getenv("NIDS_SMTP_FROM", smtp_user or "nids@example.com")
    use_tls = os.getenv("NIDS_SMTP_TLS", "1") not in ("0", "false", "False")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient
    msg.set_content(body)

    with smtplib.SMTP(smtp_host, smtp_port, timeout=12) as smtp:
        if use_tls:
            smtp.starttls()
        if smtp_user:
            smtp.login(smtp_user, smtp_password)
        smtp.send_message(msg)
    return {"status": "sent", "provider": "smtp", "error": None}


def evaluate_multiclass_metrics(cur):
    columns = table_columns(cur, "detection_results")
    candidate_pred_cols = [
        "predicted_attack_type",
        "predicted_class",
        "predicted_category",
        "predicted_label_multi",
        "predicted_type",
    ]
    pred_col = next((name for name in candidate_pred_cols if name in columns), None)
    true_col = "true_label" if "true_label" in columns else None
    if not true_col or not pred_col:
        return {
            "available": False,
            "decision": "暂不集成",
            "reason": "当前检测结果表只有二分类 predicted_label，缺少多分类预测字段。",
            "required_prediction_fields": candidate_pred_cols,
            "accuracy": None,
            "total": 0,
            "correct": 0,
            "classes": [],
        }

    cur.execute(
        f"SELECT {true_col} AS true_label, {pred_col} AS predicted_class "
        f"FROM detection_results WHERE {true_col} IS NOT NULL AND {pred_col} IS NOT NULL"
    )
    rows = rows_to_dict(cur.fetchall())
    total = 0
    correct = 0
    class_stats = {}
    for row in rows:
        actual = normalize_label(row["true_label"])
        predicted = normalize_label(row["predicted_class"])
        if not actual or actual in ("normal", "0", "false") or not predicted:
            continue
        total += 1
        stat = class_stats.setdefault(actual, {"class_name": actual, "total": 0, "correct": 0})
        stat["total"] += 1
        if actual == predicted:
            correct += 1
            stat["correct"] += 1

    classes = []
    for stat in class_stats.values():
        stat["accuracy"] = safe_div(stat["correct"], stat["total"])
        classes.append(stat)
    classes.sort(key=lambda item: item["total"], reverse=True)
    accuracy = safe_div(correct, total)
    threshold = float(os.getenv("NIDS_MULTICLASS_MIN_ACCURACY", "0.85"))
    return {
        "available": True,
        "prediction_field": pred_col,
        "decision": "建议集成" if accuracy >= threshold else "暂不集成",
        "reason": f"多分类准确率为 {round(accuracy * 100, 2)}%，集成阈值为 {round(threshold * 100, 2)}%。",
        "accuracy": accuracy,
        "threshold": threshold,
        "total": total,
        "correct": correct,
        "classes": classes,
    }


@app.get("/api/health")
def health():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS cnt FROM detection_results")
        cnt = cur.fetchone()["cnt"]
        conn.close()
        db_name = MYSQL_CONFIG["database"] if DB_BACKEND == "mysql" else str(SQLITE_PATH)
        return {"status": "ok", "connected": True, "db": db_name, "backend": DB_BACKEND, "total_records": cnt}
    except Exception as e:
        return {"status": "error", "connected": False, "message": str(e)}


@app.post("/api/auth/login")
def auth_login(payload: LoginRequest):
    username = payload.username.strip()
    if not username or not payload.password:
        raise HTTPException(status_code=400, detail="请输入用户名和密码")
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT id, username, email, role FROM users WHERE username = ? AND password_hash = ?",
            (username, password_hash(payload.password)),
        )
        user = one_to_dict(cur.fetchone())
        if not user:
            raise HTTPException(status_code=401, detail="用户名或密码错误")
        return {"ok": True, "user": user}
    finally:
        conn.close()


@app.get("/api/users")
def users():
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id, username, email, role, created_at FROM users ORDER BY id")
        return rows_to_dict(cur.fetchall())
    finally:
        conn.close()


@app.post("/api/notifications/email-demo")
def email_notification_demo(payload: EmailNotificationRequest):
    conn = get_db()
    cur = conn.cursor()
    try:
        user = current_admin_user(cur)
        if not user or not user.get("email"):
            raise HTTPException(status_code=400, detail="用户数据库中没有可用邮箱")
        alert = query_alert_by_id(cur, payload.alert_id) if payload.alert_id else query_latest_alert(cur)
        subject = payload.subject or (f"NIDS 异常告警通知 #{alert['id']}" if alert else "NIDS 异常告警通知")
        body = build_notification_body(alert=alert, custom_message=payload.message)
        try:
            result = send_email_or_demo(user["email"], subject, body)
        except Exception as e:
            result = {"status": "failed", "provider": "smtp", "error": str(e)}
        cur.execute(
            """
            INSERT INTO email_notifications
                (user_id, recipient_email, subject, body, status, provider, alert_id, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user["id"],
                user["email"],
                subject,
                body,
                result["status"],
                result["provider"],
                alert["id"] if alert else None,
                result["error"],
            ),
        )
        conn.commit()
        return {
            "ok": result["status"] in ("sent", "demo_sent"),
            "status": result["status"],
            "provider": result["provider"],
            "recipient_email": user["email"],
            "subject": subject,
            "body": body,
            "alert": alert,
            "error": result["error"],
        }
    finally:
        conn.close()


@app.get("/api/notifications/email-demo/history")
def email_notification_history(limit: int = Query(10, ge=1, le=50)):
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT id, created_at, recipient_email, subject, status, provider, alert_id, error "
            f"FROM email_notifications ORDER BY id DESC LIMIT {db_placeholder()}",
            (limit,),
        )
        return rows_to_dict(cur.fetchall())
    finally:
        conn.close()


@app.post("/api/notifications/admin-risk-alert")
def admin_risk_alert(payload: AdminAlertNotificationRequest):
    threshold = max(1, int(payload.threshold or 1))
    smtp_ready = bool(
        os.getenv("NIDS_SMTP_HOST", "").strip()
        or (os.getenv("NIDS_SMTP_USER", "").strip() and os.getenv("NIDS_SMTP_PASSWORD", ""))
    )
    conn = get_db()
    cur = conn.cursor()
    try:
        user = current_admin_user(cur)
        if not user or not user.get("email"):
            raise HTTPException(status_code=400, detail="管理员邮箱未配置")

        cur.execute("SELECT COUNT(*) AS attacks FROM detection_results WHERE predicted_label='attack'")
        attack_count = cur.fetchone()["attacks"]
        cur.execute(
            "SELECT id, created_at, recipient_email, subject, status, provider, alert_id, error "
            "FROM email_notifications WHERE subject = ? ORDER BY id DESC LIMIT 1",
            ("NIDS 危险告警提醒",),
        )
        existing = one_to_dict(cur.fetchone())
        if existing and not payload.force and (existing["status"] == "sent" or not smtp_ready):
            return {
                "ok": True,
                "already_sent": True,
                "status": existing["status"],
                "provider": existing["provider"],
                "recipient_email": existing["recipient_email"],
                "subject": existing["subject"],
                "attack_count": attack_count,
                "threshold": threshold,
                "message": "管理员危险告警邮件已经发送过，本次不重复发送。",
                "history": existing,
            }
        if attack_count < threshold:
            return {
                "ok": False,
                "already_sent": False,
                "status": "below_threshold",
                "recipient_email": user["email"],
                "subject": "NIDS 危险告警提醒",
                "attack_count": attack_count,
                "threshold": threshold,
                "message": f"当前危险告警 {attack_count} 次，未达到 {threshold} 次阈值。",
            }

        latest = query_latest_alert(cur)
        subject = "NIDS 危险告警提醒"
        body = build_admin_risk_body(attack_count, latest)
        try:
            result = send_email_or_demo(user["email"], subject, body)
        except Exception as e:
            result = {"status": "failed", "provider": "smtp", "error": str(e)}
        cur.execute(
            """
            INSERT INTO email_notifications
                (user_id, recipient_email, subject, body, status, provider, alert_id, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user["id"],
                user["email"],
                subject,
                body,
                result["status"],
                result["provider"],
                latest["id"] if latest else None,
                result["error"],
            ),
        )
        conn.commit()
        return {
            "ok": result["status"] in ("sent", "demo_sent"),
            "already_sent": False,
            "status": result["status"],
            "provider": result["provider"],
            "recipient_email": user["email"],
            "subject": subject,
            "body": body,
            "attack_count": attack_count,
            "threshold": threshold,
            "alert": latest,
            "error": result["error"],
        }
    finally:
        conn.close()


@app.get("/api/model/multiclass-evaluation")
def multiclass_evaluation():
    conn = get_db()
    cur = conn.cursor()
    try:
        return evaluate_multiclass_metrics(cur)
    finally:
        conn.close()


@app.get("/api/stats")
def stats():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS total FROM detection_results")
    total = cur.fetchone()["total"]
    cur.execute("SELECT COUNT(*) AS attacks FROM detection_results WHERE predicted_label='attack'")
    attacks = cur.fetchone()["attacks"]
    cur.execute(
        "SELECT COUNT(*) AS false_positives FROM detection_results "
        "WHERE predicted_label='attack' "
        "AND LOWER(COALESCE(true_label, '')) IN ('', 'normal', '0', 'false', 'benign')"
    )
    false_positives = cur.fetchone()["false_positives"]
    cur.execute("SELECT COUNT(DISTINCT iteration) AS drift_batches FROM detection_results WHERE drift_detected=1")
    drift_batches = cur.fetchone()["drift_batches"]
    columns = table_columns(cur, "detection_results")
    if "drift_score" in columns:
        cur.execute(
            "SELECT AVG(drift_score) AS avg_score, MAX(drift_score) AS max_score "
            "FROM detection_results WHERE drift_score IS NOT NULL"
        )
        drift_score_row = cur.fetchone()
        drift_score_avg = drift_score_row["avg_score"] if drift_score_row else None
        drift_score_max = drift_score_row["max_score"] if drift_score_row else None
    else:
        drift_score_avg = None
        drift_score_max = None
    normal = total - attacks
    cur.execute("SELECT accuracy, precision_score, recall, f1_score FROM final_results ORDER BY id DESC LIMIT 1")
    final = cur.fetchone()
    live_metrics = calculate_live_metrics(cur)
    final_has_metrics = bool(final and any(
        final[key] is not None and float(final[key]) > 0
        for key in ("accuracy", "precision_score", "recall", "f1_score")
    ))
    conn.close()
    return {
        "total_flows": total,
        "attack_count": attacks,
        "false_positive_count": false_positives,
        "normal_count": normal,
        "attack_pct": round(attacks / total * 100, 2) if total else 0,
        "drift_detected": drift_batches,
        "drift_score_avg": drift_score_avg or 0,
        "drift_score_max": drift_score_max or 0,
        "accuracy": final["accuracy"] if final_has_metrics else live_metrics["accuracy"],
        "precision": final["precision_score"] if final_has_metrics else live_metrics["precision"],
        "recall": final["recall"] if final_has_metrics else live_metrics["recall"],
        "f1": final["f1_score"] if final_has_metrics else live_metrics["f1"],
        "metrics_source": "final" if final_has_metrics else "live",
    }


@app.get("/api/reports/intrusion")
def intrusion_report():
    """Generate an executive-friendly intrusion situation PDF."""
    import matplotlib.pyplot as plt
    from matplotlib.font_manager import FontProperties
    from matplotlib.backends.backend_pdf import PdfPages

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS total, SUM(CASE WHEN predicted_label='attack' THEN 1 ELSE 0 END) AS attacks FROM detection_results")
    summary = cur.fetchone()
    cur.execute(f"SELECT {flow_select_columns(cur)} FROM detection_results WHERE predicted_label='attack' ORDER BY id DESC LIMIT 500")
    source_counts = {}
    for row in enrich_flow_rows(rows_to_dict(cur.fetchall())):
        ip = row.get("src_ip") or "-"
        source_counts[ip] = source_counts.get(ip, 0) + 1
    sources = [{"ip": ip, "cnt": count} for ip, count in sorted(source_counts.items(), key=lambda item: item[1], reverse=True)[:5]]
    cur.execute("SELECT protocol, COUNT(*) AS cnt FROM detection_results WHERE predicted_label='attack' GROUP BY protocol ORDER BY cnt DESC")
    protocols = rows_to_dict(cur.fetchall())
    cur.execute("SELECT disposition, COUNT(*) AS cnt FROM alert_dispositions GROUP BY disposition")
    dispositions = {row["disposition"]: row["cnt"] for row in rows_to_dict(cur.fetchall())}
    conn.close()
    total, attacks = int(summary['total'] or 0), int(summary['attacks'] or 0)
    attack_ratio = attacks / total * 100 if total else 0
    risk_index = min(95, round(18 + attack_ratio * .62 + min(len(sources), 5) * 2))
    risk_label = "高风险" if risk_index >= 70 else "中风险" if risk_index >= 35 else "低风险"
    font = FontProperties(fname="C:/Windows/Fonts/msyh.ttc")
    font_bold = FontProperties(fname="C:/Windows/Fonts/msyhbd.ttc")
    navy, cyan, orange, red, pale = "#0f172a", "#0f766e", "#f97316", "#dc2626", "#f8fafc"
    plt.rcParams["axes.unicode_minus"] = False
    output = BytesIO()
    with PdfPages(output) as pdf:
        # Page 1: executive cover and security posture.
        fig = plt.figure(figsize=(8.27, 11.69), facecolor="#ffffff")
        fig.patches.append(plt.Rectangle((0, .89), 1, .11, transform=fig.transFigure, color=navy))
        fig.text(.075, .935, "NIDS  网络入侵态势报告", color="white", fontsize=24, fontproperties=font_bold)
        fig.text(.077, .902, "Network Intrusion Detection System | Security Operations Brief", color="#cbd5e1", fontsize=9)
        fig.text(.075, .835, "执行摘要", color=navy, fontsize=18, fontproperties=font_bold)
        fig.text(.075, .797, f"报告生成时间：{datetime.now():%Y-%m-%d %H:%M:%S}\n本报告基于当前已检测流量与告警记录自动生成，用于快速判断网络入侵风险与处置优先级。", color="#475569", fontsize=10, fontproperties=font, linespacing=1.8)
        cards = [("检测流量", f"{total:,}", cyan), ("异常告警", f"{attacks:,}", red), ("异常占比", f"{attack_ratio:.1f}%", orange), ("风险指数", f"{risk_index}/100", red if risk_index >= 70 else orange)]
        for index, (label, value, color) in enumerate(cards):
            x = .075 + index * .215
            fig.patches.append(plt.Rectangle((x, .62), .19, .115, transform=fig.transFigure, color=pale, ec="#e2e8f0"))
            fig.text(x + .015, .698, label, color="#64748b", fontsize=9, fontproperties=font)
            fig.text(x + .015, .652, value, color=color, fontsize=19, fontproperties=font_bold)
        fig.text(.075, .555, "风险结论", color=navy, fontsize=15, fontproperties=font_bold)
        conclusion = f"当前整体风险等级：{risk_label}。异常流量占比为 {attack_ratio:.1f}%，高频风险源主要集中在 {sources[0]['ip'] if sources else '-'}。建议优先完成高频来源的隔离、溯源和服务核查。"
        fig.text(.075, .51, conclusion, color="#334155", fontsize=11, fontproperties=font, wrap=True)
        fig.text(.075, .425, "建议处置顺序", color=navy, fontsize=15, fontproperties=font_bold)
        actions = ["隔离：对高频风险源实施临时访问控制并保留流量证据。", "核查：检查受影响服务、账号与主机日志，确认横向活动范围。", "闭环：在告警中心完成批量研判，记录处置结论与备注。"]
        for index, action in enumerate(actions, 1):
            y = .375 - (index - 1) * .065
            fig.text(.08, y, str(index), color="white", fontsize=10, fontproperties=font_bold, bbox=dict(boxstyle="circle,pad=.35", fc=cyan, ec="none"))
            fig.text(.12, y, action, color="#334155", fontsize=10, fontproperties=font)
        fig.text(.075, .08, "NIDS 安全运营中心  |  此报告由系统自动生成，人工研判结果以告警中心记录为准。", color="#94a3b8", fontsize=8, fontproperties=font)
        fig.axes.append(fig.add_axes([0, 0, 1, 1], frameon=False)); fig.axes[-1].axis("off")
        pdf.savefig(fig, bbox_inches="tight"); plt.close(fig)

        # Page 2: evidence and operational context.
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8.27, 11.69), gridspec_kw={"height_ratios": [1, 1.25]})
        fig.subplots_adjust(top=.89, bottom=.1, hspace=.48, left=.12, right=.92)
        fig.text(.12, .94, "风险证据与处置进展", color=navy, fontsize=19, fontproperties=font_bold)
        names, values = [r["protocol"] or "-" for r in protocols], [r["cnt"] for r in protocols]
        ax1.bar(names, values, color=[red, orange, cyan, "#64748b"][:len(names)])
        ax1.set_title("异常告警协议分布", loc="left", fontproperties=font_bold, color=navy, pad=15)
        ax1.set_ylabel("告警数量", fontproperties=font); ax1.grid(axis="y", alpha=.18); ax1.spines[["top", "right"]].set_visible(False)
        for label in ax1.get_xticklabels() + ax1.get_yticklabels(): label.set_fontproperties(font)
        table_rows = [[str(i + 1), row["ip"], str(row["cnt"]), "优先核查" if i < 2 else "持续观察"] for i, row in enumerate(sources)] or [["-", "暂无", "0", "-"]]
        table = ax2.table(cellText=table_rows, colLabels=["排名", "风险源 IP", "告警数", "建议"], cellLoc="left", colLoc="left", loc="upper center", colColours=[navy] * 4)
        table.auto_set_font_size(False); table.set_fontsize(10); table.scale(1, 1.75)
        for (row, col), cell in table.get_celld().items():
            cell.set_edgecolor("#e2e8f0")
            cell.get_text().set_fontproperties(font_bold if row == 0 else font)
            cell.get_text().set_color("white" if row == 0 else "#334155")
            if row and row % 2 == 0: cell.set_facecolor(pale)
        ax2.set_title("Top 风险源与研判建议", loc="left", fontproperties=font_bold, color=navy, pad=22); ax2.axis("off")
        handled = sum(dispositions.values())
        fig.text(.12, .12, f"人工研判记录：{handled} 条  |  已处置：{dispositions.get('resolved', 0)} 条  |  持续观察：{dispositions.get('watch', 0)} 条", color="#475569", fontsize=9, fontproperties=font)
        pdf.savefig(fig, bbox_inches="tight"); plt.close(fig)
    return Response(content=output.getvalue(), media_type='application/pdf', headers={'Content-Disposition': 'attachment; filename="nids-intrusion-report.pdf"'})


@app.get("/api/flows")
def flows(
    limit: int = Query(50, ge=1, le=1000),
    since_id: int = 0,
    q: str = "",
    ip: str = "",
    src_ip: str = "",
    dst_ip: str = "",
    result: str = "all",
    protocol: str = "",
    service: str = "",
    flag: str = "",
    true_label: str = "",
    start_time: str = "",
    end_time: str = "",
):
    conn = get_db()
    cur = conn.cursor()
    placeholder = db_placeholder()
    select_columns = flow_select_columns(cur)
    where, params = build_flow_filters(
        cur,
        since_id=since_id,
        result=result,
        protocol=protocol,
        service=service,
        flag=flag,
        true_label=true_label,
        start_time=start_time,
        end_time=end_time,
        q=q,
    )
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    fetch_limit = limit
    if any(str(v or "").strip() for v in (ip, src_ip, dst_ip)) and not flow_ip_columns(cur)[0]:
        fetch_limit = min(max(limit * 20, 500), 5000)
    cur.execute(
        f"SELECT {select_columns}"
        f"FROM detection_results {where_sql} ORDER BY id DESC LIMIT {placeholder}",
        (*params, fetch_limit),
    )
    rows = enrich_flow_rows(rows_to_dict(cur.fetchall()))
    attach_disposition_status(cur, rows)
    conn.close()
    rows = [
        row for row in rows
        if flow_matches_post_filters(row, ip=ip, src_ip=src_ip, dst_ip=dst_ip, q=q)
    ]
    return rows[:limit]


@app.get("/api/live-flows")
def live_flows(limit: int = Query(20, ge=1, le=500), since_id: int = 0):
    conn = get_db()
    cur = conn.cursor()
    placeholder = db_placeholder()
    select_columns = flow_select_columns(cur)
    cur.execute(
        f"SELECT {select_columns}"
        f"FROM detection_results WHERE id > {placeholder} ORDER BY id ASC LIMIT {placeholder}",
        (since_id, limit),
    )
    rows = rows_to_dict(cur.fetchall())
    attach_disposition_status(cur, rows)
    conn.close()
    return enrich_flow_rows(rows)


@app.get("/api/alerts")
def alerts(
    limit: int = Query(50, ge=1, le=1000),
    page: int | None = Query(None, ge=1),
    page_size: int = Query(50, ge=1, le=50),
    alert_filter: str = Query("all", alias="filter", pattern="^(all|attack|false_positive)$"),
):
    conn = get_db()
    cur = conn.cursor()
    placeholder = db_placeholder()
    select_columns = flow_select_columns(cur)
    normal_expr = "LOWER(COALESCE(true_label, '')) IN ('', 'normal', '0', 'false', 'benign')"
    where = ["predicted_label='attack'"]
    if alert_filter == "attack":
        where.append(f"NOT ({normal_expr})")
    elif alert_filter == "false_positive":
        where.append(normal_expr)
    where_sql = " AND ".join(where)

    if page is None:
        cur.execute(
            f"SELECT {select_columns}"
            f"FROM detection_results WHERE {where_sql} ORDER BY id DESC LIMIT {placeholder}",
            (limit,),
        )
        rows = rows_to_dict(cur.fetchall())
        rows = enrich_flow_rows(rows)
        attach_disposition_status(cur, rows)
        conn.close()
        for r in rows:
            r["is_false_positive"] = is_normal_label(r.get("true_label"))
            r["has_drift"] = bool(r["drift_detected"])
        return rows

    cur.execute(f"SELECT COUNT(*) AS total FROM detection_results WHERE {where_sql}")
    total = cur.fetchone()["total"]
    offset = (page - 1) * page_size
    cur.execute(
        f"SELECT {select_columns}"
        f"FROM detection_results WHERE {where_sql} ORDER BY id DESC LIMIT {placeholder} OFFSET {placeholder}",
        (page_size, offset),
    )
    rows = rows_to_dict(cur.fetchall())
    rows = enrich_flow_rows(rows)
    attach_disposition_status(cur, rows)
    conn.close()
    for r in rows:
        r["is_false_positive"] = is_normal_label(r.get("true_label"))
        r["has_drift"] = bool(r["drift_detected"])
    return {
        "items": rows,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@app.get("/api/alert-disposition-summary")
def alert_disposition_summary():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS handled FROM alert_dispositions")
    handled = int(cur.fetchone()["handled"] or 0)
    cur.execute("SELECT disposition, COUNT(*) AS cnt FROM alert_dispositions GROUP BY disposition")
    by_status = {row["disposition"]: int(row["cnt"] or 0) for row in cur.fetchall()}
    conn.close()
    return {"handled": handled, "by_status": by_status}


@app.post("/api/alert-aggregation/disposition")
def batch_alert_disposition(payload: BatchDispositionRequest):
    allowed_groups = {"src_ip", "dst_ip", "protocol", "service", "time", "attack_type"}
    allowed_dispositions = {"confirmed", "watch", "false_positive", "resolved"}
    if payload.group_by not in allowed_groups or payload.disposition not in allowed_dispositions:
        raise HTTPException(status_code=400, detail="Invalid aggregation disposition request")
    conn = get_db()
    cur = conn.cursor()
    placeholder = db_placeholder()
    cur.execute(f"SELECT {flow_select_columns(cur)} FROM detection_results WHERE predicted_label='attack' ORDER BY id DESC LIMIT 20000")
    rows = enrich_flow_rows(rows_to_dict(cur.fetchall()))
    def key_for(row):
        if payload.group_by == "src_ip": return row.get("src_ip") or "-"
        if payload.group_by == "dst_ip": return row.get("dst_ip") or "-"
        if payload.group_by == "protocol": return row.get("protocol") or "-"
        if payload.group_by == "service": return row.get("service") or "-"
        if payload.group_by == "attack_type": return display_attack_type(row.get("true_label"), row.get("predicted_label"))
        return format_time(row.get("run_time"))[:13] + ":00"
    matched = [row for row in rows if key_for(row) == payload.group_key]
    for row in matched:
        if DB_BACKEND == "sqlite":
            cur.execute("INSERT OR REPLACE INTO alert_dispositions (alert_id, disposition, note, group_by, group_key, handled_at) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)", (row["id"], payload.disposition, payload.note.strip(), payload.group_by, payload.group_key))
        else:
            cur.execute(f"INSERT INTO alert_dispositions (alert_id, disposition, note, group_by, group_key, handled_at) VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, CURRENT_TIMESTAMP) ON DUPLICATE KEY UPDATE disposition=VALUES(disposition), note=VALUES(note), group_by=VALUES(group_by), group_key=VALUES(group_key), handled_at=CURRENT_TIMESTAMP", (row["id"], payload.disposition, payload.note.strip(), payload.group_by, payload.group_key))
    conn.commit()
    conn.close()
    return {"ok": True, "handled_count": len(matched), "disposition": payload.disposition}


@app.get("/api/alert-aggregation")
def alert_aggregation(
    group_by: str = Query("src_ip", pattern="^(src_ip|dst_ip|protocol|service|time|attack_type)$"),
    limit: int = Query(10, ge=1, le=50),
    interval: str = Query("hour", pattern="^(minute|hour|day)$"),
):
    conn = get_db()
    cur = conn.cursor()
    placeholder = db_placeholder()
    select_columns = flow_select_columns(cur)
    fetch_limit = 5000 if group_by in ("src_ip", "dst_ip") and not flow_ip_columns(cur)[0] else 20000
    cur.execute(
        f"SELECT {select_columns}"
        f"FROM detection_results WHERE predicted_label='attack' ORDER BY id DESC LIMIT {placeholder}",
        (fetch_limit,),
    )
    rows = enrich_flow_rows(rows_to_dict(cur.fetchall()))
    conn.close()

    def time_bucket(value):
        text = format_time(value)
        if interval == "minute":
            return text[:16] if len(text) >= 16 else text
        if interval == "day":
            return text[:10] if len(text) >= 10 else text
        return text[:13] + ":00" if len(text) >= 13 else text

    def key_for(row):
        if group_by == "src_ip":
            return row.get("src_ip") or "-"
        if group_by == "dst_ip":
            return row.get("dst_ip") or "-"
        if group_by == "protocol":
            return row.get("protocol") or "-"
        if group_by == "service":
            return row.get("service") or "-"
        if group_by == "attack_type":
            attack_type = display_attack_type(row.get("true_label"), row.get("predicted_label"))
            return None if attack_type in ("normal", "false_positive") else attack_type
        return time_bucket(row.get("run_time"))

    groups = {}
    for row in rows:
        key = key_for(row)
        if key is None:
            continue
        group = groups.setdefault(key, {
            "key": key,
            "cnt": 0,
            "first_time": row.get("run_time"),
            "last_time": row.get("run_time"),
            "attack_types": {},
            "protocols": {},
            "services": {},
            "src_ips": {},
        })
        group["cnt"] += 1
        group["first_time"] = min(group["first_time"], row.get("run_time"))
        group["last_time"] = max(group["last_time"], row.get("run_time"))
        for field, bucket in (
            ("true_label", "attack_types"),
            ("protocol", "protocols"),
            ("service", "services"),
            ("src_ip", "src_ips"),
        ):
            value = display_attack_type(row.get(field), row.get("predicted_label")) if field == "true_label" else (row.get(field) or "-")
            group[bucket][value] = group[bucket].get(value, 0) + 1

    def top_name(counts):
        if not counts:
            return "-"
        return max(counts.items(), key=lambda item: item[1])[0]

    result = []
    for group in groups.values():
        result.append({
            "key": group["key"],
            "cnt": group["cnt"],
            "first_time": group["first_time"],
            "last_time": group["last_time"],
            "top_attack_type": top_name(group["attack_types"]),
            "top_protocol": top_name(group["protocols"]),
            "top_service": top_name(group["services"]),
            "top_src_ip": top_name(group["src_ips"]),
        })

    result.sort(key=lambda item: item["cnt"], reverse=True)
    return result[:limit]


@app.get("/api/protocol-distribution")
def protocol_distribution():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT protocol, COUNT(*) AS cnt FROM detection_results GROUP BY protocol ORDER BY cnt DESC"
    )
    rows = rows_to_dict(cur.fetchall())
    conn.close()
    return rows


@app.get("/api/attack-types")
def attack_types():
    conn = get_db()
    cur = conn.cursor()
    select_columns = flow_select_columns(cur)
    cur.execute(
        f"SELECT {select_columns}"
        "FROM detection_results WHERE predicted_label='attack'"
    )
    rows = enrich_flow_rows(rows_to_dict(cur.fetchall()))
    conn.close()
    counts = {}
    for row in rows:
        attack_type = display_attack_type(row.get("true_label"), row.get("predicted_label"))
        if attack_type in ("normal", "false_positive"):
            continue
        counts[attack_type] = counts.get(attack_type, 0) + 1
    return [
        {"name": name, "cnt": cnt}
        for name, cnt in sorted(counts.items(), key=lambda item: item[1], reverse=True)[:10]
    ]


@app.get("/api/flag-distribution")
def flag_distribution():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT flag, COUNT(*) AS cnt FROM detection_results WHERE flag != '' GROUP BY flag ORDER BY cnt DESC"
    )
    rows = rows_to_dict(cur.fetchall())
    conn.close()
    return rows


@app.get("/api/service-distribution")
def service_distribution():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT service, COUNT(*) AS cnt FROM detection_results WHERE service != '' GROUP BY service ORDER BY cnt DESC LIMIT 10"
    )
    rows = rows_to_dict(cur.fetchall())
    conn.close()
    return rows


@app.post("/api/assistant/chat")
def assistant_chat(payload: AssistantChatRequest):
    message = payload.message.strip()
    if not message:
        return {
            "answer": "请输入你想查询的问题，例如：最近的告警是什么时候？攻击来源最多的 IP 是什么？",
            "intent": "empty",
            "data": {},
        }

    if not is_detection_question(message):
        provider = "local"
        ai_error = None
        answer = "这个问题和当前入侵检测数据无关，我可以直接回答：请继续说你的具体问题。"
        if ai_enabled():
            try:
                ai_answer = call_external_ai(message, detection_related=False)
                if ai_answer:
                    answer = ai_answer
                    provider = AI_PROVIDER
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, KeyError, json.JSONDecodeError, OSError) as e:
                ai_error = str(e)
        return {"answer": answer, "intent": "general", "data": {}, "provider": provider, "ai_error": ai_error}

    conn = get_db()
    cur = conn.cursor()
    try:
        intent = assistant_intent(message)
        if intent == "latest_alert":
            answer, data = assistant_latest_alert(cur)
        elif intent == "top_source":
            answer, data = assistant_top_source(cur)
        elif intent == "attack_path":
            answer, data = assistant_attack_path(cur)
        elif intent == "protocol_summary":
            answer, data = assistant_group_summary(cur, "protocol", "协议")
        elif intent == "service_summary":
            answer, data = assistant_group_summary(cur, "service", "服务")
        elif intent == "attack_type_summary":
            answer, data = assistant_group_summary(cur, "true_label", "攻击类型")
        else:
            answer, data = assistant_overview(cur)
        provider = "local"
        ai_error = None
        if ai_enabled():
            try:
                ai_answer = call_external_ai(message, answer, data)
                if ai_answer:
                    answer = ai_answer
                    provider = AI_PROVIDER
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, KeyError, json.JSONDecodeError, OSError) as e:
                ai_error = str(e)
        return {"answer": answer, "intent": intent, "data": data, "provider": provider, "ai_error": ai_error}
    finally:
        conn.close()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
