
from flask import Flask, request, jsonify, render_template, session, redirect, url_for, flash, send_file, send_from_directory
from werkzeug.security import generate_password_hash
import mysql.connector
from io import BytesIO
from PyPDF2 import PdfReader
import subprocess
import os
import json
import bcrypt
import time
from datetime import datetime
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from generate_paper import generate_paper_main



app = Flask(__name__)
app.secret_key = "J@siya123"




# ---------------------- DATABASE CONNECTION ----------------------
def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",        
        password="YOURPASS",        
        database="igcse_db"
    )

# ---------------------- USERS API ----------------------
@app.route('/users', methods=['POST'])
def create_user():
    data = request.json

    # Validate required fields
    required_fields = ['name', 'email', 'password', 'role', 'contact', 'address']
    if not all(field in data for field in required_fields):
        return jsonify({"error": "Missing required fields"}), 400

    # Hash password
    hashed_password = bcrypt.hashpw(data['password'].encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    #  Insert into DB (include name, email, password_hash, contact, address, role)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO users (name, email, password_hash, contact, address, role)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (data['name'], data['email'], hashed_password, data['contact'], data['address'], data['role']))

    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({"message": "User created successfully"}), 201


# ---------------------- FRONTEND ROUTES ----------------------
@app.route("/")
def home():
    return render_template("login.html")  # Login Page

# ---------------------- LOGIN ----------------------
from flask import flash

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        name = request.form.get("name")
        password = request.form.get("password")

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE name=%s", (name,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        if user and bcrypt.checkpw(password.encode("utf-8"), user["password_hash"].encode("utf-8")):
            # Normalize role and add a generic 'id' key
            user["role"] = user["role"].lower().strip()
            user["id"] = user.get("user_id") or user.get("uid")  # adjust to match your DB
            session["user"] = user

            # ✅ Log user login activity
            log_user_action(user["id"], "Login")

            # Redirect based on role
            if user["role"] == "admin":
                return redirect(url_for("admin_dashboard"))
            elif user["role"] == "institute":
                return redirect(url_for("institute_dashboard"))
            elif user["role"] == "student":
                return redirect(url_for("student_dashboard"))
            else:
                return "Role not recognized!"
        return render_template("login.html")

    return render_template("login.html")


# ---------------------- SIGNUP ----------------------
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        role = request.form["role"].lower().strip()
        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]
        contact = request.form["contact"]
        address = request.form["address"]

        if password != confirm_password:
            flash("❌ Passwords do not match!", "error")
            return render_template("signup.html")

        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO users (name, email, password_hash, contact, address, role)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (name, email, hashed_password.decode('utf-8'), contact, address, role))
            conn.commit()
            flash("✅ Signup successful! Please login.", "success")
        except Exception as e:
            flash(f"❌ Error: {str(e)}", "error")
        finally:
            cursor.close()
            conn.close()

        return render_template("signup.html")  # reload same page

    return render_template("signup.html")

#--forgot pasword--
@app.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email")
        new_password = request.form.get("new_password")
        confirm_password = request.form.get("confirm_password")

        # Validation
        if not email or not new_password or not confirm_password:
            flash("All fields are required!", "error")
            return redirect(url_for("forgot_password"))

        if new_password != confirm_password:
            flash("Passwords do not match!", "error")
            return redirect(url_for("forgot_password"))

        # Check if email exists
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()

        if not user:
            flash("Email not found!", "error")
            cursor.close()
            conn.close()
            return redirect(url_for("forgot_password"))

        # Hash and update password
        hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
        cursor.execute("UPDATE users SET password_hash = %s WHERE email = %s", (hashed_password.decode('utf-8'), email))
        conn.commit()
        cursor.close()
        conn.close()

        
        return redirect(url_for("login"))

    return render_template("forgot_password.html")

