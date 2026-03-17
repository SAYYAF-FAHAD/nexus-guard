from flask import Flask, request, redirect, session, url_for, render_template_string
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import sqlite3
import random
import re
import urllib.parse

app = Flask(__name__)
app.secret_key = "nexus_guard_secret_key_2026"

DB_NAME = "nexus_guard.db"
PROJECT_NAME = "Nexus Guard"

ADMIN_USERNAME = "sayyaf"
ADMIN_PASSWORD = "P@ssw0rd"


# =========================
# قاعدة البيانات
# =========================
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
            password_hash TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS quiz_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            score INTEGER NOT NULL,
            total INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS phishing_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            fake_username TEXT,
            password_strength TEXT,
            risk_level TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()

    # ترقية جدول users لو كان قديم
    user_cols = [row[1] for row in cur.execute("PRAGMA table_info(users)").fetchall()]
    if "is_admin" not in user_cols:
        cur.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0")

    conn.commit()

    # إنشاء الأدمن أو ترقيته
    cur.execute("SELECT * FROM users WHERE username = ?", (ADMIN_USERNAME,))
    admin = cur.fetchone()
    if not admin:
        cur.execute(
            "INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, ?)",
            (ADMIN_USERNAME, generate_password_hash(ADMIN_PASSWORD), 1)
        )
    else:
        cur.execute("UPDATE users SET is_admin = 1 WHERE username = ?", (ADMIN_USERNAME,))

    conn.commit()
    conn.close()


# مهم جدًا: هذا السطر لازم يكون هنا عشان Render يجهز القاعدة
init_db()


# =========================
# بيانات المشروع
# =========================
SCENARIOS = [
    {
        "title": "تتبع شحنتك",
        "icon": "📦",
        "desc": "رسالة تزعم وجود مشكلة في الشحنة وتطلب تحديث البيانات عبر رابط.",
        "tip": "افتح الموقع الرسمي بنفسك ولا تدخل بياناتك من رابط مرسل."
    },
    {
        "title": "تنبيه بنكي",
        "icon": "🏦",
        "desc": "رسالة تخبرك أن الحساب البنكي موقوف ويجب التحقق فورًا.",
        "tip": "البنوك لا تطلب معلوماتك بهذه الطريقة."
    },
    {
        "title": "فزت بجائزة",
        "icon": "🎁",
        "desc": "إشعار وهمي يطلب معلوماتك الشخصية لاستلام الجائزة.",
        "tip": "الجوائز المفاجئة من جهات مجهولة غالبًا احتيال."
    },
    {
        "title": "رسالة واتساب",
        "icon": "📱",
        "desc": "شخص يطلب رمز التحقق أو معلومات شخصية من رقم غير معروف.",
        "tip": "لا ترسل رمز التحقق لأي شخص."
    },
]

WIFI_NETWORKS = [
    {
        "name": "Free_Coffee_WiFi",
        "enc": "مفتوحة",
        "signal": 78,
        "risk": "خطرة",
        "reason": "شبكة مفتوحة بدون تشفير ويمكن اعتراض البيانات خلالها."
    },
    {
        "name": "Airport_FreeNet",
        "enc": "مفتوحة",
        "signal": 65,
        "risk": "خطرة",
        "reason": "شبكة عامة وتعد بيئة مناسبة للتصيد أو التنصت."
    },
    {
        "name": "Secure_Office_WiFi",
        "enc": "WPA2/WPA3",
        "signal": 92,
        "risk": "آمنة",
        "reason": "تشفير جيد وبيئة أكثر موثوقية."
    },
    {
        "name": "Cafe_Staff_Private",
        "enc": "WPA2",
        "signal": 83,
        "risk": "متوسطة",
        "reason": "أفضل من المفتوحة لكن يلزم استخدام كلمة مرور قوية والحذر."
    },
]

QUIZ_QUESTIONS = [
    {
        "question": "هل الشبكات العامة المفتوحة مناسبة لإدخال البيانات البنكية؟",
        "options": ["نعم", "لا", "أحيانًا"],
        "answer": "لا",
        "explanation": "الشبكات العامة قد تكون غير آمنة لاعتراض البيانات."
    },
    {
        "question": "ما الأفضل لحماية الحساب؟",
        "options": ["كلمة مرور فقط", "التحقق الثنائي", "نفس كلمة المرور بكل المواقع"],
        "answer": "التحقق الثنائي",
        "explanation": "التحقق الثنائي يضيف طبقة أمان إضافية قوية."
    },
    {
        "question": "إذا وصلك رابط يطلب تحديث بياناتك من جهة مجهولة، ماذا تفعل؟",
        "options": ["أضغط فورًا", "أتجاهله وأتحقق من الجهة الرسمية", "أرسل بياناتي"],
        "answer": "أتجاهله وأتحقق من الجهة الرسمية",
        "explanation": "هذا الأسلوب شائع في التصيد الاحتيالي."
    },
    {
        "question": "هل مشاركة رمز التحقق مع الآخرين آمنة؟",
        "options": ["نعم", "لا", "إذا كان صديقًا فقط"],
        "answer": "لا",
        "explanation": "رمز التحقق سري جدًا ويمنح وصولًا مباشرًا للحساب."
    },
    {
        "question": "أي كلمة مرور أقوى؟",
        "options": ["12345678", "sayyaf2026", "P@ssw0rd!92#X"],
        "answer": "P@ssw0rd!92#X",
        "explanation": "القوة ترتفع مع الطول والتنوع والرموز."
    },
    {
        "question": "ما الهدف الشائع من رسائل الجوائز الوهمية؟",
        "options": ["الترفيه", "سرقة البيانات", "التوعية"],
        "answer": "سرقة البيانات",
        "explanation": "الهدف غالبًا إغراء الضحية لسرقة معلوماته."
    },
    {
        "question": "هل تحديث النظام والبرامج مهم أمنيًا؟",
        "options": ["نعم", "لا", "فقط إذا بطأ الجهاز"],
        "answer": "نعم",
        "explanation": "التحديثات قد تسد ثغرات أمنية مهمة."
    },
    {
        "question": "ما المقصود بالتصيد الاحتيالي؟",
        "options": ["حماية الشبكة", "خداع المستخدم لسرقة معلوماته", "تسريع الإنترنت"],
        "answer": "خداع المستخدم لسرقة معلوماته",
        "explanation": "التصيد يعتمد على استدراج الضحية لصفحة أو رسالة مزيفة."
    },
    {
        "question": "أي تصرف أفضل عند استخدام Wi-Fi عام؟",
        "options": ["فتح الحساب البنكي", "استخدام VPN وتجنب البيانات الحساسة", "تعطيل الحماية"],
        "answer": "استخدام VPN وتجنب البيانات الحساسة",
        "explanation": "هذا يقلل من المخاطر في الشبكات العامة."
    },
    {
        "question": "هل يجب استخدام نفس كلمة المرور لكل الحسابات؟",
        "options": ["نعم", "لا", "إذا كانت قوية فقط"],
        "answer": "لا",
        "explanation": "تكرار كلمة المرور يضاعف الخطر عند تسريبها."
    }
]

