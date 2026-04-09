from flask import Flask, render_template, request, redirect, url_for, session
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import os
from dotenv import load_dotenv
import sqlite3
import markdown
from groq import Groq
from openai import OpenAI

app = Flask(__name__)
app.secret_key = "minimailer_secret"

load_dotenv()

DEFAULT_EMAIL = os.getenv("DEFAULT_EMAIL")
DEFAULT_PASSWORD = os.getenv("DEFAULT_PASSWORD")
API_KEY = os.getenv("GROQ_API_KEY")

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# ---------------- DATABASE ----------------
def get_db_connection():
    conn = sqlite3.connect("minimailer.db")
    conn.row_factory = sqlite3.Row
    return conn

def create_tables():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS email(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_email TEXT,
        receiver_email TEXT,
        subject TEXT,
        message TEXT,
        send_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("INSERT OR IGNORE INTO users (id, username, password) VALUES (1,'admin','admin123')")

    conn.commit()
    conn.close()

create_tables()

# ---------------- HOME ----------------
@app.route("/index", methods=["GET", "POST"])
def index():
    if "user" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":

        sender_email = request.form.get('sender_email') or DEFAULT_EMAIL
        password = request.form.get('password') or DEFAULT_PASSWORD

        receiver_email = request.form['receiver_email']
        subject = request.form['subject']
        body = request.form['body']
        file = request.files.get('attachment')

        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = receiver_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        if file and file.filename != "":
            filename = file.filename
            temp_path = os.path.join(os.getcwd(), filename)
            file.save(temp_path)

            with open(temp_path, 'rb') as attachment:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(attachment.read())
                encoders.encode_base64(part)
                part.add_header(
                    'Content-Disposition',
                    f'attachment; filename="{filename}"'
                )
                msg.attach(part)

            os.remove(temp_path)

        try:
            with smtplib.SMTP("smtp.gmail.com", 587) as server:
                server.starttls()
                server.login(sender_email, password)
                server.send_message(msg)

            conn = get_db_connection()
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO email (sender_email, receiver_email, subject, message)
                VALUES (?, ?, ?, ?)
            """, (sender_email, receiver_email, subject, body))

            conn.commit()
            conn.close()

            return render_template(
                "result.html",
                message="✅ Email sent successfully!"
            )

        except Exception as e:
            return render_template(
                "result.html",
                message=f"❌ Failed to send email: {e}"
            )

    return render_template("index.html")


@app.route("/")
def home():
    return render_template("home.html")


# ---------------- AI EMAIL GENERATOR ----------------
@app.route("/generate-email", methods=["POST"])
def generate_email():
    if "user" not in session:
        return redirect(url_for("login"))

    email_type = request.form.get("email_type", "professional")
    topic = request.form.get("topic", "general email")

    prompt = f"""
Write a {email_type} email.

Purpose:
{topic}

Return strictly in this format:
Subject:
<subject text>

Body:
<body text>
"""

    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )

        ai_text = response.choices[0].message.content.strip()

        subject = ""
        body = ai_text

        if "Body:" in ai_text:
            subject_part, body_part = ai_text.split("Body:", 1)
            subject = subject_part.replace("Subject:", "").strip()
            body = body_part.strip()

        return render_template(
            "index.html",
            generated_subject=subject,
            generated_email=body
        )

    except Exception as e:
        return render_template(
            "index.html",
            generated_email=f"AI Error: {str(e)}"
        )


# ---------------- LOGIN ----------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM users WHERE username=? AND password=?",
            (username, password)
        )

        user = cursor.fetchone()
        conn.close()

        if user:
            session["user"] = username
            return redirect(url_for("index"))
        else:
            return render_template("login.html", error="Invalid credentials")

    return render_template("login.html")


# ---------------- LOGOUT ----------------
@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("login"))


# ---------------- HISTORY ----------------
@app.route("/history")
def history():
    if "user" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM email ORDER BY send_at DESC")
    emails = cursor.fetchall()

    conn.close()

    return render_template("history.html", emails=emails)


# ---------------- SIGNUP ----------------
@app.route("/signup", methods=["GET", "POST"])
def signup():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            cursor.execute(
                "INSERT INTO users (username, password) VALUES (?, ?)",
                (username, password)
            )

            conn.commit()
            conn.close()

            return render_template(
                "login.html",
                success="✅ Account created successfully!"
            )

        except sqlite3.IntegrityError:

            return render_template(
                "signup.html",
                error="❌ Username already taken"
            )

    return render_template("signup.html")


# ----------------- AI CHAT ----------------------
@app.route("/chat_help", methods=["GET", "POST"])
def chat_help():

    reply = None

    if request.method == "POST":

        user_message = request.form["message"].lower()

        # ✅ FIXED RESPONSE
        if "how to use minimailer" in user_message or "send email" in user_message:

            fixed_answer = """
    ### Steps to Use MiniMailer

        1. First create an account using Signup or login using Login.
        2. After login, open the Email Form.
        3. Use Email Prompt / AI Email Generator to generate email.
        4. Select the Email Type (Professional, Formal, etc).
        5. The Message will automatically fill using AI.
        6. You can rewrite or edit the message if needed.
        7. Enter Recipient Email Address.
        8. Add Attachment if needed.
        9. Click the Submit / Send Email button.
        10. Your email will be sent successfully.
"""

            reply = markdown.markdown(fixed_answer)

        else:
            # 🤖 AI RESPONSE
            response = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "user", "content": user_message}
                ],
                temperature=0.5
            )

            ai_text = response.choices[0].message.content
            reply = markdown.markdown(ai_text)

    return render_template("chat_help.html", reply=reply)

# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(debug=True)