# PROFILE ROUTE
@app.route("/profile")
def profile():
    if "user" not in session:  # ✅ check dictionary key "user"
        return redirect(url_for("login"))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE user_id = %s", (session["user"]["user_id"],))  # ✅ use session["user"]["user_id"]
    user = cursor.fetchone()
    cursor.close()
    conn.close()

    return render_template("profile.html", user=user)

#settings
@app.route("/settings", methods=["GET", "POST"])
def settings():
    if "user" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == "POST":
        username = request.form.get("username")
        email = request.form.get("email")
        password = request.form.get("password")

        if password:
            hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
            cursor.execute(
                "UPDATE users SET name=%s, email=%s, password_hash=%s WHERE user_id=%s",
                (username, email, hashed_password.decode('utf-8'), session["user"]["user_id"])
            )
        else:
            cursor.execute(
                "UPDATE users SET name=%s, email=%s WHERE user_id=%s",
                (username, email, session["user"]["user_id"])
            )

        conn.commit()

        # Update session
        session["user"]["name"] = username
        session["user"]["email"] = email

        cursor.close()
        conn.close()
        return "✅ Settings updated! <a href='/dashboard'>Back</a>"

    # GET: fetch current user data
    cursor.execute("SELECT * FROM users WHERE user_id=%s", (session["user"]["user_id"],))
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    return render_template("settings.html", user=user)

# LOGOUT ROUTE
@app.route("/logout")
def logout():
    session.clear()                                  
    
    return redirect(url_for("login"))

#---MAIN DASHBOARD---
#redirect to correct dashboard according to their role
@app.route("/dashboard")
def dashboard():
    if "user" not in session: # ✅ FIX: Now checking for the correct session key
        return redirect(url_for("login"))

    # 🔨 FIX: Also normalize the role string here
    role = session["user"]["role"].lower().strip()

    if role == "admin":
        return redirect(url_for("admin_dashboard"))
    elif role == "institute":
        return redirect(url_for("institute_dashboard"))
    elif role == "student":
        return redirect(url_for("student_dashboard"))
    else:
        return "Role not recognized!"

#-------ADMIN------

# ========================
# Helpers
# ========================

def log_admin_action(admin_id, action_type, target_table, target_id=None, description=None):
    if not action_type:  # If action_type is None or empty
        action_type = 'Unknown Action'
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO admin_activity_log (admin_id, action_type, target_table, target_id, description)
        VALUES (%s, %s, %s, %s, %s)
    """, (admin_id, action_type, target_table, target_id, description))
    conn.commit()
    cursor.close()
    conn.close()



def log_user_action(user_id, action, papers_downloaded=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO usage_logs (user_id, action, papers_downloaded, created_at)
            VALUES (%s, %s, %s, NOW())
        """, (user_id, action, papers_downloaded))
        conn.commit()
    except Exception as e:
        print("Error logging user action:", e)
        conn.rollback()
    finally:
        cursor.close()
        conn.close()



# ========================
# Admin Dashboard
# ========================
@app.route("/admin/dashboard")
def admin_dashboard():
    if "user" not in session or session["user"]["role"].lower().strip() != "admin":
        return redirect(url_for("login"))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Total users
    cursor.execute("SELECT COUNT(*) AS total_users FROM users")
    total_users = cursor.fetchone()["total_users"]

    # Papers generated
    cursor.execute("SELECT COUNT(*) AS total_papers FROM generated_paper")
    papers_generated = cursor.fetchone()["total_papers"]

    # Total payments
    cursor.execute("SELECT COALESCE(SUM(amount), 0) AS total_payments FROM payments WHERE status = 'success'")
    total_payments = cursor.fetchone()["total_payments"]

    # Combined recent activity
    cursor.execute("""
        SELECT u.name, al.action_type AS action, al.description AS details, al.created_at
        FROM admin_activity_log al
        JOIN users u ON al.admin_id = u.user_id
        UNION ALL
        SELECT u.name, ul.action, NULL AS details, ul.created_at
        FROM usage_logs ul
        JOIN users u ON ul.user_id = u.user_id
        ORDER BY created_at DESC
        LIMIT 5
    """)
    recent_activity = cursor.fetchall()


    cursor.close()
    conn.close()

    return render_template(
        "admin/dashboard.html",
        user=session["user"],
        stats={
            "total_users": total_users,
            "papers_generated": papers_generated,
            "total_payments": total_payments
        },
        recent_activity=recent_activity
    )