BOT_RESPONSES = {
    "كيف أحمي نفسي من التصيد؟": "تحقق من الرابط بدقة، ولا تدخل بياناتك إلا في المواقع الرسمية التي تصل إليها بنفسك.",
    "هل الواي فاي العام خطر؟": "نعم، خصوصًا إذا كان مفتوحًا. استخدم VPN وتجنب إدخال البيانات الحساسة.",
    "كيف أعرف كلمة المرور قوية؟": "الكلمة القوية تكون طويلة، فيها أحرف كبيرة وصغيرة وأرقام ورموز، ولا تحتوي نمطًا سهلًا.",
    "ما هو التحقق الثنائي؟": "هو طبقة أمان إضافية تطلب رمزًا ثانيًا بعد كلمة المرور.",
    "هل يمكن سرقة حسابي من صفحة مزيفة؟": "نعم، إذا أدخلت بياناتك في صفحة تصيد مزيفة يمكن سرقتها مباشرة."
}


# =========================
# أدوات مساعدة
# =========================
def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        return func(*args, **kwargs)
    return wrapper


def admin_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        if not session.get("is_admin"):
            return redirect(url_for("dashboard"))
        return func(*args, **kwargs)
    return wrapper


def evaluate_password(password):
    score = 0
    notes = []

    if len(password) >= 12:
        score += 2
        notes.append("الطول ممتاز")
    elif len(password) >= 8:
        score += 1
        notes.append("الطول جيد")
    else:
        notes.append("قصيرة")

    if re.search(r"[A-Z]", password):
        score += 1
        notes.append("تحتوي على أحرف كبيرة")
    else:
        notes.append("لا تحتوي على أحرف كبيرة")

    if re.search(r"[a-z]", password):
        score += 1
        notes.append("تحتوي على أحرف صغيرة")
    else:
        notes.append("لا تحتوي على أحرف صغيرة")

    if re.search(r"\d", password):
        score += 1
        notes.append("تحتوي على أرقام")
    else:
        notes.append("لا تحتوي على أرقام")

    if re.search(r"[!@#$%^&*()_\-+=\[{\]};:'\",<.>/?\\|`~]", password):
        score += 2
        notes.append("تحتوي على رموز")
    else:
        notes.append("لا تحتوي على رموز")

    weak_patterns = ["123", "password", "qwerty", "sayyaf", "admin"]
    if any(p in password.lower() for p in weak_patterns):
        score -= 2
        notes.append("تحتوي على نمط سهل التخمين")

    if score <= 2:
        level = "ضعيفة"
        color = "danger"
    elif score <= 5:
        level = "متوسطة"
        color = "warning"
    else:
        level = "قوية"
        color = "success"

    return {
        "level": level,
        "score": max(score, 0),
        "notes": notes,
        "color": color
    }


def svg_data_uri(icon, title, color1="#00e0ff", color2="#00ff9c"):
    svg = f"""
    <svg xmlns='http://www.w3.org/2000/svg' width='900' height='360'>
      <defs>
        <linearGradient id='g' x1='0' y1='0' x2='1' y2='1'>
          <stop offset='0%' stop-color='{color1}'/>
          <stop offset='100%' stop-color='{color2}'/>
        </linearGradient>
      </defs>
      <rect width='100%' height='100%' fill='#071019'/>
      <rect x='20' y='20' rx='28' ry='28' width='860' height='320' fill='url(#g)' opacity='0.14'/>
      <circle cx='760' cy='95' r='70' fill='url(#g)' opacity='0.25'/>
      <circle cx='130' cy='250' r='90' fill='url(#g)' opacity='0.20'/>
      <text x='80' y='170' font-size='90' fill='white'>{icon}</text>
      <text x='190' y='160' font-size='42' font-family='Arial' fill='white'>{title}</text>
      <text x='190' y='215' font-size='22' font-family='Arial' fill='#dcefff'>Nexus Guard</text>
    </svg>
    """
    return "data:image/svg+xml;utf8," + urllib.parse.quote(svg)


def badge_class_from_risk(risk):
    return "success" if risk == "آمنة" else "warning" if risk == "متوسطة" else "danger"


def get_user_level(username):
    conn = db()
    quiz_count = conn.execute(
        "SELECT COUNT(*) AS total FROM quiz_results WHERE username = ?",
        (username,)
    ).fetchone()["total"]
    phish_count = conn.execute(
        "SELECT COUNT(*) AS total FROM phishing_logs WHERE username = ?",
        (username,)
    ).fetchone()["total"]
    conn.close()

    total_score = (quiz_count * 2) + phish_count

    if total_score >= 8:
        return "متقدم"
    elif total_score >= 4:
        return "جيد"
    return "مبتدئ"


