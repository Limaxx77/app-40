from flask import Flask, render_template, request, redirect, url_for, session, flash, Response
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
from pathlib import Path
from functools import wraps
from datetime import datetime, date, timedelta
import csv
import io

APP_DIR = Path(__file__).parent
DB_PATH = APP_DIR / "database.sqlite3"

app = Flask(__name__)
app.secret_key = "troque-esta-chave-em-producao-40graus"


# ================= BANCO =================
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def execute(query, params=()):
    conn = db()
    conn.execute(query, params)
    conn.commit()
    conn.close()


def init_db():
    conn = db()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        usuario TEXT UNIQUE NOT NULL,
        senha_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'usuario',
        ativo INTEGER NOT NULL DEFAULT 1,
        criado_em TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS salarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        cargo TEXT,
        salario REAL NOT NULL,
        data TEXT,
        status TEXT NOT NULL DEFAULT 'Pendente'
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS contas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        descricao TEXT NOT NULL,
        categoria TEXT NOT NULL,
        valor REAL NOT NULL,
        vencimento TEXT,
        status TEXT NOT NULL DEFAULT 'Pendente',
        codigo_barras TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS scans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        arquivo TEXT,
        descricao TEXT NOT NULL,
        valor REAL NOT NULL,
        vencimento TEXT,
        status TEXT NOT NULL DEFAULT 'Pendente'
    )
    """)

    existe_admin = cur.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    if existe_admin == 0:
        cur.execute("""
        INSERT INTO users (nome, usuario, senha_hash, role, ativo, criado_em)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            "Administrador",
            "admin",
            generate_password_hash("123456", method="pbkdf2:sha256"),
            "admin",
            1,
            datetime.now().isoformat()
        ))

    conn.commit()
    conn.close()


# ================= FILTROS HTML =================
@app.context_processor
def utilidades():
    def brl(valor):
        try:
            valor = float(valor or 0)
            return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        except:
            return "R$ 0,00"

    def fmt_date(valor):
        if not valor:
            return "-"
        try:
            return datetime.strptime(valor, "%Y-%m-%d").strftime("%d/%m/%Y")
        except:
            return valor

    return dict(brl=brl, fmt_date=fmt_date)


# ================= LOGIN =================
def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if session.get("role") != "admin":
            flash("Apenas administrador.", "error")
            return redirect(url_for("index"))
        return fn(*args, **kwargs)
    return wrapper