# Manage Users
@app.route("/admin/users")
def manage_users():
    if "user" not in session or session["user"]["role"].lower().strip() != "admin": # 🔨 FIX: Normalize role here too
        return redirect(url_for("login"))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users")
    users = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template("admin/manage_users.html", users=users)

#add user
@app.route("/admin/users/add", methods=["GET", "POST"])
def add_user():
    if "user" not in session or session["user"]["role"].lower().strip() != "admin":
        return redirect(url_for("login"))

    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        password = request.form.get("password")
        role = request.form.get("role")
        contact = request.form.get("contact")
        address = request.form.get("address")

        # Hash password
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        # Insert into DB
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO users (name, email, password_hash, role, contact, address)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (name, email, hashed_password, role, contact, address))
        conn.commit()
        cursor.close()
        conn.close()

        return redirect(url_for("manage_users"))

    # GET request → show form
    return render_template("admin/add_user.html")


# Edit user
@app.route("/admin/users/edit/<int:user_id>", methods=["GET", "POST"])
def edit_user(user_id):
    if "user" not in session or session["user"]["role"].lower().strip() != "admin": # 🔨 FIX: Normalize role here too
        return redirect(url_for("login"))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        role = request.form["role"]

        cursor.execute(
            "UPDATE users SET name=%s, email=%s, role=%s WHERE user_id=%s",
            (name, email, role, user_id),
        )
        conn.commit()
        cursor.close()
        conn.close()

        return redirect(url_for("manage_users"))

    # Fetch user details for the form
    cursor.execute("SELECT * FROM users WHERE user_id=%s", (user_id,))
    user = cursor.fetchone()

    cursor.close()
    conn.close()
    return render_template("admin/edit_user.html", user=user)

# Delete user
@app.route("/admin/users/delete/<int:user_id>", methods=["POST", "GET"])
def delete_user(user_id):
    if "user" not in session or session["user"]["role"].lower().strip() != "admin":
        return redirect(url_for("login"))

    admin_id = session["user"]["id"]
    conn = get_db_connection()
    cursor = conn.cursor()

    # Delete related child records first
    cursor.execute("DELETE FROM usage_logs WHERE user_id = %s", (user_id,))
    cursor.execute("DELETE FROM generated_paper WHERE user_id = %s", (user_id,))

    # Delete user
    cursor.execute("DELETE FROM users WHERE user_id = %s", (user_id,))

    conn.commit()
    cursor.close()
    conn.close()

    # Log the action
    log_admin_action(
        admin_id=admin_id,
        action_type="delete_user",
        target_table="users",
        target_id=user_id,
        description=f"Deleted user with ID {user_id}"
    )

    return redirect(url_for("manage_users"))



# ========================
# Manage Papers
# ========================

# Manage Papers

UPLOAD_FOLDER = "uploads/papers"
ALLOWED_EXTENSIONS = {"pdf", "docx", "jpg", "png"}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
# --- Helpers ---
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

# --- Manage Papers ---
@app.route("/manage_papers")
def manage_papers():
    conn = get_db_connection()
    if not conn:
        flash("Database connection error.", "error")
        return redirect(url_for('login')) # Assuming you have a login route

    cursor = conn.cursor(dictionary=True)

    # Fetch manually uploaded papers
    cursor.execute("SELECT *, 'uploaded' AS type FROM papers ORDER BY created_at DESC")
    uploaded_papers = cursor.fetchall()

    # Fetch generated papers, using 'generated_at'
    cursor.execute("SELECT *, 'generated' AS type FROM generated_paper ORDER BY generated_at DESC")
    generated_papers = cursor.fetchall()

    cursor.close()
    conn.close()

    # Combine the lists and create a common key for sorting
    for p in uploaded_papers:
        p['sort_date'] = p['created_at']
    for p in generated_papers:
        p['sort_date'] = p['generated_at']

    all_papers = sorted(uploaded_papers + generated_papers, key=lambda p: p['sort_date'], reverse=True)

    return render_template("admin/manage_papers.html", papers=all_papers)