def base_page(title, content, user=None):
    admin_link = ""
    if session.get("is_admin"):
        admin_link = '<a href="/admin">لوحة الأدمن</a>'

    nav = ""
    if user:
        nav = f"""
        <nav class="navbar">
            <div class="brand">
                <div class="logo">N</div>
                <div>
                    <div class="brand-title">{PROJECT_NAME}</div>
                    <div class="brand-sub">منصة تفاعلية للتوعية بالأمن السيبراني</div>
                </div>
            </div>
            <div class="links">
                <a href="/dashboard">الرئيسية</a>
                <a href="/cyber-info">الأمن السيبراني</a>
                <a href="/scenarios">السيناريوهات</a>
                <a href="/wifi">تحليل Wi-Fi</a>
                <a href="/hacker">مختبر التجارب</a>
                <a href="/protection">الحماية</a>
                <a href="/quiz">الاختبار</a>
                <a href="/chatbot">الشات بوت</a>
                {admin_link}
                <a class="logout" href="/logout">تسجيل الخروج</a>
            </div>
        </nav>
        """

    html = f"""
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{title}</title>
        <style>
            :root {{
                --bg:#071019;
                --card:#101c2b;
                --text:#ebf3ff;
                --muted:#9cb1c9;
                --primary:#00e0ff;
                --secondary:#00ff9c;
                --danger:#ff4d6d;
                --warning:#ffb703;
                --success:#39d98a;
                --border:rgba(255,255,255,.08);
            }}
            * {{
                box-sizing:border-box;
                margin:0;
                padding:0;
            }}
            body {{
                font-family:Tahoma, Arial, sans-serif;
                background:linear-gradient(135deg, var(--bg), #050b12 45%, #0b1320);
                color:var(--text);
                min-height:100vh;
            }}
            .bg {{
                position:fixed;
                inset:0;
                background-image:
                    linear-gradient(rgba(255,255,255,.03) 1px, transparent 1px),
                    linear-gradient(90deg, rgba(255,255,255,.03) 1px, transparent 1px);
                background-size:26px 26px;
                pointer-events:none;
                z-index:0;
            }}
            .navbar {{
                display:flex;
                justify-content:space-between;
                align-items:center;
                gap:20px;
                padding:14px 22px;
                background:rgba(7,16,25,.92);
                border-bottom:1px solid var(--border);
                position:sticky;
                top:0;
                z-index:20;
                flex-wrap:wrap;
                backdrop-filter: blur(10px);
            }}
            .brand {{
                display:flex;
                align-items:center;
                gap:12px;
            }}
            .logo {{
                width:50px;
                height:50px;
                display:grid;
                place-items:center;
                border-radius:16px;
                background:linear-gradient(135deg, var(--primary), var(--secondary));
                color:#031016;
                font-size:28px;
                font-weight:bold;
                box-shadow:0 0 20px rgba(0,224,255,.35);
            }}
            .brand-title {{
                font-size:20px;
                font-weight:bold;
            }}
            .brand-sub {{
                color:var(--muted);
                font-size:13px;
            }}
            .links {{
                display:flex;
                gap:10px;
                flex-wrap:wrap;
            }}
            .links a {{
                text-decoration:none;
                color:var(--text);
                border:1px solid var(--border);
                padding:10px 14px;
                border-radius:12px;
                background:rgba(255,255,255,.02);
                transition:.2s;
            }}
            .links a:hover {{
                border-color:rgba(0,224,255,.45);
                transform:translateY(-2px);
            }}
            .logout {{
                border-color:rgba(255,77,109,.35) !important;
            }}
            .wrap {{
                max-width:1250px;
                margin:auto;
                padding:24px;
                position:relative;
                z-index:2;
            }}
            .panel {{
                background:linear-gradient(180deg, rgba(16,28,43,.92), rgba(9,17,27,.95));
                border:1px solid var(--border);
                border-radius:22px;
                padding:24px;
                margin-bottom:22px;
                box-shadow:0 10px 35px rgba(0,0,0,.28);
            }}
            .hero {{
                display:grid;
                grid-template-columns:1.2fr 1fr;
                gap:20px;
                align-items:center;
            }}
            .title {{
                font-size:34px;
                margin-bottom:14px;
                line-height:1.5;
            }}
            .sub {{
                color:var(--muted);
                line-height:1.9;
                margin-bottom:18px;
            }}
            .btns {{
                display:flex;
                gap:10px;
                flex-wrap:wrap;
            }}
            .btn {{
                display:inline-block;
                text-decoration:none;
                border:none;
                cursor:pointer;
                padding:12px 18px;
                border-radius:14px;
                font-weight:bold;
                transition:.2s;
            }}
            .btn:hover {{
                transform:translateY(-2px);
            }}
            .btn-primary {{
                background:linear-gradient(135deg, var(--primary), #1cc7ff);
                color:#071019;
            }}
            .btn-secondary {{
                background:linear-gradient(135deg, var(--secondary), #38f2b3);
                color:#071019;
            }}
            .btn-danger {{
                background:linear-gradient(135deg, var(--danger), #ff7591);
                color:#fff;
            }}
            .terminal {{
                background:#03080d;
                border:1px solid rgba(0,255,156,.18);
                border-radius:20px;
                overflow:hidden;
                box-shadow:0 0 25px rgba(0,255,156,.08);
            }}
            .terminal-head {{
                display:flex;
                gap:8px;
                padding:14px 16px;
                background:#07111a;
                border-bottom:1px solid rgba(255,255,255,.06);
            }}
            .terminal-head span {{
                width:12px;
                height:12px;
                border-radius:50%;
            }}
            .terminal-head span:nth-child(1) {{ background:#ff5f57; }}
            .terminal-head span:nth-child(2) {{ background:#febc2e; }}
            .terminal-head span:nth-child(3) {{ background:#28c840; }}
            .terminal-body {{
                min-height:280px;
                padding:22px;
                color:#46ff9d;
                font-family:Consolas, monospace;
                white-space:pre-wrap;
                line-height:1.8;
            }}
            .grid {{
                display:grid;
                grid-template-columns:repeat(auto-fit, minmax(240px, 1fr));
                gap:16px;
            }}
            .card {{
                background:linear-gradient(180deg, rgba(16,28,43,.92), rgba(9,17,27,.95));
                border:1px solid var(--border);
                border-radius:18px;
                padding:20px;
                text-decoration:none;
                color:var(--text);
                transition:.2s;
            }}
            .card:hover {{
                transform:translateY(-4px);
                border-color:rgba(0,224,255,.35);
            }}
            .card p {{
                color:var(--muted);
                margin-top:8px;
                line-height:1.8;
            }}
            .auth {{
                min-height:80vh;
                display:grid;
                place-items:center;
                padding:20px;
            }}
            .auth-card {{
                width:min(100%, 470px);
                background:linear-gradient(180deg, rgba(16,28,43,.95), rgba(9,17,27,.92));
                border:1px solid var(--border);
                border-radius:24px;
                padding:30px;
                box-shadow:0 0 30px rgba(0,255,156,.08);
            }}
            .auth-title {{
                font-size:32px;
                margin-bottom:10px;
            }}
            .auth-sub {{
                color:var(--muted);
                margin-bottom:20px;
            }}
            .field {{
                margin-bottom:12px;
            }}
            input, select {{
                width:100%;
                padding:14px 16px;
                border-radius:14px;
                border:1px solid var(--border);
                background:#08131f;
                color:var(--text);
                outline:none;
            }}
            .msg {{
                padding:14px 16px;
                border-radius:14px;
                margin-bottom:14px;
                border:1px solid var(--border);
            }}
            .success {{ color:#d6ffeb; border-color:rgba(57,217,138,.4); background:rgba(57,217,138,.08); }}
            .warning {{ color:#fff1bf; border-color:rgba(255,183,3,.45); background:rgba(255,183,3,.08); }}
            .danger {{ color:#ffd8e0; border-color:rgba(255,77,109,.45); background:rgba(255,77,109,.08); }}
            .muted {{ color:var(--muted); }}
            .tip {{
                margin-top:12px;
                padding:12px 14px;
                border-radius:14px;
                background:rgba(0,224,255,.08);
                border:1px solid rgba(0,224,255,.16);
                color:#dff8ff;
            }}
            .badge {{
                display:inline-block;
                padding:8px 12px;
                border-radius:999px;
                font-size:13px;
                margin-top:10px;
            }}
            .badge.success {{ background:rgba(57,217,138,.12); color:#bcffe1; }}
            .badge.warning {{ background:rgba(255,183,3,.12); color:#ffeab0; }}
            .badge.danger {{ background:rgba(255,77,109,.12); color:#ffd4dc; }}
            .list {{
                padding-right:18px;
                line-height:1.9;
                color:var(--muted);
            }}
            .question {{
                border:1px solid var(--border);
                border-radius:18px;
                padding:18px;
                margin-bottom:16px;
                background:rgba(255,255,255,.03);
            }}
            .question h3 {{
                margin-bottom:14px;
            }}
            .option {{
                display:block;
                margin-bottom:10px;
                padding:12px 14px;
                border:1px solid var(--border);
                border-radius:12px;
                cursor:pointer;
            }}
            .score {{
                font-size:36px;
                color:var(--secondary);
                margin:10px 0 14px;
            }}
            .chat-box {{
                min-height:280px;
                max-height:420px;
                overflow:auto;
                border:1px solid var(--border);
                border-radius:18px;
                padding:16px;
                background:#07131f;
                margin-bottom:14px;
            }}
            .chat-msg {{
                padding:12px 14px;
                border-radius:14px;
                margin-bottom:10px;
                line-height:1.8;
            }}
            .bot {{
                background:rgba(0,224,255,.09);
                border:1px solid rgba(0,224,255,.15);
            }}
            .user {{
                background:rgba(57,217,138,.12);
                border:1px solid rgba(57,217,138,.2);
            }}
            .inline {{
                display:flex;
                gap:10px;
                flex-wrap:wrap;
            }}
            .inline input {{
                flex:1;
            }}
            .small {{
                font-size:13px;
                color:var(--muted);
            }}
            .table-wrap {{
                overflow:auto;
                margin-top:16px;
            }}
            table {{
                width:100%;
                border-collapse:collapse;
            }}
            th, td {{
                padding:12px;
                text-align:right;
                border-bottom:1px solid var(--border);
            }}
            th {{
                color:#00e0ff;
            }}
            .image-card {{
                width:100%;
                height:180px;
                object-fit:cover;
                border-radius:16px;
                border:1px solid var(--border);
                margin-bottom:14px;
                background:#09131d;
            }}
            .footer {{
                margin-top:50px;
                padding:25px 20px;
                border-top:1px solid rgba(255,255,255,.08);
                text-align:center;
                background:linear-gradient(180deg, rgba(0,0,0,0), rgba(0,224,255,0.03));
            }}
            .footer-content {{
                max-width:700px;
                margin:auto;
            }}
            .footer-title {{
                font-size:20px;
                font-weight:bold;
                color:#00e0ff;
                margin-bottom:10px;
                letter-spacing:1px;
            }}
            .footer-text {{
                font-size:14px;
                color:#9cb1c9;
                line-height:1.9;
                margin-bottom:12px;
            }}
            .footer-copy {{
                font-size:12px;
                color:#6b7f99;
                opacity:0.8;
            }}
            @media (max-width: 900px) {{
                .hero {{
                    grid-template-columns:1fr;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="bg"></div>
        {nav}
        <div class="wrap">
            {content}
            <footer class="footer">
                <div class="footer-content">
                    <div class="footer-title">Nexus Guard</div>
                    <div class="footer-text">
                        تم تطوير هذه المنصة بعناية على يد سياف اليزيدي، ضمن مشروع تقني متقدم
                        يهدف إلى تعزيز الوعي بالأمن السيبراني من خلال تجارب تفاعلية واقعية.
                    </div>
                    <div class="footer-copy">
                        © 2026 جميع الحقوق محفوظة — سياف اليزيدي
                    </div>
                </div>
            </footer>
        </div>
    </body>
    </html>
    """
    return html


