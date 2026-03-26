from flask import Flask, request, redirect, session, url_for, render_template_string, flash
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import sqlite3
import os
import random
import re
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "nexus_guard_secret_key_2026")

DB_NAME = os.getenv("DB_NAME", "nexus_guard.db")
PROJECT_NAME = "Nexus Guard"

ADMIN_USERNAME = "sayyaf"
ADMIN_PASSWORD = "P@ssw0rd"


# =========================================================
# قاعدة البيانات
# =========================================================
def db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0,
            failed_attempts INTEGER DEFAULT 0,
            locked INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS quiz_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            score INTEGER,
            total INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS phishing_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            fake_username TEXT,
            password_strength TEXT,
            risk_level TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS login_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            success INTEGER,
            ip_address TEXT,
            user_agent TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # إنشاء حساب الأدمن إذا غير موجود
    cur.execute("SELECT * FROM users WHERE username = ?", (ADMIN_USERNAME,))
    admin = cur.fetchone()
    if not admin:
        cur.execute("""
            INSERT INTO users (username, password_hash, is_admin)
            VALUES (?, ?, 1)
        """, (ADMIN_USERNAME, generate_password_hash(ADMIN_PASSWORD)))

    conn.commit()
    conn.close()


# =========================================================
# أدوات مساعدة
# =========================================================
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("يجب تسجيل الدخول أولاً", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session or not session.get("is_admin"):
            flash("غير مصرح لك بالدخول", "danger")
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)
    return wrapper


def get_ip():
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "Unknown"


def get_user():
    if "user_id" not in session:
        return None
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],))
    user = cur.fetchone()
    conn.close()
    return user


def count_user_quizzes(user_id):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as c FROM quiz_results WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row["c"] if row else 0


def count_user_phishing(user_id):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as c FROM phishing_logs WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row["c"] if row else 0


def get_user_level(user_id):
    quizzes = count_user_quizzes(user_id)
    phishing = count_user_phishing(user_id)
    score = quizzes + phishing

    if score >= 8:
        return "متقدم"
    elif score >= 4:
        return "جيد"
    return "مبتدئ"


def analyze_password_strength(password):
    score = 0
    notes = []

    if len(password) >= 8:
        score += 1
    else:
        notes.append("يفضل أن تكون 8 أحرف أو أكثر")

    if len(password) >= 12:
        score += 1

    if re.search(r"[A-Z]", password):
        score += 1
    else:
        notes.append("أضف حرفًا كبيرًا")

    if re.search(r"[a-z]", password):
        score += 1
    else:
        notes.append("أضف حرفًا صغيرًا")

    if re.search(r"\d", password):
        score += 1
    else:
        notes.append("أضف أرقامًا")

    if re.search(r"[^\w]", password):
        score += 1
    else:
        notes.append("أضف رمزًا خاصًا")

    weak_patterns = ["123", "password", "qwerty", "admin", "111", "000", "abc"]
    lowered = password.lower()
    for p in weak_patterns:
        if p in lowered:
            score -= 1
            notes.append(f"يحتوي على نمط ضعيف: {p}")
            break

    if score <= 2:
        return {"level": "ضعيفة", "score": max(score, 0), "color": "#ff4d4d", "notes": notes}
    elif score <= 4:
        return {"level": "متوسطة", "score": score, "color": "#ffcc00", "notes": notes}
    else:
        return {"level": "قوية", "score": score, "color": "#00ff88", "notes": notes}


def cyber_tip():
    tips = [
        "لا تضغط أي رابط مجهول قبل التأكد من المصدر.",
        "فعّل التحقق بخطوتين لحساباتك المهمة.",
        "لا تستخدم نفس كلمة المرور في كل المواقع.",
        "شبكات Wi-Fi المفتوحة قد تعرّض بياناتك للخطر.",
        "الرسائل المستعجلة والمخيفة غالبًا تكون تصيدًا.",
        "حدّث نظامك وبرامجك باستمرار.",
        "لا تشارك رمز التحقق مع أي شخص.",
        "تأكد من كتابة اسم الموقع الصحيح قبل تسجيل الدخول."
    ]
    return random.choice(tips)


SCENARIOS = [
    {
        "title": "📦 تتبع شحنتك",
        "desc": "وصلتك رسالة تقول إن شحنتك متوقفة ويجب الضغط فورًا على الرابط.",
        "risk": "غالبًا تصيد",
        "tip": "ادخل على موقع شركة الشحن الرسمي بنفسك ولا تضغط الرابط مباشرة."
    },
    {
        "title": "🏦 تنبيه بنكي",
        "desc": "رسالة تقول: تم إيقاف حسابك البنكي مؤقتًا، حدّث بياناتك الآن.",
        "risk": "خطر مرتفع",
        "tip": "البنك لا يطلب بياناتك السرية عبر الروابط العشوائية."
    },
    {
        "title": "🎁 فزت بجائزة",
        "desc": "مبروك! ربحت هاتفًا جديدًا، أدخل معلوماتك للاستلام.",
        "risk": "احتيال",
        "tip": "العروض المبالغ فيها غالبًا هدفها سرقة البيانات."
    },
    {
        "title": "📱 رسالة واتساب",
        "desc": "تم إرسال ملف أو صورة لك، سجّل دخولك للمشاهدة.",
        "risk": "رابط مزيف",
        "tip": "تحقق من عنوان الموقع، ولا تسجل دخولك إلا في الصفحة الرسمية."
    }
]