@app.route("/download_uploaded_paper/<int:paper_id>")
def download_uploaded_paper(paper_id):
    conn = get_db_connection()
    if not conn:
        return "Database connection error.", 500
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT filename FROM papers WHERE paper_id = %s", (paper_id,))
    paper = cursor.fetchone()
    cursor.close()
    conn.close()

    if not paper or not paper.get('filename'):
        return "Paper not found", 404
    
    return send_from_directory(app.config["UPLOAD_FOLDER"], paper["filename"], as_attachment=True)

@app.route("/download_generated_paper/<int:paper_id>")
def download_generated_paper(paper_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT pdf_url FROM generated_paper WHERE paper_id = %s", (paper_id,))
    paper = cursor.fetchone()
    cursor.close()
    conn.close()

    if not paper or not paper.get('pdf_url'):
        return "Generated paper not found", 404

    # Extract the filename from the URL
    filepath = paper['pdf_url'].lstrip('/')   # remove leading slash
    directory = os.path.dirname(filepath)     # e.g. static/papers
    filename = os.path.basename(filepath)     # e.g. paper_123.pdf

    # ✅ Log the download
    if "user" in session:
        log_user_action(session["user"]["id"], "Downloaded Generated Paper", papers_downloaded=1)

    return send_from_directory(directory, filename, as_attachment=True)

@app.route("/delete_paper/<string:paper_type>/<int:paper_id>", methods=["POST"])
def delete_paper(paper_type, paper_id):
    # You should add an admin check here similar to your previous code
    # if "user" not in session or session["user"]["role"].lower().strip() != "admin":
    #    return redirect(url_for("login"))

    conn = get_db_connection()
    if not conn:
        flash("Database connection error.", "error")
        return redirect(url_for("manage_papers"))
    
    cursor = conn.cursor()
    filename_to_delete = None

    if paper_type == 'uploaded':
        cursor.execute("SELECT filename FROM papers WHERE paper_id = %s", (paper_id,))
        result = cursor.fetchone()
        if result:
            filename_to_delete = result[0]
            cursor.execute("DELETE FROM papers WHERE paper_id = %s", (paper_id,))
    elif paper_type == 'generated':
        cursor.execute("SELECT pdf_url FROM generated_paper WHERE paper_id = %s", (paper_id,))
        result = cursor.fetchone()
        if result:
            filename_to_delete = result[0]
            cursor.execute("DELETE FROM generated_paper WHERE paper_id = %s", (paper_id,))
    else:
        flash("Invalid paper type.", "error")
        cursor.close()
        conn.close()
        return redirect(url_for("manage_papers"))

    conn.commit()
    cursor.close()
    conn.close()

    log_admin_action(
        admin_id=session["user"]["id"],
        action_type="delete_paper",
        target_table="generated_paper" if paper_type=='generated' else 'papers',
        target_id=paper_id,
        description=f"Deleted {paper_type} paper with ID {paper_id}"
    )


    if filename_to_delete:
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename_to_delete)
        if os.path.exists(filepath):
            os.remove(filepath)

    return redirect(url_for("manage_papers"))