# =========================
# الصفحات
# =========================
@app.route("/", methods=["GET", "POST"])
def login():
    message = ""

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        conn = db()
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        conn.close()

        if user and check_password_hash(user["password_hash"], password):
            session["user"] = username
            session["is_admin"] = bool(user["is_admin"])
            return redirect(url_for("dashboard"))
        else:
            message = '<div class="msg danger">بيانات الدخول غير صحيحة.</div>'

    content = f"""
    <section class="auth">
        <div class="auth-card">
            <div class="auth-title">🛡️ {PROJECT_NAME}</div>
            <div class="auth-sub">تسجيل الدخول إلى منصة التوعية بالأمن السيبراني</div>
            {message}
            <form method="POST">
                <div class="field"><input type="text" name="username" placeholder="اسم المستخدم" required></div>
                <div class="field"><input type="password" name="password" placeholder="كلمة المرور" required></div>
                <button class="btn btn-primary" type="submit">دخول</button>
            </form>
            <div style="margin-top:16px;">
                <a class="muted" href="/register">إنشاء حساب جديد</a>
            </div>
        </div>
    </section>
    """
    return render_template_string(base_page("تسجيل الدخول", content))


@app.route("/register", methods=["GET", "POST"])
def register():
    message = ""

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        confirm = request.form.get("confirm_password", "").strip()

        if not username or not password or not confirm:
            message = '<div class="msg danger">جميع الحقول مطلوبة.</div>'
        elif len(username) < 3:
            message = '<div class="msg danger">اسم المستخدم يجب أن يكون 3 أحرف على الأقل.</div>'
        elif password != confirm:
            message = '<div class="msg danger">كلمتا المرور غير متطابقتين.</div>'
        else:
            evaluation = evaluate_password(password)
            if evaluation["level"] == "ضعيفة":
                message = '<div class="msg danger">كلمة المرور ضعيفة. اختر كلمة أقوى.</div>'
            else:
                conn = db()
                try:
                    conn.execute(
                        "INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, ?)",
                        (username, generate_password_hash(password), 0)
                    )
                    conn.commit()
                    conn.close()
                    return redirect(url_for("login"))
                except sqlite3.IntegrityError:
                    conn.close()
                    message = '<div class="msg danger">اسم المستخدم مستخدم بالفعل.</div>'

    content = f"""
    <section class="auth">
        <div class="auth-card">
            <div class="auth-title">إنشاء حساب جديد</div>
            <div class="auth-sub">أنشئ حسابًا للوصول إلى المنصة</div>
            {message}
            <form method="POST">
                <div class="field"><input type="text" name="username" placeholder="اسم المستخدم" required></div>
                <div class="field"><input type="password" name="password" placeholder="كلمة المرور" required></div>
                <div class="field"><input type="password" name="confirm_password" placeholder="تأكيد كلمة المرور" required></div>
                <button class="btn btn-primary" type="submit">إنشاء الحساب</button>
            </form>
            <div style="margin-top:16px;">
                <a class="muted" href="/">العودة لتسجيل الدخول</a>
            </div>
        </div>
    </section>
    """
    return render_template_string(base_page("إنشاء حساب", content))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    username = session["user"]
    level = get_user_level(username)

    conn = db()
    latest_quiz = conn.execute(
        "SELECT * FROM quiz_results WHERE username = ? ORDER BY id DESC LIMIT 1",
        (username,)
    ).fetchone()
    phish_count = conn.execute(
        "SELECT COUNT(*) AS total FROM phishing_logs WHERE username = ?",
        (username,)
    ).fetchone()["total"]
    conn.close()

    latest_result_html = ""
    if latest_quiz:
        latest_result_html = f"""
        <div class="panel">
            <h3>آخر نتيجة لك في الاختبار</h3>
            <p>الدرجة: <strong>{latest_quiz["score"]}/{latest_quiz["total"]}</strong></p>
        </div>
        """

    hero_img = svg_data_uri("🛡️", "منصة التدريب السيبراني", "#00e0ff", "#00ff9c")

    content = f"""
    <section class="panel hero">
        <div>
            <div class="title">مرحبًا {username} في {PROJECT_NAME}</div>
            <div class="sub">
                منصة عربية تجمع بين التوعية والتجارب التفاعلية والتحليل العملي،
                لتعليم المستخدم كيف يحمي نفسه من التصيد الاحتيالي والشبكات غير الآمنة
                وكلمات المرور الضعيفة.
            </div>
            <div class="btns">
                <a class="btn btn-primary" href="/hacker">ابدأ مختبر التجارب</a>
                <a class="btn btn-secondary" href="/quiz">ابدأ الاختبار</a>
            </div>
        </div>
        <div>
            <img class="image-card" src="{hero_img}" alt="Cyber Hero">
        </div>
    </section>

    <section class="grid">
        <div class="card">
            <h3>مستوى المستخدم</h3>
            <p>{level}</p>
        </div>
        <div class="card">
            <h3>تجارب التصيد المكتملة</h3>
            <p>{phish_count}</p>
        </div>
        <div class="card">
            <h3>الوصول السريع</h3>
            <p>ابدأ من مختبر التجارب أو اختبار الوعي السيبراني.</p>
        </div>
    </section>

    <section class="grid">
        <a class="card" href="/cyber-info"><h3>💻 الأمن السيبراني</h3><p>تعريفات ومفاهيم أساسية وأمثلة واقعية.</p></a>
        <a class="card" href="/scenarios"><h3>🎭 السيناريوهات</h3><p>حالات تصيد واحتيال شائعة مع نصائح عملية.</p></a>
        <a class="card" href="/wifi"><h3>📶 تحليل Wi-Fi</h3><p>اختر شبكة واعرف هل هي آمنة أو خطرة.</p></a>
        <a class="card" href="/protection"><h3>🛡️ الحماية</h3><p>نصائح أمنية وفاحص لقوة كلمة المرور.</p></a>
        <a class="card" href="/chatbot"><h3>🤖 الشات بوت</h3><p>مساعد توعوي يجيب عن الأسئلة الشائعة.</p></a>
        <a class="card" href="/quiz"><h3>📝 الاختبار</h3><p>اختبار من 10 أسئلة مع نتيجة نهائية.</p></a>
    </section>

    {latest_result_html}
    """
    return render_template_string(base_page("الرئيسية", content, username))


