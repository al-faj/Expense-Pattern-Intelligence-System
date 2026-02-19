from flask import Flask, render_template, request, send_file
import sqlite3
import joblib
from datetime import datetime
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib.pagesizes import A4
import os

app = Flask(__name__)

# Load ML model
model, vectorizer = joblib.load("model.pkl")


# ================= DATABASE INIT =================
def init_db():
    conn = sqlite3.connect("expense.db")
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        amount REAL,
        description TEXT,
        date TEXT,
        payment_mode TEXT,
        category TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS budget (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        month INTEGER,
        year INTEGER,
        budget_amount REAL
    )
    """)

    conn.commit()
    conn.close()

init_db()


# ================= HOME ROUTE =================
@app.route("/", methods=["GET", "POST"])
def home():
    conn = sqlite3.connect("expense.db")
    cursor = conn.cursor()

    current_month = datetime.now().month
    current_year = datetime.now().year

    if request.method == "POST":

        # ADD EXPENSE
        if "add_expense" in request.form:
            amount = float(request.form["amount"])
            description = request.form["description"]
            date = request.form["date"]
            payment_mode = request.form["payment_mode"]

            # ML Prediction
            desc_vector = vectorizer.transform([description])
            category = model.predict(desc_vector)[0]

            cursor.execute("""
            INSERT INTO expenses (amount, description, date, payment_mode, category)
            VALUES (?, ?, ?, ?, ?)
            """, (amount, description, date, payment_mode, category))

            conn.commit()

        # SET BUDGET
        if "set_budget" in request.form:
            budget_amount = float(request.form["budget_amount"])

            cursor.execute("DELETE FROM budget WHERE month=? AND year=?",
                           (current_month, current_year))

            cursor.execute("""
            INSERT INTO budget (month, year, budget_amount)
            VALUES (?, ?, ?)
            """, (current_month, current_year, budget_amount))

            conn.commit()

        # RESET CURRENT MONTH
        if "reset_month" in request.form:
            cursor.execute("""
            DELETE FROM expenses
            WHERE strftime('%m', date)=? AND strftime('%Y', date)=?
            """, (f"{current_month:02d}", str(current_year)))

            conn.commit()

    # FETCH TOTAL SPENT
    cursor.execute("""
    SELECT SUM(amount) FROM expenses
    WHERE strftime('%m', date)=? AND strftime('%Y', date)=?
    """, (f"{current_month:02d}", str(current_year)))

    total_spent = cursor.fetchone()[0]
    if total_spent is None:
        total_spent = 0

    # FETCH BUDGET
    cursor.execute("""
    SELECT budget_amount FROM budget
    WHERE month=? AND year=?
    """, (current_month, current_year))

    budget_data = cursor.fetchone()
    budget_amount = budget_data[0] if budget_data else 0

    remaining = budget_amount - total_spent

    # FETCH ALL HISTORY
    cursor.execute("SELECT * FROM expenses ORDER BY date DESC")
    expenses = cursor.fetchall()

    conn.close()

    return render_template("index.html",
                           total_spent=total_spent,
                           budget_amount=budget_amount,
                           remaining=remaining,
                           expenses=expenses)


# ================= PDF DOWNLOAD =================
@app.route("/download_pdf")
def download_pdf():
    conn = sqlite3.connect("expense.db")
    cursor = conn.cursor()

    current_month = datetime.now().month
    current_year = datetime.now().year

    cursor.execute("""
    SELECT amount, description, date, payment_mode, category
    FROM expenses
    WHERE strftime('%m', date)=? AND strftime('%Y', date)=?
    """, (f"{current_month:02d}", str(current_year)))

    expenses = cursor.fetchall()

    cursor.execute("""
    SELECT SUM(amount) FROM expenses
    WHERE strftime('%m', date)=? AND strftime('%Y', date)=?
    """, (f"{current_month:02d}", str(current_year)))

    total_spent = cursor.fetchone()[0] or 0

    cursor.execute("""
    SELECT budget_amount FROM budget
    WHERE month=? AND year=?
    """, (current_month, current_year))

    budget_data = cursor.fetchone()
    budget_amount = budget_data[0] if budget_data else 0

    remaining = budget_amount - total_spent

    conn.close()

    file_path = "Monthly_Expense_Report.pdf"
    doc = SimpleDocTemplate(file_path, pagesize=A4)
    elements = []
    styles = getSampleStyleSheet()

    elements.append(Paragraph("<b>Expense Monthly Report</b>", styles["Title"]))
    elements.append(Spacer(1, 0.3 * inch))
    elements.append(Paragraph(f"Total Spent: ₹ {total_spent}", styles["Normal"]))
    elements.append(Paragraph(f"Budget: ₹ {budget_amount}", styles["Normal"]))
    elements.append(Paragraph(f"Remaining: ₹ {remaining}", styles["Normal"]))
    elements.append(Spacer(1, 0.3 * inch))

    data = [["Amount", "Description", "Date", "Payment Mode", "Category"]]

    for exp in expenses:
        data.append([str(exp[0]), exp[1], exp[2], exp[3], exp[4]])

    table = Table(data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
    ]))

    elements.append(table)
    doc.build(elements)

    return send_file(file_path, as_attachment=True)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