# --- Upload Paper ---
@app.route("/upload_paper", methods=["GET", "POST"])
def upload_paper():
    if request.method == "POST":
        title = request.form["title"]
        subject = request.form["subject"]
        file = request.files["file"]

        if file and allowed_file(file.filename):
            filename = file.filename
            filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            file.save(filepath)

            conn = get_db_connection()
            if not conn:
                flash("Database connection error.", "error")
                return redirect(url_for("upload_paper"))
            
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO papers (title, subject, filename) VALUES (%s, %s, %s)",
                (title, subject, filename)
            )
            conn.commit()
            cursor.close()
            conn.close()
            
            log_admin_action(
                admin_id=session["user"]["id"],
                action_type="upload_paper",
                target_table="papers",
                target_id=cursor.lastrowid,
                description=f"Uploaded paper '{title}' for subject '{subject}'"
            )

            return redirect(url_for("manage_papers"))
        else:
            flash("Invalid file type! Only PDF, DOCX, JPG, PNG allowed.", "error")
            return redirect(url_for("upload_paper"))

    return render_template("admin/upload_paper.html")

# Manage Payments
@app.route("/admin/payments")
def manage_payments():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT 
            payments.payment_id,
            users.user_id,
            users.name,
            users.email,
            payments.amount,
            payments.currency,
            payments.method,
            payments.status,
            payments.created_at
        FROM payments
        JOIN users ON payments.user_id = users.user_id
        ORDER BY payments.created_at DESC
    """)
    payments = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("admin/manage_payments.html", payments=payments)

#----student----
# ----------------- STUDENT DASHBOARD -----------------
@app.route("/student/dashboard")
def student_dashboard():
    if "user" not in session or session["user"]["role"].lower().strip() != "student":
        return redirect(url_for("login"))

    user = session["user"]

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Total papers generated by this student
    cursor.execute("SELECT COUNT(*) AS total_papers FROM generated_paper WHERE user_id = %s", (user["id"],))
    total_papers = cursor.fetchone()["total_papers"]

    # Subjects this student has generated papers for
    cursor.execute("SELECT DISTINCT subject FROM generated_paper WHERE user_id = %s", (user["id"],))
    subjects_list = [row["subject"] for row in cursor.fetchall()]
    subjects_str = ", ".join(subjects_list) if subjects_list else "BIOLOGY"

    # Free papers left
    cursor.execute("SELECT papers_downloaded FROM users WHERE user_id = %s", (user["id"],))
    papers_downloaded = cursor.fetchone()["papers_downloaded"]
    free_limit = 3
    free_left = max(free_limit - papers_downloaded, 0)

    # Premium status based on payment table
    cursor.execute("""
        SELECT status 
        FROM payments 
        WHERE user_id = %s 
        ORDER BY created_at DESC LIMIT 1
    """, (user["id"],))
    payment = cursor.fetchone()
    premium_status = "Active" if payment and payment["status"] == "success" else "Inactive"

    # Recent papers
    cursor.execute("""
        SELECT subject, generated_at AS date,
               CASE WHEN has_watermark = 1 THEN 'Generated' ELSE 'Draft' END AS status,
               paper_id
        FROM generated_paper
        WHERE user_id = %s
        ORDER BY generated_at DESC
        LIMIT 5
    """, (user["id"],))
    recent_papers = cursor.fetchall()

    cursor.close()
    conn.close()

    stats = {
        "total_papers": total_papers,
        "subjects": subjects_str,
        "free_left": free_left,
        "premium_status": premium_status
    }

    return render_template(
        "student/dashboard.html",
        user=user,
        stats=stats,
        recent_papers=recent_papers
    )

# --- Institute Dashboard ---
@app.route("/institute/dashboard")
def institute_dashboard():
    if "user" not in session or session["user"]["role"].lower().strip() != "institute":
        return redirect(url_for("login"))

    user = session["user"]

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Total papers generated/uploaded by this institute
    cursor.execute("""
        SELECT COUNT(*) AS total_papers 
        FROM generated_paper 
        WHERE user_id = %s
    """, (user["id"],))
    total_papers = cursor.fetchone()["total_papers"]

    # Subjects list from DB (for this institute)
    cursor.execute("""
        SELECT DISTINCT subject 
        FROM generated_paper 
        WHERE user_id = %s
    """, (user["id"],))
    subjects = [row["subject"] for row in cursor.fetchall()]
    subjects_str = "Mathematics, Biology"

    # Premium status – you can base this on payments table
    cursor.execute("""
        SELECT status 
        FROM payments 
        WHERE user_id = %s 
        ORDER BY created_at DESC LIMIT 1
    """, (user["id"],))
    payment = cursor.fetchone()
    premium_status = "Active" if total_papers > 0 else "Inactive"


    # Recent papers
    cursor.execute("""
        SELECT subject, generated_at AS date, 
               CASE WHEN has_watermark = 1 THEN 'Generated' ELSE 'Draft' END AS status,
               paper_id
        FROM generated_paper
        WHERE user_id = %s
        ORDER BY generated_at DESC
        LIMIT 5
    """, (user["id"],))
    recent_papers = cursor.fetchall()

    cursor.close()
    conn.close()

    stats = {
        "total_papers": total_papers,
        "subjects": subjects_str,
        "premium_status": premium_status
    }

    return render_template(
        "institute/dashboard.html",
        user=user,
        stats=stats,
        recent_papers=recent_papers
    )

#--generate paper--
# -----------------------------
# Generate Paper Route
# -----------------------------
@app.route("/generate_paper", methods=["POST"])
def generate_paper():
    if "user" not in session:
        flash("Please login to generate papers.", "error")
        return redirect(url_for("login"))

    user = session["user"]
    role = user["role"].lower().strip()

    # Prepare paper data
    paper_data = {
        "subject": request.form.get("subject", "Unknown"),
        "watermark": "Burhani College" if role == "student" else (request.form.get("watermark") or "Burhani College"),
        "years": request.form.get("years"),
        "marks": request.form.get("marks")
    }

    if role == "student":
        # Check free papers
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT papers_downloaded FROM users WHERE user_id = %s", (user["id"],))
        usage = cursor.fetchone()
        cursor.close()
        conn.close()

        papers_downloaded = usage["papers_downloaded"] if usage else 0
        free_limit = 3

        if papers_downloaded < free_limit:
            # Generate free paper immediately
            paper_id = generate_paper_after_payment(user, paper_data)

            # Increment papers_downloaded
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET papers_downloaded = papers_downloaded + 1 WHERE user_id = %s", (user["id"],))
            conn.commit()
            cursor.close()
            conn.close()

            return redirect(url_for("preview_paper", paper_id=paper_id))
        else:
            # Free limit reached → require payment
            session["pending_paper"] = paper_data
            flash("You have used your 3 free papers. Please make a payment to generate more.", "error")
            return redirect(url_for("payment_page"))

    elif role == "institute":
        # Always require payment
        session["pending_paper"] = paper_data
       
        return redirect(url_for("payment_page"))

#payment
# -----------------------------
# HELPER: safe integer conversion
# -----------------------------
def safe_int(value, default=30):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

# -----------------------------
# GENERATE PAPER AFTER PAYMENT / FREE
# -----------------------------
# -----------------------------
# GENERATE PAPER AFTER PAYMENT / FREE
# -----------------------------
def generate_paper_after_payment(user, data):
    # Determine watermark based on role
    role = user["role"].lower().strip()
    if role == "student":
        watermark_text = "Burhani College"  # always for students
    else:
        watermark_text = data.get("watermark") or "Burhani College"  # institute: use provided or default

    # Paths
    tex_path = os.path.join("static", "sample.tex")  # your LaTeX input file
    raw_filename = f"raw_paper_{user['id']}_{int(time.time())}.pdf"
    raw_pdf_path = os.path.join("static", "papers", raw_filename)

    # Step 1: Generate AI-based paper
    

    generate_paper_main(
        tex_path,
        raw_pdf_path,
        marks=int(data.get("marks") or 30)
    )


    # Step 2: Add watermark to AI-generated paper
    final_filename = f"paper_{user['id']}_{int(time.time())}.pdf"
    output_dir = os.path.join("static", "papers")
    os.makedirs(output_dir, exist_ok=True)
    final_pdf_path = os.path.join(output_dir, final_filename)

    packet = BytesIO()
    can = canvas.Canvas(packet, pagesize=A4)
    can.setFont("Helvetica-Bold", 60)
    can.setFillGray(0.8, 0.3)
    width, height = A4
    can.saveState()
    can.translate(width / 2, height / 2)
    can.rotate(45)
    can.drawCentredString(0, 0, watermark_text)
    can.restoreState()
    can.save()
    packet.seek(0)

    watermark_pdf = PdfReader(packet)
    reader = PdfReader(open(raw_pdf_path, "rb"))
    writer = PdfWriter()
    for page in reader.pages:
        page.merge_page(watermark_pdf.pages[0])
        writer.add_page(page)

    with open(final_pdf_path, "wb") as f:
        writer.write(f)

    # Step 3: Save in DB
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        INSERT INTO generated_paper (user_id, subject, title, questions, pdf_url, has_watermark, generated_at, preview_url)
        VALUES (%s, %s, %s, %s, %s, %s, NOW(), %s)
    """, (
        user["id"],
        data.get("subject") or "Unknown",
        (data.get("subject") or "Mathematics"),   # 👈 force Mathematics as title if empty
        "[]",
        f"/static/papers/{final_filename}",
        1,
        f"/static/papers/{final_filename}"
    ))

    paper_id = cursor.lastrowid
    conn.commit()
    cursor.close()
    conn.close()

    return paper_id