@app.route("/admin")
@admin_required
def admin_panel():
    conn = db()

    users_count = conn.execute("SELECT COUNT(*) AS total FROM users").fetchone()["total"]
    quiz_count = conn.execute("SELECT COUNT(*) AS total FROM quiz_results").fetchone()["total"]
    phishing_count = conn.execute("SELECT COUNT(*) AS total FROM phishing_logs").fetchone()["total"]

    latest_users = conn.execute("""
        SELECT id, username, is_admin
        FROM users
        ORDER BY id DESC
        LIMIT 10
    """).fetchall()

    quiz_results = conn.execute("""
        SELECT id, username, score, total, created_at
        FROM quiz_results
        ORDER BY id DESC
        LIMIT 20
    """).fetchall()

    phishing_rows = conn.execute("""
        SELECT id, username, fake_username, password_strength, risk_level, created_at
        FROM phishing_logs
        ORDER BY id DESC
        LIMIT 20
    """).fetchall()

    conn.close()

    users_rows = ""
    for row in latest_users:
        role = "أدمن" if row["is_admin"] else "مستخدم"
        users_rows += f"""
        <tr>
            <td>{row["id"]}</td>
            <td>{row["username"]}</td>
            <td>{role}</td>
        </tr>
        """

    quiz_rows = ""
    for row in quiz_results:
        quiz_rows += f"""
        <tr>
            <td>{row["id"]}</td>
            <td>{row["username"]}</td>
            <td>{row["score"]}</td>
            <td>{row["total"]}</td>
            <td>{row["created_at"]}</td>
        </tr>
        """

    phish_table = ""
    for row in phishing_rows:
        phish_table += f"""
        <tr>
            <td>{row["id"]}</td>
            <td>{row["username"]}</td>
            <td>{row["fake_username"]}</td>
            <td>{row["password_strength"]}</td>
            <td>{row["risk_level"]}</td>
            <td>{row["created_at"]}</td>
        </tr>
        """

    content = f"""
    <section class="panel">
        <h2>👑 لوحة الأدمن</h2>
        <p class="sub">هذه الصفحة مخصصة للإدارة فقط وتعرض نظرة شاملة على المستخدمين والنتائج والتجارب.</p>
    </section>

    <section class="grid">
        <div class="card"><h3>عدد المستخدمين</h3><p>{users_count}</p></div>
        <div class="card"><h3>عدد نتائج الاختبار</h3><p>{quiz_count}</p></div>
        <div class="card"><h3>عدد تجارب التصيد</h3><p>{phishing_count}</p></div>
    </section>

    <section class="panel">
        <h3>آخر المستخدمين</h3>
        <div class="table-wrap">
            <table>
                <thead>
                    <tr><th>#</th><th>اسم المستخدم</th><th>النوع</th></tr>
                </thead>
                <tbody>
                    {users_rows if users_rows else '<tr><td colspan="3">لا يوجد مستخدمون</td></tr>'}
                </tbody>
            </table>
        </div>
    </section>

    <section class="panel">
        <h3>آخر نتائج الاختبارات</h3>
        <div class="table-wrap">
            <table>
                <thead>
                    <tr><th>#</th><th>اسم المستخدم</th><th>الدرجة</th><th>من</th><th>التاريخ</th></tr>
                </thead>
                <tbody>
                    {quiz_rows if quiz_rows else '<tr><td colspan="5">لا توجد نتائج</td></tr>'}
                </tbody>
            </table>
        </div>
    </section>

    <section class="panel">
        <h3>آخر تجارب التصيد</h3>
        <div class="table-wrap">
            <table>
                <thead>
                    <tr><th>#</th><th>المستخدم</th><th>الاسم المدخل</th><th>قوة الكلمة</th><th>مستوى الخطر</th><th>التاريخ</th></tr>
                </thead>
                <tbody>
                    {phish_table if phish_table else '<tr><td colspan="6">لا توجد سجلات</td></tr>'}
                </tbody>
            </table>
        </div>
    </section>
    """
    return render_template_string(base_page("لوحة الأدمن", content, session["user"]))