# ================= ROTAS =================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form.get("usuario")
        senha = request.form.get("senha")

        conn = db()
        user = conn.execute(
            "SELECT * FROM users WHERE usuario = ? AND ativo = 1",
            (usuario,)
        ).fetchone()
        conn.close()

        if not user or not check_password_hash(user["senha_hash"], senha):
            flash("Login inválido", "error")
            return redirect(url_for("login"))

        session["user_id"] = user["id"]
        session["role"] = user["role"]
        session["nome"] = user["nome"]

        return redirect(url_for("index"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    conn = db()

    contas = conn.execute("SELECT * FROM contas ORDER BY vencimento ASC").fetchall()
    salarios = conn.execute("SELECT * FROM salarios ORDER BY id DESC").fetchall()
    scans = conn.execute("SELECT * FROM scans ORDER BY id DESC").fetchall()
    usuarios = conn.execute("SELECT * FROM users ORDER BY id DESC").fetchall()

    hoje = date.today()
    limite = hoje + timedelta(days=7)

    folha = conn.execute("""
        SELECT COALESCE(SUM(salario), 0) FROM salarios
    """).fetchone()[0]

    contas_pendentes = conn.execute("""
        SELECT COALESCE(SUM(valor), 0) FROM contas
        WHERE status != 'Pago'
    """).fetchone()[0]

    contas_pagas = conn.execute("""
        SELECT COALESCE(SUM(valor), 0) FROM contas
        WHERE status = 'Pago'
    """).fetchone()[0]

    total_scans = conn.execute("""
        SELECT COALESCE(SUM(valor), 0) FROM scans
    """).fetchone()[0]

    atrasadas = 0
    vencendo = 0

    for c in contas:
        if c["vencimento"]:
            try:
                data_venc = datetime.strptime(c["vencimento"], "%Y-%m-%d").date()
                if c["status"] != "Pago":
                    if data_venc < hoje:
                        atrasadas += 1
                    elif hoje <= data_venc <= limite:
                        vencendo += 1
            except:
                pass

    em_aberto = contas_pendentes + total_scans
    quitado = contas_pagas
    total_geral = folha + contas_pendentes + contas_pagas + total_scans

    stats = {
        "folha": folha,
        "contas_pendentes": contas_pendentes,
        "contas_pagas": contas_pagas,
        "total_geral": total_geral,
        "em_aberto": em_aberto,
        "quitado": quitado,
        "vencendo": vencendo,
        "atrasadas": atrasadas
    }

    conn.close()

    return render_template(
        "index.html",
        stats=stats,
        contas=contas,
        salarios=salarios,
        scans=scans,
        usuarios=usuarios
    )


# ================= USUÁRIOS =================
@app.route("/usuarios/salvar", methods=["POST"])
@login_required
@admin_required
def salvar_usuario():
    nome = request.form.get("nome")
    usuario = request.form.get("usuario")
    senha = request.form.get("senha")
    role = request.form.get("role", "usuario")
    ativo = request.form.get("ativo", "1")

    try:
        execute("""
            INSERT INTO users (nome, usuario, senha_hash, role, ativo, criado_em)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            nome,
            usuario,
            generate_password_hash(senha, method="pbkdf2:sha256"),
            role,
            ativo,
            datetime.now().isoformat()
        ))

        flash("Usuário criado com sucesso.", "success")
    except sqlite3.IntegrityError:
        flash("Esse usuário já existe.", "error")

    return redirect(url_for("index"))


@app.route("/usuarios/toggle/<int:id>")
@login_required
@admin_required
def toggle_usuario(id):
    conn = db()
    user = conn.execute("SELECT ativo FROM users WHERE id = ?", (id,)).fetchone()

    if user:
        novo_status = 0 if user["ativo"] == 1 else 1
        conn.execute("UPDATE users SET ativo = ? WHERE id = ?", (novo_status, id))
        conn.commit()

    conn.close()
    return redirect(url_for("index"))


@app.route("/usuarios/excluir/<int:id>")
@login_required
@admin_required
def excluir_usuario(id):
    execute("DELETE FROM users WHERE id = ?", (id,))
    return redirect(url_for("index"))


# ================= SALÁRIOS =================
@app.route("/salarios/salvar", methods=["POST"])
@login_required
def salvar_salario():
    item_id = request.form.get("id")
    nome = request.form.get("nome")
    cargo = request.form.get("cargo")
    salario = request.form.get("salario")
    data = request.form.get("data")
    status = request.form.get("status", "Pendente")

    if item_id:
        execute("""
            UPDATE salarios
            SET nome=?, cargo=?, salario=?, data=?, status=?
            WHERE id=?
        """, (nome, cargo, salario, data, status, item_id))
    else:
        execute("""
            INSERT INTO salarios (nome, cargo, salario, data, status)
            VALUES (?, ?, ?, ?, ?)
        """, (nome, cargo, salario, data, status))

    return redirect(url_for("index"))


@app.route("/salarios/excluir/<int:id>")
@login_required
def excluir_salario(id):
    execute("DELETE FROM salarios WHERE id = ?", (id,))
    return redirect(url_for("index"))


# ================= CONTAS =================
@app.route("/contas/salvar", methods=["POST"])
@login_required
def salvar_conta():
    item_id = request.form.get("id")
    descricao = request.form.get("descricao")
    categoria = request.form.get("categoria")
    valor = request.form.get("valor")
    vencimento = request.form.get("vencimento")
    status = request.form.get("status", "Pendente")
    codigo_barras = request.form.get("codigo_barras")

    if item_id:
        execute("""
            UPDATE contas
            SET descricao=?, categoria=?, valor=?, vencimento=?, status=?, codigo_barras=?
            WHERE id=?
        """, (descricao, categoria, valor, vencimento, status, codigo_barras, item_id))
    else:
        execute("""
            INSERT INTO contas (descricao, categoria, valor, vencimento, status, codigo_barras)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (descricao, categoria, valor, vencimento, status, codigo_barras))

    return redirect(url_for("index"))


@app.route("/contas/excluir/<int:id>")
@login_required
def excluir_conta(id):
    execute("DELETE FROM contas WHERE id = ?", (id,))
    return redirect(url_for("index"))


# ================= SCANNER =================
@app.route("/scans/salvar", methods=["POST"])
@login_required
def salvar_scan():
    arquivo_file = request.files.get("arquivo")
    nome_arquivo = ""

    if arquivo_file and arquivo_file.filename:
        nome_arquivo = arquivo_file.filename

    descricao = request.form.get("descricao")
    valor = request.form.get("valor")
    vencimento = request.form.get("vencimento")

    execute("""
        INSERT INTO scans (arquivo, descricao, valor, vencimento, status)
        VALUES (?, ?, ?, ?, ?)
    """, (nome_arquivo, descricao, valor, vencimento, "Pendente"))

    return redirect(url_for("index"))


@app.route("/scans/excluir/<int:id>")
@login_required
def excluir_scan(id):
    execute("DELETE FROM scans WHERE id = ?", (id,))
    return redirect(url_for("index"))


# ================= EXPORTAR CSV =================
@app.route("/exportar_csv")
@login_required
def exportar_csv():
    conn = db()
    contas = conn.execute("SELECT * FROM contas").fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["Descrição", "Categoria", "Valor", "Vencimento", "Status", "Código de Barras"])

    for c in contas:
        writer.writerow([
            c["descricao"],
            c["categoria"],
            c["valor"],
            c["vencimento"],
            c["status"],
            c["codigo_barras"]
        ])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=relatorio_40graus.csv"
        }
    )


# ================= START =================
if __name__ == "__main__":
    init_db()
    app.run(debug=True)