@app.route("/payment")
def payment_page():
    if "user" not in session:
        return redirect(url_for("login"))
    user = session["user"]
    amount = 500  # dynamic if needed
    return render_template("payment_page.html", user=user, amount=amount)

@app.route("/process_payment", methods=["POST"])
def process_payment():
    if "user" not in session:
        flash("Please login first.", "error")
        return redirect(url_for("login"))

    user = session["user"]

    if "pending_paper" not in session:
        flash("No paper request found.", "error")
        return redirect(url_for("student_dashboard"))

    paper_data = session.pop("pending_paper")

    # Save payment record
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO payments (user_id, amount, currency, method, status)
        VALUES (%s, %s, %s, %s, %s)
    """, (
        user["id"],
        request.form.get("amount", 500),
        request.form.get("currency", "INR"),
        request.form.get("method", "Manual"),
        "success"
    ))
    conn.commit()
    cursor.close()
    conn.close()

    # Generate paper AFTER payment
    paper_id = generate_paper_after_payment(user, paper_data)

    # Increment papers_downloaded for students
    if user["role"].lower().strip() == "student":
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET papers_downloaded = papers_downloaded + 1 WHERE user_id = %s", (user["id"],))
        conn.commit()
        cursor.close()
        conn.close()

    return redirect(url_for("preview_paper", paper_id=paper_id))


@app.route("/request_generate_paper", methods=["POST"])
def request_generate_paper():
    if "user" not in session:
        flash("Please login first.", "error")
        return redirect(url_for("login"))

    user = session["user"]
    role = user["role"].lower().strip()

    # Prepare paper data
    paper_data = {
        "subject": request.form.get("subject", "Unknown"),
        "watermark": "Burhani College" if role == "student" else (request.form.get("watermark") or "Burhani College"),
        "years": request.form.get("years"),
        "marks": request.form.get("marks")
    }

    if role == "student":
        # Student logic: free papers first
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT papers_downloaded FROM users WHERE user_id = %s", (user["id"],))
        usage = cursor.fetchone()
        cursor.close()
        conn.close()

        papers_downloaded = usage["papers_downloaded"] if usage else 0
        free_limit = 3

        if papers_downloaded < free_limit:
            paper_id = generate_paper_after_payment(user, paper_data)

            # Increment free paper count
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET papers_downloaded = papers_downloaded + 1 WHERE user_id = %s", (user["id"],))
            conn.commit()
            cursor.close()
            conn.close()

            return redirect(url_for("preview_paper", paper_id=paper_id))
        else:
            session["pending_paper"] = paper_data
            flash("You have used your 3 free papers. Please make a payment to generate more.", "error")
            return redirect(url_for("payment_page"))

    elif role == "institute":
        # Always redirect to payment page for institutes
        session["pending_paper"] = paper_data
        
        return redirect(url_for("payment_page"))

@app.route("/student_generate_paper")
def student_generate_paper():
    if "user" not in session:
        flash("Please login first.", "error")
        return redirect(url_for("login"))

    if "pending_paper" not in session:
        flash("No paper request found.", "error")
        return redirect(url_for("student_dashboard"))

    user = session["user"]
    paper_data = session.pop("pending_paper")

    # Generate paper
    paper_id = generate_paper_after_payment(user, paper_data)

    # Decrease free paper count in DB
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE users
        SET free_papers_left = free_papers_left - 1
        WHERE user_id = %s
    """, (user["id"],))
    conn.commit()
    cursor.close()
    conn.close()

    return redirect(url_for("preview_paper", paper_id=paper_id))