@app.route("/cyber-info")
@login_required
def cyber_info():
    img1 = svg_data_uri("💻", "الأمن السيبراني", "#00e0ff", "#00a3ff")
    img2 = svg_data_uri("🔐", "السرية والنزاهة", "#00ff9c", "#00d4aa")

    content = f"""
    <section class="panel">
        <h2>💻 ما هو الأمن السيبراني؟</h2>
        <p class="sub">
            الأمن السيبراني هو مجال حماية الأنظمة والشبكات والبرامج والبيانات من
            الهجمات الإلكترونية أو الوصول غير المصرح به أو العبث بالمعلومات.
        </p>
    </section>

    <section class="grid">
        <div class="card">
            <img class="image-card" src="{img1}" alt="Cybersecurity">
            <h3>الأساسيات</h3>
            <p>يشمل الأمن السيبراني حماية الأجهزة والهواتف والشبكات والخوادم والبيانات من المخاطر الرقمية.</p>
        </div>

        <div class="card">
            <img class="image-card" src="{img2}" alt="CIA">
            <h3>الأهداف الرئيسية</h3>
            <p>السرية، النزاهة، والتوافر هي الركائز الأساسية لأي نظام آمن.</p>
        </div>
    </section>

    <section class="grid">
        <div class="card"><h3>السرية</h3><p>منع غير المصرح لهم من الوصول إلى المعلومات الحساسة.</p></div>
        <div class="card"><h3>النزاهة</h3><p>ضمان عدم تعديل البيانات أو العبث بها دون إذن.</p></div>
        <div class="card"><h3>التوافر</h3><p>استمرار عمل الأنظمة والخدمات للمستخدمين المصرح لهم.</p></div>
    </section>

    <section class="panel">
        <h3>💡 ما هو Kali Linux؟</h3>
        <p class="sub">
            كالي لينكس نظام مبني على لينكس ومخصص لتعلم الأمن السيبراني واختبار
            الاختراق الأخلاقي، ويحتوي على أدوات تحليل وفحص متقدمة.
        </p>
    </section>
    """
    return render_template_string(base_page("الأمن السيبراني", content, session["user"]))


@app.route("/scenarios")
@login_required
def scenarios():
    cards = ""
    colors = [
        ("#00e0ff", "#00ff9c"),
        ("#4cc9f0", "#4895ef"),
        ("#ff6b6b", "#f06595"),
        ("#ffd43b", "#fab005"),
    ]

    for i, item in enumerate(SCENARIOS):
        c1, c2 = colors[i % len(colors)]
        image = svg_data_uri(item["icon"], item["title"], c1, c2)
        cards += f"""
        <div class="card">
            <img class="image-card" src="{image}" alt="{item["title"]}">
            <h3>{item["icon"]} {item["title"]}</h3>
            <p>{item["desc"]}</p>
            <div class="tip">{item["tip"]}</div>
        </div>
        """

    content = f"""
    <section class="panel">
        <h2>🎭 سيناريوهات احتيال شائعة</h2>
        <p class="sub">هذه الحالات تحاكي أكثر أنواع الخداع انتشارًا في الحياة الرقمية.</p>
        <div class="grid">{cards}</div>
    </section>
    """
    return render_template_string(base_page("السيناريوهات", content, session["user"]))


@app.route("/wifi")
@login_required
def wifi():
    selected_name = request.args.get("name", "")
    selected = None
    for item in WIFI_NETWORKS:
        if item["name"] == selected_name:
            selected = item
            break

    cards = ""
    for net in WIFI_NETWORKS:
        image = svg_data_uri("📶", net["name"], "#00e0ff", "#00ff9c")
        bclass = badge_class_from_risk(net["risk"])
        cards += f"""
        <a class="card" href="/wifi?name={net["name"]}">
            <img class="image-card" src="{image}" alt="{net["name"]}">
            <h3>{net["name"]}</h3>
            <p>التشفير: {net["enc"]}</p>
            <p>قوة الإشارة: {net["signal"]}%</p>
            <span class="badge {bclass}">{net["risk"]}</span>
        </a>
        """

    analysis = ""
    if selected:
        bclass = badge_class_from_risk(selected["risk"])
        note = (
            "هذه الشبكة أفضل من غيرها، ومع ذلك حافظ على الحذر."
            if selected["risk"] == "آمنة"
            else "يمكن استخدامها بحذر مع تجنب إدخال بيانات حساسة."
            if selected["risk"] == "متوسطة"
            else "هذه الشبكة غير مناسبة لإدخال كلمات المرور أو البيانات البنكية."
        )
        analysis = f"""
        <section class="panel">
            <h3>نتيجة التحليل: {selected["name"]}</h3>
            <p class="sub"><strong>مستوى الأمان:</strong> {selected["risk"]}</p>
            <p class="sub"><strong>نوع التشفير:</strong> {selected["enc"]}</p>
            <p class="sub"><strong>قوة الإشارة:</strong> {selected["signal"]}%</p>
            <p class="sub"><strong>السبب:</strong> {selected["reason"]}</p>
            <div class="msg {bclass}">{note}</div>
        </section>
        """

    content = f"""
    <section class="panel">
        <h2>📶 تحليل الشبكات اللاسلكية</h2>
        <p class="sub">اختر أي شبكة لعرض حالة الأمان والتحليل التوعوي الخاص بها.</p>
        <div class="grid">{cards}</div>
    </section>
    {analysis}
    """
    return render_template_string(base_page("تحليل Wi-Fi", content, session["user"]))


@app.route("/hacker", methods=["GET", "POST"])
@login_required
def hacker():
    simulation = """
[+] CYBER EXPERIENCE LAB READY...
[+] WAITING FOR USER INPUT...
[+] أدخل بيانات المحاكاة لرؤية النتيجة التوعوية
    """.strip()

    details = ""

    if request.method == "POST":
        fake_username = request.form.get("fake_username", "").strip()
        fake_password = request.form.get("fake_password", "").strip()

        if fake_username and fake_password:
            fake_ip = f"192.168.{random.randint(10, 250)}.{random.randint(2, 250)}"
            port = random.choice([21, 22, 80, 443, 8080])
            strength = evaluate_password(fake_password)

            simulation = f"""
[+] STARTING EDUCATIONAL EXPERIENCE...
[+] TARGET FORM DETECTED
[+] USERNAME CAPTURED: {fake_username}
[+] PASSWORD CAPTURED: {fake_password}
[+] SOURCE IP: {fake_ip}
[+] OPEN PORT DETECTED: {port}
[+] PASSWORD STRENGTH: {strength["level"]}
[!] WARNING: إدخال البيانات في صفحة مزيفة قد يعرّض الحساب للسرقة
[✔] EXPERIENCE FINISHED
            """.strip()

            notes = "".join([f"<li>{n}</li>" for n in strength["notes"]])
            details = f"""
            <section class="panel">
                <h3>نتيجة التجربة</h3>
                <p class="sub"><strong>اسم المستخدم المدخل:</strong> {fake_username}</p>
                <p class="sub"><strong>قوة كلمة المرور:</strong> {strength["level"]}</p>
                <ul class="list">{notes}</ul>
                <div class="msg danger">هذه تجربة تعليمية فقط، لكنها توضح كيف يمكن لصفحات التصيد أن تجمع بياناتك.</div>
            </section>
            """

    image = svg_data_uri("🧠", "مختبر التجارب السيبرانية", "#00ff9c", "#00e0ff")

    content = f"""
    <section class="panel">
        <h2>🧠 مختبر التجارب السيبرانية</h2>
        <p class="sub">قسم تفاعلي يعرّض المستخدم لتجارب واقعية آمنة تساعده على اكتشاف الخطر قبل الوقوع فيه.</p>
    </section>

    <section class="hero">
        <div class="panel" style="margin-bottom:0;">
            <h3>🎣 نموذج تصيد مزيف</h3>
            <form method="POST" style="margin-top:16px;">
                <div class="field"><input type="text" name="fake_username" placeholder="اسم المستخدم" required></div>
                <div class="field"><input type="password" name="fake_password" placeholder="كلمة المرور" required></div>
                <button class="btn btn-danger" type="submit">تشغيل التجربة</button>
            </form>
        </div>

        <div class="card">
            <img class="image-card" src="{image}" alt="مختبر التجارب">
            <div class="terminal">
                <div class="terminal-head"><span></span><span></span><span></span></div>
                <div class="terminal-body">{simulation}</div>
            </div>
        </div>
    </section>

    {details}
    """
    return render_template_string(base_page("مختبر التجارب", content, session["user"]))


