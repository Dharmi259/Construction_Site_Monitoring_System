# ==============================
# IMPORTS
# ==============================
from flask import Flask, render_template, request, redirect, session, Response, jsonify, send_file, flash
import cv2
import os
import csv
import datetime
import pandas as pd
from ultralytics import YOLO
import random
from flask_mail import Mail, Message

# ==============================
# FLASK APP CONFIG
# ==============================
app = Flask(__name__)
app.secret_key = "csms_secret_key"

# ==============================
# MAIL CONFIG (GMAIL SMTP)
# ==============================
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'dharmiipatell09@gmail.com'
app.config['MAIL_PASSWORD'] = 'ffqq tywp rwqn nyul'

mail = Mail(app)

# ==============================
# LOAD YOLO MODELS
# ==============================
helmet_model = YOLO("csmsbest.pt")
person_model = YOLO("yolov8n.pt")

# ==============================
# GLOBAL VARIABLES
# ==============================
workers = 0
safe_workers = 0
unsafe_workers = 0

video_running = False
webcam_running = False
video_path = None

alarm_running = False

# OTP storage
otp_store = {}

# Folders
UPLOAD_FOLDER = "static/uploads/"
OUTPUT_FOLDER = "static/output/"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# ==============================
# CSV INITIALIZATION
# ==============================

# users.csv
if not os.path.exists("users.csv"):
    with open("users.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["username", "email", "password"])

# safety_report.csv
if not os.path.exists("safety_report.csv"):
    with open("safety_report.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["time", "workers", "safe", "unsafe"])

# ==============================
# OVERLAP FUNCTION
# ==============================
def overlap(boxA, boxB):

    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2])
    yB = min(boxA[3], boxB[3])

    return xA < xB and yA < yB

# ==============================
# OTP GENERATE FUNCTION
# ==============================
def generate_otp():

    otp = str(random.randint(1000, 9999))
    return otp

# ==============================
# SEND OTP EMAIL
# ==============================
def send_otp_email(email, otp):

    msg = Message(
        "CSMS Password Reset OTP",
        sender="dharmiipatell09@gmail.com",
        recipients=[email]
    )

    msg.body = f"""
    CSMS Password Reset

    Your OTP is: {otp}

    This OTP is valid for 5 minutes.

    Do not share this OTP.
    """

    mail.send(msg)


def is_strong_password(password):
    # Min 8 chars, 1 uppercase, 1 number, 1 special char
    pattern = r'^(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$'
    return re.match(pattern, password)