#--preview paper
@app.route("/preview/<int:paper_id>")
def preview_paper(paper_id):
    # Ensure user is logged in
    if "user" not in session:
        flash("Please login to preview papers.", "error")
        return redirect(url_for("login"))

    user = session["user"]
    role = user["role"].lower().strip()

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Fetch the generated paper by ID
    cursor.execute("SELECT * FROM generated_paper WHERE paper_id = %s", (paper_id,))
    paper = cursor.fetchone()

    cursor.close()
    conn.close()

    if not paper:
        return "Paper not found!", 404

    # Pass the saved PDF URL to template
    pdf_url = paper["pdf_url"]  # must match path saved in DB

    return render_template("preview_paper.html", pdf_url=pdf_url, role=role)

#view all paper
@app.route("/student/all_papers")
def student_all_papers():
    if "user" not in session or session["user"]["role"].lower() != "student":
        return redirect(url_for("login"))

    user = session["user"]
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT paper_id, subject, generated_at, pdf_url,
               CASE WHEN has_watermark = 1 THEN 'Generated' ELSE 'Draft' END AS status
        FROM generated_paper
        WHERE user_id = %s
        ORDER BY generated_at DESC
    """, (user["id"],))
    papers = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template("all_papers.html", user=user, papers=papers)


@app.route("/institute/all_papers")
def institute_all_papers():
    if "user" not in session or session["user"]["role"].lower() != "institute":
        return redirect(url_for("login"))

    user = session["user"]
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT paper_id, subject, generated_at, pdf_url,
               CASE WHEN has_watermark = 1 THEN 'Generated' ELSE 'Draft' END AS status
        FROM generated_paper
        WHERE user_id = %s
        ORDER BY generated_at DESC
    """, (user["id"],))
    papers = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template("all_papers.html", user=user, papers=papers)


# ----------------------------
# SAVE PAPER ROUTE
# ----------------------------
@app.route("/save_paper/<int:paper_id>", methods=["POST"])
def save_paper(paper_id):
    if "user" not in session:
        flash("Please login to save papers.", "error")
        return redirect(url_for("login"))

    user_id = session["user"]["id"]
    subject = request.form.get("subject", "Unknown")
    edited_content = request.form.get("paper_content", "")

    conn = get_db_connection()
    cursor = conn.cursor()

    # Insert into edited_paper table
    cursor.execute("""
        INSERT INTO edited_paper (paper_id, user_id, subject, edited_questions)
        VALUES (%s, %s, %s, %s)
    """, (paper_id, user_id, subject, edited_content))

    conn.commit()
    cursor.close()
    conn.close()

    flash("Edited paper saved successfully!", "success")
    return redirect(url_for("preview_paper", paper_id=paper_id))

if __name__ == "__main__":
    app.run(debug=True)