@app.route("/fake-bank", methods=["GET", "POST"])
@login_required
def fake_bank():
    if request.method == "POST":
        fake_user = request.form.get("username", "").strip()
        fake_pass = request.form.get("password", "").strip()

        session["last_fake_user"] = fake_user
        session["last_fake_pass"] = fake_pass

        strength = evaluate_password(fake_pass)
        conn = db()
        conn.execute(
            "INSERT INTO phishing_logs (username, fake_username, password_strength, risk_level) VALUES (?, ?, ?, ?)",
            (session["user"], fake_user, strength["level"], "مرتفع")
        )
        conn.commit()
        conn.close()

        return redirect(url_for("phishing_result"))

    image = svg_data_uri("🏦", "بوابة التحقق البنكي", "#00e0ff", "#ff4d6d")

    content = f"""
    <section class="panel">
        <h2>🏦 بوابة التحقق البنكي</h2>
        <p class="sub">هذه صفحة تدريبية داخل المشروع تحاكي شكل صفحة تصيد تقلد جهة رسمية.</p>
    </section>

    <section class="hero">
        <div class="auth-card" style="margin:0 auto;">
            <div class="auth-title">التحقق من الحساب البنكي</div>
            <div class="auth-sub">يرجى تسجيل الدخول لتأكيد هوية الحساب</div>

            <form method="POST">
                <div class="field"><input type="text" name="username" placeholder="اسم المستخدم أو رقم الهوية" required></div>
                <div class="field"><input type="password" name="password" placeholder="كلمة المرور" required></div>
                <button class="btn btn-danger" type="submit">تسجيل الدخول</button>
            </form>

            <div class="tip">
                كثير من صفحات التصيد تستخدم عبارات مثل: "تحقق الآن فورًا" أو "حسابك موقوف".
            </div>
        </div>

        <div class="card">
            <img class="image-card" src="{image}" alt="بوابة مزيفة">
            <p class="sub">هذه التجربة توضح كيف تبدو بعض الصفحات المزيفة بشكل مقنع للمستخدم.</p>
        </div>
    </section>
    """
    return render_template_string(base_page("صفحة تصيد مزيفة", content, session["user"]))


@app.route("/phishing-result")
@login_required
def phishing_result():
    fake_user = session.get("last_fake_user", "غير معروف")
    fake_pass = session.get("last_fake_pass", "")

    strength = evaluate_password(fake_pass) if fake_pass else {
        "level": "غير معروف",
        "score": 0,
        "notes": []
    }

    notes_html = "".join([f"<li>{note}</li>" for note in strength["notes"]]) if fake_pass else "<li>لا توجد بيانات.</li>"

    content = f"""
    <section class="panel">
        <h2>🚨 نتيجة التجربة</h2>
        <div class="msg danger">
            لقد أدخلت بياناتك في صفحة مشابهة لصفحات التصيد الاحتيالي.
        </div>
        <p class="sub">
            في الواقع، كان من الممكن أن تُجمع هذه المعلومات لاستهداف حسابك أو إعادة استخدام كلمة المرور في مواقع أخرى.
        </p>
    </section>

    <section class="grid">
        <div class="card">
            <h3>البيانات التي أدخلتها</h3>
            <p><strong>اسم المستخدم:</strong> {fake_user}</p>
            <p><strong>تم إدخال كلمة مرور:</strong> نعم</p>
        </div>

        <div class="card">
            <h3>تحليل كلمة المرور</h3>
            <p><strong>التقييم:</strong> {strength["level"]}</p>
            <p><strong>الدرجة:</strong> {strength["score"]}</p>
        </div>
    </section>

    <section class="panel">
        <h3>كيف كان يمكنك اكتشاف الخطر؟</h3>
        <ul class="list">
            <li>الرسالة كانت مستعجلة وتضغط عليك للتصرف فورًا.</li>
            <li>الرابط لم يكن من الموقع الرسمي الذي تصل إليه بنفسك.</li>
            <li>الجهات الرسمية لا تطلب معلوماتك بهذه الطريقة.</li>
            <li>يجب فتح الموقع الرسمي يدويًا بدل الضغط على الروابط.</li>
        </ul>
    </section>

    <section class="panel">
        <h3>تفصيل تقييم كلمة المرور</h3>
        <ul class="list">{notes_html}</ul>
    </section>

    <section class="panel">
        <h3>ما التصرف الصحيح؟</h3>
        <div class="msg success">
            التصرف الصحيح هو تجاهل الرابط، ثم فتح الموقع الرسمي بنفسك أو التواصل مع الجهة مباشرة.
        </div>
        <div class="btns" style="margin-top:14px;">
            <a class="btn btn-primary" href="/protection">العودة إلى صفحة الحماية</a>
            <a class="btn btn-secondary" href="/dashboard">العودة للرئيسية</a>
        </div>
    </section>
    """
    return render_template_string(base_page("نتيجة التصيد", content, session["user"]))