# ==============================
# DETECTION FUNCTION
# ==============================
def detect_frame(frame):

    global workers, safe_workers, unsafe_workers, alarm_running

    workers = 0
    safe_workers = 0
    unsafe_workers = 0

    # lower confidence
    person_results = person_model(frame, conf=0.2)[0]
    helmet_results = helmet_model(frame, conf=0.2)[0]

    person_boxes = []
    helmet_boxes = []
    jacket_boxes = []

    # ======================
    # PERSON DETECTION
    # ======================
    for box in person_results.boxes:

        cls = int(box.cls[0])
        conf = float(box.conf[0])

        if cls == 0:

            x1, y1, x2, y2 = map(int, box.xyxy[0])
            person_boxes.append([x1, y1, x2, y2, conf])

    # ======================
    # HELMET & JACKET
    # ======================
    for box in helmet_results.boxes:

        cls = int(box.cls[0])
        conf = float(box.conf[0])

        x1, y1, x2, y2 = map(int, box.xyxy[0])

        if cls == 0:
            helmet_boxes.append([x1, y1, x2, y2, conf])

        elif cls == 1:
            jacket_boxes.append([x1, y1, x2, y2, conf])

    # ======================
    # PPE CHECK
    # ======================
    for p in person_boxes:

        workers += 1

        px1, py1, px2, py2, pconf = p

        has_helmet = False
        has_jacket = False

        # helmet
        for h in helmet_boxes:

            hx1, hy1, hx2, hy2, hconf = h

            if overlap(p, h):

                has_helmet = True

                cv2.rectangle(frame, (hx1, hy1), (hx2, hy2), (0,255,255), 2)

                cv2.putText(
                    frame,
                    f"Helmet {hconf:.2f}",
                    (hx1, hy1-5),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (0,255,255),
                    2
                )

        # jacket
        for j in jacket_boxes:

            jx1, jy1, jx2, jy2, jconf = j

            if overlap(p, j):

                has_jacket = True

                cv2.rectangle(frame, (jx1, jy1), (jx2, jy2), (255,255,0), 2)

                cv2.putText(
                    frame,
                    f"Jacket {jconf:.2f}",
                    (jx1, jy1-5),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (255,255,0),
                    2
                )

        # safe / unsafe
        if has_helmet and has_jacket:

            safe_workers += 1
            color = (0,255,0)
            label = "SAFE"

        else:

            unsafe_workers += 1
            color = (0,0,255)
            label = "UNSAFE"

        cv2.rectangle(frame, (px1, py1), (px2, py2), color, 3)

        cv2.putText(
            frame,
            f"Person {pconf:.2f} {label}",
            (px1, py1-10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            color,
            2
        )


    # ======================
    # CSV LOG
    # ======================
    with open("safety_report.csv", "a", newline="") as f:

        writer = csv.writer(f)

        writer.writerow([
            datetime.datetime.now(),
            workers,
            safe_workers,
            unsafe_workers
        ])

    return frame

# ==============================
# HOME ROUTE
# ==============================
@app.route("/")
def home():
    if "user" in session:
        return redirect("/dashboard")
    return render_template("login.html")


# ==============================
# LOGIN ROUTE
# ==============================
@app.route("/login", methods=["POST"])
def login():

    username = request.form.get("username")
    password = request.form.get("password")

    if not username or not password:
        flash("Please enter username and password", "danger")
        return redirect("/")

    df = pd.read_csv("users.csv",dtype=str)

    user = df[(df["username"] == username) & (df["password"] == password)]

    if len(user) > 0:

        session["user"] = username
        flash("Login successful", "success")
        return redirect("/dashboard")

    else:
        flash("Invalid username or password", "danger")
        return redirect("/")


# ==============================
# SIGNUP ROUTE
# ==============================
@app.route("/signup", methods=["GET", "POST"])
def signup():

    if request.method == "POST":

        username = request.form.get("username")
        email = request.form.get("email")
        password = request.form.get("password")

        if not username or not email or not password:
            flash("All fields are required", "danger")
            return redirect("/signup")

        df = pd.read_csv("users.csv",dtype=str)

        # username exists
        if username in df["username"].values:
            flash("Username already exists", "danger")
            return redirect("/signup")

        # email exists
        if email in df["email"].values:
            flash("Email already registered", "danger")
            return redirect("/signup")

        with open("users.csv", "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([username, email, password])

        flash("Signup successful. Please login.", "success")
        return redirect("/")

    return render_template("signup.html")


# ==============================
# FORGET PASSWORD
# ==============================
@app.route("/forget_password", methods=["GET", "POST"])
def forget_password():

    if request.method == "POST":

        email = request.form.get("email")

        df = pd.read_csv("users.csv",dtype=str)

        if email not in df["email"].values:
            flash("Email not registered", "danger")
            return redirect("/forget_password")

        otp = generate_otp()

        otp_store[email] = {
            "otp": otp,
            "time": datetime.datetime.now()
        }

        send_otp_email(email, otp)

        flash("OTP sent to your email", "success")
        return render_template("verify_otp.html", email=email)

    return render_template("forget_password.html")


# ==============================
# VERIFY OTP
# ==============================
@app.route("/verify_otp", methods=["POST"])
def verify_otp():

    email = request.form.get("email")
    user_otp = request.form.get("otp")

    if email not in otp_store:
        flash("OTP not found. Try again.", "danger")
        return redirect("/forget_password")

    stored_otp = otp_store[email]["otp"]
    stored_time = otp_store[email]["time"]

    current_time = datetime.datetime.now()

    # 5 minutes expiry
    if (current_time - stored_time).seconds > 300:
        otp_store.pop(email)
        flash("OTP expired. Request again.", "danger")
        return redirect("/forget_password")

    if user_otp != stored_otp:
        flash("Invalid OTP", "danger")
        return render_template("verify_otp.html", email=email)

    flash("OTP verified. Set new password.", "success")
    return render_template("reset_password.html", email=email)


# ==============================
# RESET PASSWORD
# ==============================
@app.route("/reset_password", methods=["POST"])
def reset_password():

    email = request.form.get("email")
    password = request.form.get("password")
    confirm = request.form.get("confirm_password")

    if password != confirm:
        flash("Passwords do not match", "danger")
        return render_template("reset_password.html", email=email)

    df = pd.read_csv("users.csv", dtype=str)

    df.loc[df["email"] == email, "password"] = password

    df.to_csv("users.csv", index=False)

    otp_store.pop(email, None)

    flash("Password updated successfully", "success")

    return redirect("/")

# ==============================
# DASHBOARD
# ==============================
@app.route("/dashboard")
def dashboard():

    if "user" not in session:
        return redirect("/")

    return render_template("dashboard.html")

# ==============================
# RESET DASHBOARD
# ==============================
@app.route("/reset_dashboard", methods=["POST"])
def reset_dashboard():
    global workers, safe_workers, unsafe_workers

    workers = 0
    safe_workers = 0
    unsafe_workers = 0

    # Optional: clear CSV (keep header)
    with open("safety_report.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["time", "workers", "safe", "unsafe"])

    return jsonify({"status": "success"})

# ==============================
# DASHBOARD STATS API
# ==============================
@app.route("/dashboard_stats")
def dashboard_stats():

    global workers, safe_workers, unsafe_workers

    return jsonify({
        "workers": workers,
        "safe": safe_workers,
        "unsafe": unsafe_workers
    })


# ==============================
# IMAGE PAGE
# ==============================
@app.route("/image")
def image_page():

    if "user" not in session:
        return redirect("/")

    return render_template("image.html")


# ==============================
# IMAGE DETECTION
# ==============================
@app.route("/predict_image", methods=["POST"])
def predict_image():

    global workers, safe_workers, unsafe_workers

    file = request.files["image"]
    path = UPLOAD_FOLDER + file.filename
    file.save(path)

    frame = cv2.imread(path)

    frame = detect_frame(frame)

    out = OUTPUT_FOLDER + "output.jpg"
    cv2.imwrite(out, frame)

    return render_template(
        "image.html",
        image_path="/" + out,
        workers=workers,
        safe=safe_workers,
        unsafe=unsafe_workers
    )

# ==============================
# VIDEO PAGE
# ==============================
@app.route("/video")
def video_page():

    if "user" not in session:
        return redirect("/")

    return render_template("video.html")


# ==============================
# START VIDEO
# ==============================
@app.route("/start_video", methods=["POST"])
def start_video():

    global video_path, video_running

    file = request.files.get("video")

    if not file or file.filename == "":
        flash("Upload video first", "danger")
        return redirect("/video")

    video_path = UPLOAD_FOLDER + file.filename
    file.save(video_path)

    video_running = True

    flash("Video started", "success")

    return redirect("/video")


# ==============================
# STOP VIDEO
# ==============================
@app.route("/stop_video", methods=["POST"])
def stop_video():

    global video_running

    video_running = False

    flash("Video stopped", "warning")

    return redirect("/video")


# ==============================
# VIDEO STREAM
# ==============================
@app.route("/video_stream")
def video_stream():

    def generate():

        global video_path, video_running

        if not video_path:
            return

        cap = cv2.VideoCapture(video_path)

        while cap.isOpened():

            if not video_running:
                break

            ret, frame = cap.read()

            if not ret:
                break

            frame = detect_frame(frame)

            _, buffer = cv2.imencode(".jpg", frame)

            yield (
                b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n' +
                buffer.tobytes() +
                b'\r\n'
            )

        cap.release()

    return Response(generate(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


# ==============================
# WEBCAM PAGE
# ==============================
@app.route("/webcam_page")
def webcam_page():

    if "user" not in session:
        return redirect("/")

    return render_template("webcam.html")


# ==============================
# START WEBCAM
# ==============================
@app.route("/start_webcam", methods=["POST"])
def start_webcam():

    global webcam_running

    webcam_running = True

    flash("Webcam started", "success")

    return redirect("/webcam_page")


# ==============================
# STOP WEBCAM
# ==============================
@app.route("/stop_webcam", methods=["POST"])
def stop_webcam():

    global webcam_running

    webcam_running = False

    flash("Webcam stopped", "warning")

    return redirect("/webcam_page")


# ==============================
# WEBCAM STREAM
# ==============================
@app.route("/webcam")
def webcam():

    def generate():

        global webcam_running

        cap = cv2.VideoCapture(0)

        while True:

            ret, frame = cap.read()

            if not ret:
                break

            if webcam_running:
                frame = detect_frame(frame)

            _, buffer = cv2.imencode(".jpg", frame)

            yield (
                b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n' +
                buffer.tobytes() +
                b'\r\n'
            )

        cap.release()

    return Response(generate(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


# ==============================
# DOWNLOAD REPORT
# ==============================
@app.route("/download_report")
def download_report():

    if "user" not in session:
        return redirect("/")

    return send_file("safety_report.csv", as_attachment=True)


# ==============================
# LOGOUT
# ==============================
@app.route("/logout")
def logout():

    session.clear()

    flash("Logged out successfully", "success")

    return redirect("/")

# =========================
# CHART DATA API
# =========================
@app.route("/chart_data")
def chart_data():
    global workers, safe_workers, unsafe_workers

    return jsonify({
        "workers": workers,
        "safe": safe_workers,
        "unsafe": unsafe_workers,
        "time": datetime.datetime.now().strftime("%H:%M:%S")
    })


# =========================
# MONTHLY DATA
# =========================
@app.route("/monthly_data")
def monthly_data():

    df = pd.read_csv("safety_report.csv")

    df["time"] = pd.to_datetime(df["time"])
    df["date"] = df["time"].dt.date

    grouped = df.groupby("date").sum()

    labels = [str(d) for d in grouped.index]

    return jsonify({
        "labels": labels,
        "safe": grouped["safe"].tolist(),
        "unsafe": grouped["unsafe"].tolist()
    })


# ==============================
# RUN APP
# ==============================
if __name__ == "__main__":
    app.run(debug=True)