WIFI_NETWORKS = [
    {
        "name": "Free_Coffee_WiFi",
        "security": "Open",
        "signal": "قوي",
        "risk": "خطرة",
        "reason": "شبكة مفتوحة بدون تشفير، يمكن اعتراض البيانات."
    },
    {
        "name": "Airport_FreeNet",
        "security": "Open",
        "signal": "متوسط",
        "risk": "خطرة",
        "reason": "الشبكات العامة المفتوحة مكان شائع للتصيد والتجسس."
    },
    {
        "name": "Secure_Office_WiFi",
        "security": "WPA2/WPA3",
        "signal": "قوي",
        "risk": "آمنة",
        "reason": "تستخدم بروتوكول تشفير جيد."
    },
    {
        "name": "Cafe_Staff_Private",
        "security": "WPA2",
        "signal": "جيد",
        "risk": "متوسطة",
        "reason": "أفضل من المفتوحة، لكن يجب التأكد من اسم الشبكة الصحيح."
    }
]

QUIZ_QUESTIONS = [
    {
        "q": "ما أفضل تصرف عند وصول رسالة تطلب منك تحديث كلمة المرور عبر رابط مجهول؟",
        "choices": ["أضغط الرابط فورًا", "أتجاهل التحقق", "أدخل الموقع الرسمي يدويًا", "أرسل بياناتي للمرسل"],
        "answer": "أدخل الموقع الرسمي يدويًا",
        "explain": "الطريقة الآمنة هي الدخول للموقع الرسمي بنفسك بدل الضغط على روابط مجهولة."
    },
    {
        "q": "ما فائدة التحقق بخطوتين؟",
        "choices": ["يزيد الأمان", "يقلل سرعة الإنترنت", "يحذف الفيروسات", "يغني عن كلمة المرور"],
        "answer": "يزيد الأمان",
        "explain": "حتى لو عرف المهاجم كلمة المرور يبقى بحاجة لخطوة إضافية."
    },
    {
        "q": "أي كلمة مرور أقوى؟",
        "choices": ["12345678", "password", "Sayyaf2026!", "abcd1234"],
        "answer": "Sayyaf2026!",
        "explain": "لأنها تحتوي على أحرف كبيرة وصغيرة وأرقام ورمز."
    },
    {
        "q": "ما خطورة Wi-Fi المفتوح؟",
        "choices": ["أسرع دائمًا", "لا يوجد خطر", "قد يسمح باعتراض البيانات", "يحميك من التصيد"],
        "answer": "قد يسمح باعتراض البيانات",
        "explain": "الشبكات المفتوحة تجعل بياناتك أكثر عرضة للاعتراض."
    },
    {
        "q": "أي علامة تدل على التصيد؟",
        "choices": ["استعجال وتهديد", "اسم نطاق معروف وصحيح", "شهادة موثوقة من جهة معروفة", "دخول عبر التطبيق الرسمي"],
        "answer": "استعجال وتهديد",
        "explain": "المحتال غالبًا يستخدم التخويف أو الاستعجال لدفعك للضغط بسرعة."
    },
    {
        "q": "هل يجوز مشاركة رمز التحقق مع موظف يدّعي الدعم الفني؟",
        "choices": ["نعم", "لا", "أحيانًا", "إذا كان مستعجل"],
        "answer": "لا",
        "explain": "رموز التحقق سرية ولا يجب مشاركتها مع أي أحد."
    }
]

CHATBOT_KNOWLEDGE = {
    "ما هو الأمن السيبراني": "الأمن السيبراني هو حماية الأجهزة والأنظمة والشبكات والبيانات من الاختراق أو التخريب أو الوصول غير المصرح به.",
    "ما هو التصيد": "التصيد هو محاولة خداع الضحية برسالة أو موقع مزيف للحصول على بياناته مثل كلمة المرور أو رقم البطاقة.",
    "ما هي فائدة التحقق بخطوتين": "التحقق بخطوتين يضيف طبقة أمان إضافية فوق كلمة المرور ويصعّب اختراق الحساب.",
    "كيف أعرف الرابط المزيف": "افحص اسم النطاق جيدًا، وانتبه للأخطاء الإملائية والروابط المختصرة والرسائل المستعجلة.",
    "ما خطر الواي فاي المفتوح": "الشبكات المفتوحة قد تسمح للمهاجمين بمراقبة التصفح أو اعتراض البيانات.",
    "كيف أحمي حسابي": "استخدم كلمة مرور قوية ومختلفة وفعّل التحقق بخطوتين ولا تضغط الروابط المشبوهة.",
    "ما هي كلمة المرور القوية": "هي كلمة طويلة وتحتوي على أحرف كبيرة وصغيرة وأرقام ورموز ولا تتضمن معلومات سهلة التخمين.",
    "هل كل رسالة بنك صحيحة": "لا، بعض الرسائل تنتحل اسم البنك. الأفضل الدخول لتطبيق البنك أو موقعه الرسمي مباشرة.",
    "ما هو الهندسة الاجتماعية": "هي أسلوب خداع نفسي يستغل الثقة أو الخوف أو الاستعجال للحصول على معلومات حساسة.",
    "ما أفضل طريقة للتأكد من الموقع": "اكتب رابط الموقع يدويًا أو استخدم التطبيق الرسمي بدل الاعتماد على الروابط المرسلة.",
}