@app.route("/protection", methods=["GET", "POST"])
@login_required
def protection():
    result_html = ""
    password_value = ""

    if request.method == "POST":
        password_value = request.form.get("password", "")
        result = evaluate_password(password_value)
        notes = "".join([f"<li>{n}</li>" for n in result["notes"]])
        result_html = f"""
        <section class="panel">
            <h3>نتيجة التحليل</h3>
            <p class="sub"><strong>التقييم:</strong> <span class="badge {result["color"]}">{result["level"]}</span></p>
            <p class="sub"><strong>الدرجة التقريبية:</strong> {result["score"]}</p>
            <ul class="list">{notes}</ul>
        </section>
        """

    img = svg_data_uri("🛡️", "الحماية الرقمية", "#00ff9c", "#00e0ff")

    content = f"""
    <section class="panel">
        <h2>🛡️ الحماية وفحص كلمة المرور</h2>
        <p class="sub">قسم يجمع بين الإرشادات الأساسية والتجارب العملية التي تساعد المستخدم على اتخاذ القرار الصحيح.</p>
    </section>

    <section class="grid">
        <div class="card"><h3>عدم الثقة بالروابط</h3><p>لا تدخل بياناتك إلا في المواقع الرسمية التي تصل إليها بنفسك.</p></div>
        <div class="card"><h3>تفعيل 2FA</h3><p>التحقق الثنائي يمنع كثيرًا من محاولات الاستيلاء على الحساب.</p></div>
        <div class="card"><h3>التحديثات المستمرة</h3><p>حافظ على تحديث النظام والمتصفح والبرامج باستمرار.</p></div>
    </section>

    <section class="hero">
        <div class="panel" style="margin-bottom:0;">
            <h3>فاحص قوة كلمة المرور</h3>
            <form method="POST" class="inline" style="margin-top:16px;">
                <input type="text" name="password" placeholder="اكتب كلمة المرور للفحص" value="{password_value}">
                <button class="btn btn-primary" type="submit">تحليل الكلمة</button>
            </form>
        </div>
        <div class="card">
            <img class="image-card" src="{img}" alt="الحماية">
        </div>
    </section>

    {result_html}

    <section class="panel">
        <h3>تجربة تصيد تفاعلية</h3>
        <p class="sub">وصلتك رسالة: "تم تعليق حسابك البنكي، حدّث بياناتك فورًا عبر الرابط".</p>
        <div class="btns">
            <a class="btn btn-danger" href="/fake-bank">فتح الرابط</a>
            <button class="btn btn-primary" onclick="alert('✅ أحسنت. التحقق من الجهة الرسمية هو التصرف الصحيح.')">تجاهل والتحقق الرسمي</button>
        </div>
    </section>
    """
    return render_template_string(base_page("الحماية", content, session["user"]))


@app.route("/quiz", methods=["GET", "POST"])
@login_required
def quiz():
    if request.method == "POST":
        score = 0
        total = len(QUIZ_QUESTIONS)

        for idx, item in enumerate(QUIZ_QUESTIONS):
            ans = request.form.get(f"q{idx}")
            if ans == item["answer"]:
                score += 1

        conn = db()
        conn.execute(
            "INSERT INTO quiz_results (username, score, total) VALUES (?, ?, ?)",
            (session["user"], score, total)
        )
        conn.commit()
        conn.close()

        if score == total:
            message = "أحسنت! نتيجتك ممتازة جدًا في الوعي السيبراني."
            cls = "success"
        elif score >= 7:
            message = "أحسنت، مستواك جيد جدًا وتحتاج فقط إلى صقل إضافي."
            cls = "success"
        elif score >= 5:
            message = "نتيجتك جيدة، لكن ما زال لديك مجال واضح للتطوير."
            cls = "warning"
        else:
            message = "تحتاج إلى مزيد من التوعية والمراجعة."
            cls = "danger"

        content = f"""
        <section class="panel">
            <h2>📝 النتيجة النهائية</h2>
            <div class="score">{score} / {total}</div>
            <div class="msg {cls}">{message}</div>
            <a class="btn btn-primary" href="/quiz">إعادة الاختبار</a>
        </section>
        """
        return render_template_string(base_page("نتيجة الاختبار", content, session["user"]))

    question_blocks = ""
    for idx, item in enumerate(QUIZ_QUESTIONS):
        options_html = ""
        for option in item["options"]:
            options_html += f"""
            <label class="option">
                <input type="radio" name="q{idx}" value="{option}" required> {option}
            </label>
            """
        question_blocks += f"""
        <div class="question">
            <h3>{idx + 1}. {item["question"]}</h3>
            {options_html}
            <p class="small">💡 {item["explanation"]}</p>
        </div>
        """

    content = f"""
    <section class="panel">
        <h2>📝 اختبار الوعي السيبراني</h2>
        <form method="POST" style="margin-top:18px;">
            {question_blocks}
            <button class="btn btn-primary" type="submit">إنهاء الاختبار</button>
        </form>
    </section>
    """
    return render_template_string(base_page("الاختبار", content, session["user"]))


@app.route("/chatbot", methods=["GET", "POST"])
@login_required
def chatbot():
    reply = ""
    user_msg = ""

    if request.method == "POST":
        user_msg = request.form.get("message", "").strip()

        if user_msg in BOT_RESPONSES:
            reply = BOT_RESPONSES[user_msg]
        else:
            msg_lower = user_msg.lower()
            if "واي فاي" in user_msg or "wifi" in msg_lower:
                reply = "الشبكات العامة المفتوحة قد تكون خطرة. استخدم VPN ولا تدخل بيانات حساسة."
            elif "كلمة مرور" in user_msg or "الباسورد" in user_msg:
                reply = "استخدم كلمة مرور طويلة، متنوعة، ولا تكررها بين الحسابات."
            elif "تصيد" in user_msg:
                reply = "التصيد يعتمد على الخداع والاستعجال. تحقق من الرابط والجهة الرسمية دائمًا."
            elif "التحقق الثنائي" in user_msg or "2fa" in msg_lower:
                reply = "التحقق الثنائي من أقوى وسائل حماية الحسابات."
            else:
                reply = "أنا مساعد توعوي مخصص للأمن السيبراني. اسألني عن التصيد، الواي فاي، كلمات المرور، أو التحقق الثنائي."

    suggested = "".join(
        f"<button class='btn btn-secondary' type='submit' name='message' value='{q}' style='padding:10px 12px;'>{q}</button>"
        for q in BOT_RESPONSES.keys()
    )

    chat_area = """
    <div class="chat-box">
        <div class="chat-msg bot">مرحبًا بك، أنا المساعد التوعوي للأمن السيبراني. اسألني ما تشاء.</div>
    """
    if user_msg:
        chat_area += f"<div class='chat-msg user'>{user_msg}</div>"
    if reply:
        chat_area += f"<div class='chat-msg bot'>{reply}</div>"
    chat_area += "</div>"

    content = f"""
    <section class="panel">
        <h2>🤖 الشات بوت التوعوي</h2>
        <p class="sub">اكتب سؤالك أو اختر من الأسئلة الجاهزة.</p>
        {chat_area}
        <form method="POST">
            <div class="inline" style="margin-bottom:12px;">
                <input type="text" name="message" placeholder="اكتب سؤالك هنا">
                <button class="btn btn-primary" type="submit">إرسال</button>
            </div>
        </form>
        <form method="POST" class="btns">
            {suggested}
        </form>
    </section>
    """
    return render_template_string(base_page("الشات بوت", content, session["user"]))


if __name__ == "__main__":
    app.run(debug=True)