# =========================================================
# القالب الأساسي
# =========================================================
BASE_HTML = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }} - {{ project_name }}</title>
    <style>
        * { box-sizing: border-box; }
        body {
            margin: 0;
            font-family: Tahoma, Arial, sans-serif;
            background:
                radial-gradient(circle at top right, rgba(0,255,65,0.08), transparent 25%),
                linear-gradient(135deg, #050505, #0b1220, #08110a);
            color: #e5ffe9;
            min-height: 100vh;
        }
        a { text-decoration: none; color: inherit; }
        .nav {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            align-items: center;
            justify-content: space-between;
            padding: 16px 24px;
            background: rgba(0,0,0,0.45);
            border-bottom: 1px solid rgba(0,255,65,0.22);
            position: sticky;
            top: 0;
            backdrop-filter: blur(10px);
            z-index: 99;
        }
        .brand {
            font-size: 24px;
            font-weight: bold;
            color: #00ff88;
            text-shadow: 0 0 12px rgba(0,255,136,0.35);
        }
        .nav-links {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
        }
        .nav-links a {
            padding: 10px 14px;
            border: 1px solid rgba(0,255,65,0.25);
            border-radius: 12px;
            background: rgba(255,255,255,0.03);
            transition: 0.25s;
            font-size: 14px;
        }
        .nav-links a:hover {
            background: rgba(0,255,65,0.12);
            transform: translateY(-1px);
        }
        .container {
            max-width: 1200px;
            margin: 24px auto;
            padding: 0 18px 40px;
        }
        .hero {
            background: linear-gradient(135deg, rgba(0,255,136,0.10), rgba(0,224,255,0.08));
            border: 1px solid rgba(0,255,136,0.25);
            border-radius: 22px;
            padding: 28px;
            box-shadow: 0 0 30px rgba(0,0,0,0.18);
            margin-bottom: 20px;
        }
        .hero h1 {
            margin: 0 0 10px;
            color: #00ff88;
            font-size: 30px;
        }
        .hero p {
            margin: 6px 0;
            color: #d6fbe0;
            line-height: 1.8;
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
            gap: 16px;
        }
        .card {
            background: rgba(0,0,0,0.35);
            border: 1px solid rgba(0,255,65,0.18);
            border-radius: 18px;
            padding: 18px;
            box-shadow: 0 0 18px rgba(0,0,0,0.12);
        }
        .card h3 {
            margin-top: 0;
            color: #00ff88;
        }
        .btn {
            display: inline-block;
            background: linear-gradient(135deg, #00ff88, #00d4ff);
            color: #03140a;
            border: none;
            border-radius: 12px;
            padding: 11px 16px;
            font-weight: bold;
            cursor: pointer;
            transition: 0.25s;
        }
        .btn:hover {
            transform: translateY(-1px);
            opacity: 0.95;
        }
        .btn-secondary {
            background: rgba(255,255,255,0.08);
            color: #eaffef;
            border: 1px solid rgba(0,255,65,0.20);
        }
        input, select, textarea {
            width: 100%;
            padding: 12px 13px;
            margin: 8px 0 14px;
            border-radius: 12px;
            border: 1px solid rgba(0,255,65,0.20);
            background: rgba(255,255,255,0.04);
            color: #ffffff;
            outline: none;
        }
        textarea { min-height: 120px; resize: vertical; }
        label { display: block; margin-top: 10px; color: #d9ffe2; }
        .flash {
            padding: 12px 14px;
            margin: 10px 0;
            border-radius: 12px;
            font-size: 14px;
        }
        .success { background: rgba(0,255,136,0.12); border: 1px solid rgba(0,255,136,0.35); }
        .danger { background: rgba(255,77,77,0.12); border: 1px solid rgba(255,77,77,0.35); }
        .warning { background: rgba(255,204,0,0.12); border: 1px solid rgba(255,204,0,0.35); color: #fff5c2; }
        .info { background: rgba(0,212,255,0.12); border: 1px solid rgba(0,212,255,0.35); }
        .terminal {
            background: #020202;
            border: 1px solid rgba(0,255,65,0.30);
            border-radius: 16px;
            padding: 16px;
            color: #00ff88;
            font-family: Consolas, monospace;
            white-space: pre-wrap;
            line-height: 1.8;
            box-shadow: inset 0 0 30px rgba(0,255,65,0.05);
        }
        .badge {
            display: inline-block;
            padding: 6px 10px;
            border-radius: 999px;
            font-size: 13px;
            font-weight: bold;
            margin-left: 6px;
        }
        .safe { background: rgba(0,255,136,0.15); color: #8fffc0; border: 1px solid rgba(0,255,136,0.25); }
        .medium { background: rgba(255,204,0,0.12); color: #ffe68a; border: 1px solid rgba(255,204,0,0.25); }
        .danger-badge { background: rgba(255,77,77,0.14); color: #ff9f9f; border: 1px solid rgba(255,77,77,0.28); }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
            overflow: hidden;
            border-radius: 14px;
        }
        th, td {
            padding: 12px;
            border-bottom: 1px solid rgba(255,255,255,0.08);
            text-align: right;
            vertical-align: top;
        }
        th { color: #00ff88; background: rgba(255,255,255,0.04); }
        .footer {
            text-align: center;
            padding: 30px 20px;
            color: #b5cdb8;
            opacity: 0.85;
            font-size: 14px;
        }
        .muted {
            color: #bfd7c4;
            font-size: 14px;
        }
        .split {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
            gap: 16px;
        }
        .phone-frame {
            border: 8px solid #111;
            border-radius: 28px;
            padding: 18px;
            background: linear-gradient(180deg, #1a1a1a, #080808);
            min-height: 440px;
            box-shadow: 0 0 20px rgba(0,0,0,0.3);
        }
        .phone-top {
            width: 120px;
            height: 8px;
            border-radius: 999px;
            background: #222;
            margin: 0 auto 18px;
        }
        .danger-text { color: #ff9f9f; }
        .good-text { color: #8fffc0; }
        .center { text-align: center; }
    </style>
</head>
<body>
    {% if show_nav %}
    <div class="nav">
        <div class="brand">{{ project_name }}</div>
        <div class="nav-links">
            {% if session.get("user_id") %}
                <a href="{{ url_for('dashboard') }}">الرئيسية</a>
                <a href="{{ url_for('cyber_info') }}">الأمن السيبراني</a>
                <a href="{{ url_for('scenarios') }}">السيناريوهات</a>
                <a href="{{ url_for('wifi_analysis') }}">تحليل Wi-Fi</a>
                <a href="{{ url_for('hacker_lab') }}">مختبر التجارب</a>
                <a href="{{ url_for('protection') }}">الحماية</a>
                <a href="{{ url_for('quiz') }}">الاختبار</a>
                <a href="{{ url_for('chatbot') }}">الشات بوت</a>
                {% if session.get("is_admin") %}
                    <a href="{{ url_for('admin_panel') }}">لوحة الأدمن</a>
                {% endif %}
                <a href="{{ url_for('logout') }}">تسجيل خروج</a>
            {% else %}
                <a href="{{ url_for('login') }}">تسجيل الدخول</a>
                <a href="{{ url_for('register') }}">حساب جديد</a>
            {% endif %}
        </div>
    </div>
    {% endif %}

    <div class="container">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, msg in messages %}
                    <div class="flash {{ category }}">{{ msg }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}

        {{ content|safe }}
    </div>

    <div class="footer">
        {{ project_name }} | مشروع توعوي بالأمن السيبراني - محاكاة تعليمية فقط
    </div>
</body>
</html>
"""


def render_page(title, content, show_nav=True):
    return render_template_string(
        BASE_HTML,
        title=title,
        content=content,
        show_nav=show_nav,
        project_name=PROJECT_NAME,
        session=session
    )


# =========================================================
# المسارات الأساسية
# =========================================================
@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if len(username) < 3:
            flash("اسم المستخدم قصير جدًا", "danger")
            return redirect(url_for("register"))

        if len(password) < 6:
            flash("كلمة المرور يجب أن تكون 6 أحرف على الأقل", "danger")
            return redirect(url_for("register"))

        conn = db()
        cur = conn.cursor()
        try:
            cur.execute("""
                INSERT INTO users (username, password_hash, is_admin)
                VALUES (?, ?, 0)
            """, (username, generate_password_hash(password)))
            conn.commit()
            flash("تم إنشاء الحساب بنجاح، سجل الدخول الآن", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("اسم المستخدم موجود مسبقًا", "danger")
        finally:
            conn.close()

    content = f"""
    <div class="hero center">
        <h1>إنشاء حساب جديد</h1>
        <p>ابدأ رحلتك في التوعية بالأمن السيبراني داخل مشروع <b>{PROJECT_NAME}</b></p>
    </div>

    <div class="card" style="max-width:700px;margin:auto;">
        <form method="post">
            <label>اسم المستخدم</label>
            <input type="text" name="username" placeholder="اكتب اسم المستخدم" required>

            <label>كلمة المرور</label>
            <input type="password" name="password" placeholder="اكتب كلمة المرور" required>

            <button class="btn" type="submit">إنشاء الحساب</button>
            <a class="btn btn-secondary" href="{url_for('login')}">عندي حساب</a>
        </form>
    </div>
    """
    return render_page("حساب جديد", content, show_nav=False)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        conn = db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = cur.fetchone()

        success = 0

        if user:
            if user["locked"] == 1:
                conn.execute("""
                    INSERT INTO login_logs (username, success, ip_address, user_agent)
                    VALUES (?, ?, ?, ?)
                """, (username, 0, get_ip(), request.headers.get("User-Agent", "Unknown")))
                conn.commit()
                conn.close()
                flash("تم قفل الحساب بعد محاولات فاشلة متعددة، راجع الأدمن", "danger")
                return redirect(url_for("login"))

            if check_password_hash(user["password_hash"], password):
                session["user_id"] = user["id"]
                session["username"] = user["username"]
                session["is_admin"] = bool(user["is_admin"])

                cur.execute("UPDATE users SET failed_attempts = 0 WHERE id = ?", (user["id"],))
                success = 1
                conn.execute("""
                    INSERT INTO login_logs (username, success, ip_address, user_agent)
                    VALUES (?, ?, ?, ?)
                """, (username, success, get_ip(), request.headers.get("User-Agent", "Unknown")))
                conn.commit()
                conn.close()

                flash("تم تسجيل الدخول بنجاح", "success")
                return redirect(url_for("dashboard"))
            else:
                new_attempts = user["failed_attempts"] + 1
                locked = 1 if new_attempts >= 3 else 0
                cur.execute("""
                    UPDATE users
                    SET failed_attempts = ?, locked = ?
                    WHERE id = ?
                """, (new_attempts, locked, user["id"]))
        else:
            # لو المستخدم غير موجود، نسجل المحاولة فقط
            pass

        conn.execute("""
            INSERT INTO login_logs (username, success, ip_address, user_agent)
            VALUES (?, ?, ?, ?)
        """, (username, success, get_ip(), request.headers.get("User-Agent", "Unknown")))
        conn.commit()
        conn.close()

        flash("بيانات الدخول غير صحيحة", "danger")
        return redirect(url_for("login"))

    content = """
    <div class="hero center">
        <h1>تسجيل دخول إلى محاكي الأمن السيبراني</h1>
        <p>واجهة تعليمية عربية احترافية لمحاكاة المخاطر الرقمية وطرق الحماية</p>
    </div>

    <div class="card" style="max-width:760px;margin:auto;">
        <form method="post">
            <label>اسم المستخدم</label>
            <input type="text" name="username" placeholder="اكتب اسم المستخدم" required>

            <label>كلمة المرور</label>
            <input type="password" name="password" id="passwordField" placeholder="اكتب كلمة المرور" required>

            <button type="button" class="btn btn-secondary" onclick="togglePassword()">إظهار / إخفاء كلمة المرور</button>
            <br><br>
            <button class="btn" type="submit">دخول</button>
            <a class="btn btn-secondary" href="/register">إنشاء حساب</a>
        </form>

        <div class="card" style="margin-top:18px;">
            <h3>نصيحة سيبرانية</h3>
            <p>{{ tip }}</p>
            <p class="muted">معلومة مهمة: هذا المشروع للتوعية والمحاكاة التعليمية فقط.</p>
        </div>
    </div>

    <script>
    function togglePassword() {
        const field = document.getElementById("passwordField");
        field.type = field.type === "password" ? "text" : "password";
    }
    </script>
    """
    return render_template_string(
        BASE_HTML,
        title="تسجيل الدخول",
        content=render_template_string(content, tip=cyber_tip()),
        show_nav=False,
        project_name=PROJECT_NAME,
        session=session
    )


@app.route("/logout")
def logout():
    session.clear()
    flash("تم تسجيل الخروج", "info")
    return redirect(url_for("login"))


# =========================================================
# لوحة المستخدم
# =========================================================
@app.route("/dashboard")
@login_required
def dashboard():
    user = get_user()
    level = get_user_level(user["id"])

    content = f"""
    <div class="hero">
        <h1>مرحبًا {user["username"]} 👋</h1>
        <p>مستواك الحالي: <span class="badge safe">{level}</span></p>
        <p>نصيحة اليوم: {cyber_tip()}</p>
        <p>هذا النظام صُمم لتوعية المستخدمين بالمخاطر الرقمية بأسلوب تفاعلي واقعي واحترافي.</p>
    </div>

    <div class="grid">
        <div class="card">
            <h3>🛡️ الأمن السيبراني</h3>
            <p>تعرف على المفاهيم الأساسية وأهمية حماية الأجهزة والحسابات والبيانات.</p>
            <a class="btn" href="{url_for('cyber_info')}">فتح القسم</a>
        </div>

        <div class="card">
            <h3>🎭 السيناريوهات</h3>
            <p>أمثلة عملية لرسائل وروابط احتيالية وكيفية اكتشافها قبل الوقوع فيها.</p>
            <a class="btn" href="{url_for('scenarios')}">عرض السيناريوهات</a>
        </div>

        <div class="card">
            <h3>📡 تحليل Wi-Fi</h3>
            <p>تعلم الفرق بين الشبكات الآمنة والخطرة ولماذا تعد الشبكات المفتوحة مخاطرة.</p>
            <a class="btn" href="{url_for('wifi_analysis')}">تحليل الشبكات</a>
        </div>

        <div class="card">
            <h3>💀 مختبر التجارب</h3>
            <p>محاكاة تعليمية لواجهة تصيد مزيفة مع شاشة هكر توضح خطورة تسريب البيانات.</p>
            <a class="btn" href="{url_for('hacker_lab')}">دخول المختبر</a>
        </div>

        <div class="card">
            <h3>🔐 الحماية</h3>
            <p>اختبر قوة كلمة المرور وخذ نصائح عملية لتأمين حساباتك وأجهزتك.</p>
            <a class="btn" href="{url_for('protection')}">افتح الحماية</a>
        </div>

        <div class="card">
            <h3>📝 الاختبار</h3>
            <p>اختبر معلوماتك واطلع على نتيجتك وتقييمك في الأمن السيبراني.</p>
            <a class="btn" href="{url_for('quiz')}">ابدأ الاختبار</a>
        </div>

        <div class="card">
            <h3>🤖 الشات بوت</h3>
            <p>اسأل المستشار الذكي عن مفاهيم الأمن السيبراني والروابط المشبوهة والحماية.</p>
            <a class="btn" href="{url_for('chatbot')}">افتح الشات بوت</a>
        </div>
    </div>
    """
    return render_page("الرئيسية", content)


@app.route("/cyber_info")
@login_required
def cyber_info():
    content = """
    <div class="hero">
        <h1>ما هو الأمن السيبراني؟</h1>
        <p>الأمن السيبراني هو عملية حماية الأنظمة والشبكات والبرامج والبيانات من الهجمات الرقمية.</p>
        <p>الهدف منه هو منع الوصول غير المصرح به والتخريب وسرقة المعلومات.</p>
    </div>

    <div class="grid">
        <div class="card">
            <h3>🔐 لماذا هو مهم؟</h3>
            <p>لأنه يحمي حساباتك وصورك وبياناتك البنكية وخصوصيتك من الاحتيال والاختراق.</p>
        </div>
        <div class="card">
            <h3>🎣 ما هو التصيد؟</h3>
            <p>رسائل أو مواقع مزيفة هدفها خداعك لكتابة بياناتك أو كلمة المرور أو رمز التحقق.</p>
        </div>
        <div class="card">
            <h3>🧠 ما هي الهندسة الاجتماعية؟</h3>
            <p>هي خداع نفسي يعتمد على الخوف أو الاستعجال أو الثقة بدل الاعتماد فقط على التقنية.</p>
        </div>
        <div class="card">
            <h3>🐧 ما علاقة Linux و Kali؟</h3>
            <p>أنظمة Linux تُستخدم في إدارة الأنظمة والأمن السيبراني، وKali Linux مشهور في بيئات الاختبار والتعلم الأمني.</p>
        </div>
    </div>
    """
    return render_page("الأمن السيبراني", content)


@app.route("/scenarios")
@login_required
def scenarios():
    cards = ""
    for s in SCENARIOS:
        risk_class = "danger-badge" if s["risk"] in ["غالبًا تصيد", "خطر مرتفع", "احتيال", "رابط مزيف"] else "medium"
        cards += f"""
        <div class="card">
            <h3>{s["title"]}</h3>
            <p>{s["desc"]}</p>
            <p><span class="badge {risk_class}">{s["risk"]}</span></p>
            <p><b>النصيحة:</b> {s["tip"]}</p>
        </div>
        """

    content = f"""
    <div class="hero">
        <h1>سيناريوهات توعوية واقعية</h1>
        <p>هذه أمثلة شائعة لأساليب الاحتيال الرقمي التي تستغل استعجال المستخدم أو ثقته.</p>
    </div>
    <div class="grid">
        {cards}
    </div>
    """
    return render_page("السيناريوهات", content)


@app.route("/wifi", methods=["GET", "POST"])
@login_required
def wifi_analysis():
    result_html = ""

    if request.method == "POST":
        selected = request.form.get("network")
        network = next((n for n in WIFI_NETWORKS if n["name"] == selected), None)

        if network:
            badge_class = "safe" if network["risk"] == "آمنة" else "medium" if network["risk"] == "متوسطة" else "danger-badge"
            result_html = f"""
            <div class="card">
                <h3>نتيجة التحليل</h3>
                <p><b>اسم الشبكة:</b> {network["name"]}</p>
                <p><b>نوع الحماية:</b> {network["security"]}</p>
                <p><b>قوة الإشارة:</b> {network["signal"]}</p>
                <p><b>التقييم:</b> <span class="badge {badge_class}">{network["risk"]}</span></p>
                <p><b>السبب:</b> {network["reason"]}</p>
            </div>
            """

    options = "".join([f'<option value="{n["name"]}">{n["name"]}</option>' for n in WIFI_NETWORKS])

    content = f"""
    <div class="hero">
        <h1>تحليل شبكات Wi-Fi</h1>
        <p>اختر شبكة لمعرفة مستوى الأمان والمخاطر المرتبطة بها.</p>
    </div>

    <div class="card">
        <form method="post">
            <label>اختر شبكة</label>
            <select name="network" required>
                <option value="">-- اختر --</option>
                {options}
            </select>
            <button class="btn" type="submit">تحليل</button>
        </form>
    </div>

    {result_html}

    <div class="grid">
        <div class="card">
            <h3>نصيحة مهمة</h3>
            <p>الشبكات المفتوحة ليست مناسبة لتسجيل الدخول إلى الحسابات أو تنفيذ عمليات مالية.</p>
        </div>
        <div class="card">
            <h3>ماذا أفعل عند الاضطرار؟</h3>
            <p>استخدم VPN وتجنب إدخال كلمات المرور والمعلومات الحساسة.</p>
        </div>
    </div>
    """
    return render_page("تحليل Wi-Fi", content)


@app.route("/hacker-lab", methods=["GET", "POST"])
@login_required
def hacker_lab():
    output = ""
    fake_user = ""
    fake_pass = ""

    if request.method == "POST":
        fake_user = request.form.get("fake_username", "").strip()
        fake_pass = request.form.get("fake_password", "").strip()
        strength = analyze_password_strength(fake_pass)

        risk_level = "منخفض"
        if strength["level"] == "ضعيفة":
            risk_level = "مرتفع"
        elif strength["level"] == "متوسطة":
            risk_level = "متوسط"

        conn = db()
        conn.execute("""
            INSERT INTO phishing_logs (user_id, fake_username, password_strength, risk_level)
            VALUES (?, ?, ?, ?)
        """, (session["user_id"], fake_user, strength["level"], risk_level))
        conn.commit()
        conn.close()

        output = f"""
        <div class="card">
            <h3>نتيجة المحاكاة التعليمية</h3>
            <p class="danger-text"><b>تنبيه:</b> لو كانت هذه صفحة مزيفة حقيقية فإدخال البيانات هنا قد يعرّضك للاختراق.</p>
            <p><b>اسم المستخدم الذي تم إدخاله:</b> {fake_user}</p>
            <p><b>قوة كلمة المرور:</b> <span style="color:{strength["color"]};font-weight:bold;">{strength["level"]}</span></p>
            <p><b>مستوى الخطورة:</b> {risk_level}</p>
            <p><b>الهدف من المحاكاة:</b> توضيح كيف تقع البيانات في صفحات مزيفة ظاهرها طبيعي.</p>
        </div>
        """

    content = f"""
    <div class="hero">
        <h1>مختبر التجارب التعليمية</h1>
        <p>هذه الصفحة محاكاة توعوية فقط ولا يوجد فيها أي اختراق حقيقي.</p>
    </div>

    <div class="split">
        <div class="phone-frame">
            <div class="phone-top"></div>
            <div class="card" style="background:rgba(255,255,255,0.02);">
                <h3 class="center">Instagram Login</h3>
                <p class="muted center">مثال تعليمي لواجهة مزيفة قد تشبه صفحات معروفة</p>
                <form method="post">
                    <label>اسم المستخدم</label>
                    <input type="text" name="fake_username" placeholder="Phone, username, email" required>

                    <label>كلمة المرور</label>
                    <input type="password" name="fake_password" placeholder="Password" required>

                    <button class="btn" type="submit">Log in</button>
                </form>
            </div>
        </div>

        <div class="card">
            <h3>شاشة المراقبة التوعوية</h3>
            <div class="terminal">
[ SYSTEM ] Simulation started...
[ WIFI ] STC_WiFi_5G
[ DEVICE ] Mobile / Tablet (Simulated)
[ LOCATION ] Makkah - Al-Akishiyah (Simulated)
[ DNS ] 8.8.8.8
[ STATUS ] Waiting for educational input...
[ ALERT ] لا تدخل بياناتك في أي صفحة قبل التحقق من الرابط الرسمي.
            </div>

            <div class="card" style="margin-top:14px;">
                <h3>تحذير</h3>
                <p>الصفحات المزيفة قد تكون مشابهة جدًا للحقيقية من حيث التصميم والشعار والألوان.</p>
                <p>تحقق دائمًا من اسم الموقع، القفل، والنطاق الصحيح.</p>
            </div>
        </div>

        <div class="card">
            <h3>المستشار الذكي</h3>
            <p><b>س:</b> كيف أعرف أن الصفحة مزيفة؟</p>
            <p><b>ج:</b> راقب اسم النطاق، والأخطاء الإملائية، والرسائل المستعجلة، وادخل يدويًا للموقع الرسمي.</p>
            <hr>
            <p><b>س:</b> هل يجوز إدخال كلمة المرور في أي رابط؟</p>
            <p><b>ج:</b> لا، إلا إذا تأكدت من الموقع الرسمي 100٪.</p>
            <hr>
            <p><b>س:</b> ما أخطر شيء؟</p>
            <p><b>ج:</b> مشاركة كلمة المرور أو رمز التحقق أو بيانات البطاقة في صفحات غير موثوقة.</p>
        </div>
    </div>

    {output}
    """
    return render_page("مختبر التجارب", content)


@app.route("/protection", methods=["GET", "POST"])
@login_required
def protection():
    result = ""

    if request.method == "POST":
        password = request.form.get("password_to_check", "")
        analysis = analyze_password_strength(password)
        notes_html = "".join([f"<li>{n}</li>" for n in analysis["notes"]]) if analysis["notes"] else "<li>ممتاز، كلمة المرور جيدة</li>"

        result = f"""
        <div class="card">
            <h3>نتيجة تحليل كلمة المرور</h3>
            <p><b>التقييم:</b> <span style="color:{analysis["color"]};font-weight:bold;">{analysis["level"]}</span></p>
            <p><b>الدرجة:</b> {analysis["score"]}</p>
            <ul>{notes_html}</ul>
        </div>
        """

    content = f"""
    <div class="hero">
        <h1>قسم الحماية</h1>
        <p>اختبر قوة كلمة المرور وتعلم أهم خطوات الحماية العملية.</p>
    </div>

    <div class="split">
        <div class="card">
            <h3>تحليل كلمة المرور</h3>
            <form method="post">
                <label>أدخل كلمة المرور</label>
                <input type="text" name="password_to_check" placeholder="اكتب كلمة المرور لتحليلها" required>
                <button class="btn" type="submit">تحليل</button>
            </form>
            {result}
        </div>

        <div class="card">
            <h3>نصائح أساسية</h3>
            <ul>
                <li>استخدم كلمة مرور طويلة وغير متوقعة.</li>
                <li>فعّل التحقق بخطوتين.</li>
                <li>لا تعيد استخدام نفس كلمة المرور.</li>
                <li>لا تحفظ كلمات المرور في أماكن مكشوفة.</li>
                <li>تأكد من تحديث النظام والمتصفح باستمرار.</li>
            </ul>
        </div>
    </div>
    """
    return render_page("الحماية", content)


@app.route("/quiz", methods=["GET", "POST"])
@login_required
def quiz():
    if request.method == "POST":
        score = 0
        result_blocks = []

        for i, item in enumerate(QUIZ_QUESTIONS):
            user_answer = request.form.get(f"q{i}", "")
            correct = item["answer"]
            if user_answer == correct:
                score += 1
                status = '<span class="badge safe">صحيحة</span>'
            else:
                status = '<span class="badge danger-badge">خاطئة</span>'

            result_blocks.append(f"""
                <div class="card">
                    <h3>السؤال {i+1}</h3>
                    <p>{item["q"]}</p>
                    <p><b>إجابتك:</b> {user_answer if user_answer else "لم يتم الاختيار"} {status}</p>
                    <p><b>الإجابة الصحيحة:</b> {correct}</p>
                    <p><b>التوضيح:</b> {item["explain"]}</p>
                </div>
            """)

        conn = db()
        conn.execute("""
            INSERT INTO quiz_results (user_id, score, total)
            VALUES (?, ?, ?)
        """, (session["user_id"], score, len(QUIZ_QUESTIONS)))
        conn.commit()
        conn.close()

        final_level = "ضعيف"
        if score >= 5:
            final_level = "ممتاز"
        elif score >= 3:
            final_level = "جيد"

        content = f"""
        <div class="hero">
            <h1>نتيجة الاختبار</h1>
            <p>درجتك: <span class="badge safe">{score} / {len(QUIZ_QUESTIONS)}</span></p>
            <p>التقييم العام: <span class="badge medium">{final_level}</span></p>
            <a class="btn" href="{url_for('quiz')}">إعادة الاختبار</a>
        </div>
        {"".join(result_blocks)}
        """
        return render_page("نتيجة الاختبار", content)

    questions_html = ""
    for i, item in enumerate(QUIZ_QUESTIONS):
        choices = ""
        for choice in item["choices"]:
            choices += f"""
            <label style="display:block;margin:8px 0;">
                <input type="radio" name="q{i}" value="{choice}" style="width:auto;margin-left:8px;"> {choice}
            </label>
            """
        questions_html += f"""
        <div class="card">
            <h3>السؤال {i+1}</h3>
            <p>{item["q"]}</p>
            {choices}
        </div>
        """

    content = f"""
    <div class="hero">
        <h1>اختبار الأمن السيبراني</h1>
        <p>أجب عن الأسئلة التالية ثم اعرض نتيجتك في النهاية.</p>
    </div>

    <form method="post">
        {questions_html}
        <br>
        <button class="btn" type="submit">عرض النتيجة</button>
    </form>
    """
    return render_page("الاختبار", content)


@app.route("/chatbot", methods=["GET", "POST"])
@login_required
def chatbot():
    answer = ""
    question = ""

    if request.method == "POST":
        question = request.form.get("question", "").strip()

        answer = "عذرًا، لم أفهم السؤال بشكل كامل. جرّب سؤالًا مثل: ما هو التصيد؟ أو كيف أحمي حسابي؟"
        for key, value in CHATBOT_KNOWLEDGE.items():
            if key in question or question in key:
                answer = value
                break
        else:
            # تحسين بسيط للأسئلة المتقاربة
            q = question.replace("؟", "").strip().lower()
            if "تصيد" in q:
                answer = CHATBOT_KNOWLEDGE["ما هو التصيد"]
            elif "واي" in q or "wifi" in q or "wi-fi" in q:
                answer = CHATBOT_KNOWLEDGE["ما خطر الواي فاي المفتوح"]
            elif "كلمة المرور" in q:
                answer = CHATBOT_KNOWLEDGE["ما هي كلمة المرور القوية"]
            elif "حسابي" in q or "احمي" in q:
                answer = CHATBOT_KNOWLEDGE["كيف أحمي حسابي"]

    sample_questions = "".join([f"<li>{k}</li>" for k in CHATBOT_KNOWLEDGE.keys()])

    content = f"""
    <div class="hero">
        <h1>المستشار الذكي</h1>
        <p>اسأل عن الأمن السيبراني، التصيد، الروابط المشبوهة، كلمات المرور، والحماية.</p>
    </div>

    <div class="split">
        <div class="card">
            <form method="post">
                <label>اكتب سؤالك</label>
                <textarea name="question" placeholder="مثال: كيف أعرف الرابط المزيف؟">{question}</textarea>
                <button class="btn" type="submit">إرسال السؤال</button>
            </form>
        </div>

        <div class="card">
            <h3>الإجابة</h3>
            <p>{answer if answer else "بانتظار سؤالك..."}</p>
        </div>
    </div>

    <div class="card">
        <h3>أسئلة مقترحة</h3>
        <ul>{sample_questions}</ul>
    </div>
    """
    return render_page("الشات بوت", content)


# =========================================================
# لوحة الأدمن
# =========================================================
@app.route("/admin")
@login_required
@admin_required
def admin_panel():
    conn = db()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) as c FROM users")
    users_count = cur.fetchone()["c"]

    cur.execute("SELECT COUNT(*) as c FROM quiz_results")
    quizzes_count = cur.fetchone()["c"]

    cur.execute("SELECT COUNT(*) as c FROM phishing_logs")
    phishing_count = cur.fetchone()["c"]

    cur.execute("SELECT * FROM users ORDER BY id DESC LIMIT 10")
    users = cur.fetchall()

    cur.execute("SELECT * FROM login_logs ORDER BY id DESC LIMIT 15")
    logs = cur.fetchall()

    cur.execute("""
        SELECT p.*, u.username
        FROM phishing_logs p
        LEFT JOIN users u ON p.user_id = u.id
        ORDER BY p.id DESC
        LIMIT 10
    """)
    phishing_logs = cur.fetchall()

    cur.execute("""
        SELECT q.*, u.username
        FROM quiz_results q
        LEFT JOIN users u ON q.user_id = u.id
        ORDER BY q.id DESC
        LIMIT 10
    """)
    quiz_logs = cur.fetchall()

    conn.close()

    users_rows = ""
    for u in users:
        users_rows += f"""
        <tr>
            <td>{u["id"]}</td>
            <td>{u["username"]}</td>
            <td>{"نعم" if u["is_admin"] else "لا"}</td>
            <td>{u["failed_attempts"]}</td>
            <td>{"مقفول" if u["locked"] else "مفتوح"}</td>
            <td>{u["created_at"]}</td>
        </tr>
        """

    login_rows = ""
    for l in logs:
        login_rows += f"""
        <tr>
            <td>{l["username"]}</td>
            <td>{"نجاح" if l["success"] else "فشل"}</td>
            <td>{l["ip_address"]}</td>
            <td>{l["user_agent"][:50]}...</td>
            <td>{l["created_at"]}</td>
        </tr>
        """

    phishing_rows = ""
    for p in phishing_logs:
        phishing_rows += f"""
        <tr>
            <td>{p["username"] if p["username"] else "غير معروف"}</td>
            <td>{p["fake_username"]}</td>
            <td>{p["password_strength"]}</td>
            <td>{p["risk_level"]}</td>
            <td>{p["created_at"]}</td>
        </tr>
        """

    quiz_rows = ""
    for q in quiz_logs:
        quiz_rows += f"""
        <tr>
            <td>{q["username"] if q["username"] else "غير معروف"}</td>
            <td>{q["score"]} / {q["total"]}</td>
            <td>{q["created_at"]}</td>
        </tr>
        """

    content = f"""
    <div class="hero">
        <h1>لوحة الأدمن</h1>
        <p>إدارة ومتابعة الاستخدام داخل المشروع</p>
    </div>

    <div class="grid">
        <div class="card">
            <h3>عدد المستخدمين</h3>
            <p style="font-size:28px;font-weight:bold;">{users_count}</p>
        </div>
        <div class="card">
            <h3>عدد نتائج الاختبارات</h3>
            <p style="font-size:28px;font-weight:bold;">{quizzes_count}</p>
        </div>
        <div class="card">
            <h3>عدد سجلات التصيد</h3>
            <p style="font-size:28px;font-weight:bold;">{phishing_count}</p>
        </div>
    </div>

    <div class="card">
        <h3>آخر المستخدمين</h3>
        <table>
            <tr>
                <th>ID</th>
                <th>اسم المستخدم</th>
                <th>أدمن</th>
                <th>محاولات فاشلة</th>
                <th>الحالة</th>
                <th>تاريخ الإنشاء</th>
            </tr>
            {users_rows}
        </table>
    </div>

    <div class="card">
        <h3>آخر محاولات تسجيل الدخول</h3>
        <table>
            <tr>
                <th>اسم المستخدم</th>
                <th>النتيجة</th>
                <th>IP</th>
                <th>الجهاز</th>
                <th>الوقت</th>
            </tr>
            {login_rows}
        </table>
    </div>

    <div class="card">
        <h3>آخر سجلات محاكاة التصيد</h3>
        <table>
            <tr>
                <th>المستخدم</th>
                <th>الاسم المدخل</th>
                <th>قوة كلمة المرور</th>
                <th>الخطورة</th>
                <th>الوقت</th>
            </tr>
            {phishing_rows}
        </table>
    </div>

    <div class="card">
        <h3>آخر نتائج الاختبارات</h3>
        <table>
            <tr>
                <th>المستخدم</th>
                <th>الدرجة</th>
                <th>الوقت</th>
            </tr>
            {quiz_rows}
        </table>
    </div>

    <div class="card">
        <h3>بيانات الأدمن الحالية</h3>
        <p><b>اسم المستخدم:</b> {ADMIN_USERNAME}</p>
        <p><b>كلمة المرور:</b> {ADMIN_PASSWORD}</p>
        <p class="danger-text">بعد نجاح التشغيل يفضل تغيير كلمة مرور الأدمن إلى كلمة أقوى.</p>
    </div>
    """
    return render_page("لوحة الأدمن", content)


# =========================================================
# تشغيل التطبيق
# =========================================================
init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
