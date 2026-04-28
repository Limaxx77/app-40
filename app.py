from flask import Flask, render_template, request, redirect, url_for, session, flash, Response
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime, date, timedelta
import os
import csv
import io
import psycopg2
import psycopg2.extras

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

if DATABASE_URL.startswith("DATABASE_URL="):
    DATABASE_URL = DATABASE_URL.replace("DATABASE_URL=", "", 1).strip()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "troque-esta-chave-em-producao-40graus")


# ================= BANCO POSTGRES =================
def db():
    if not DATABASE_URL:
        raise Exception("DATABASE_URL não configurado.")
    return psycopg2.connect(DATABASE_URL)


def execute(query, params=()):
    conn = db()
    cur = conn.cursor()
    cur.execute(query, params)
    conn.commit()
    cur.close()
    conn.close()


def fetchone(query, params=()):
    conn = db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(query, params)
    result = cur.fetchone()
    cur.close()
    conn.close()
    return result


def fetchall(query, params=()):
    conn = db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(query, params)
    result = cur.fetchall()
    cur.close()
    conn.close()
    return result


def init_db():
    conn = db()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
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
        id SERIAL PRIMARY KEY,
        nome TEXT NOT NULL,
        cargo TEXT,
        salario NUMERIC(10,2) NOT NULL,
        data TEXT,
        status TEXT NOT NULL DEFAULT 'Pendente'
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS contas (
        id SERIAL PRIMARY KEY,
        descricao TEXT NOT NULL,
        categoria TEXT NOT NULL,
        valor NUMERIC(10,2) NOT NULL,
        vencimento TEXT,
        status TEXT NOT NULL DEFAULT 'Pendente',
        codigo_barras TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS scans (
        id SERIAL PRIMARY KEY,
        arquivo TEXT,
        descricao TEXT NOT NULL,
        valor NUMERIC(10,2) NOT NULL,
        vencimento TEXT,
        status TEXT NOT NULL DEFAULT 'Pendente'
    )
    """)

    cur.execute("SELECT COUNT(*) FROM users")
    total = cur.fetchone()[0]

    if total == 0:
        cur.execute("""
            INSERT INTO users (nome, usuario, senha_hash, role, ativo, criado_em)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            "Administrador",
            "admin",
            generate_password_hash("123456", method="pbkdf2:sha256"),
            "admin",
            1,
            datetime.now().isoformat()
        ))

    conn.commit()
    cur.close()
    conn.close()


# ================= FILTROS =================
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


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form.get("usuario")
        senha = request.form.get("senha")

        user = fetchone(
            "SELECT * FROM users WHERE usuario = %s AND ativo = 1",
            (usuario,)
        )

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
    contas = fetchall("SELECT * FROM contas ORDER BY vencimento ASC NULLS LAST")
    salarios = fetchall("SELECT * FROM salarios ORDER BY id DESC")
    scans = fetchall("SELECT * FROM scans ORDER BY id DESC")
    usuarios = fetchall("SELECT * FROM users ORDER BY id DESC")

    hoje = date.today()
    limite = hoje + timedelta(days=7)

    folha = fetchone("SELECT COALESCE(SUM(salario), 0) AS total FROM salarios")["total"]
    contas_pendentes = fetchone("SELECT COALESCE(SUM(valor), 0) AS total FROM contas WHERE status != 'Pago'")["total"]
    contas_pagas = fetchone("SELECT COALESCE(SUM(valor), 0) AS total FROM contas WHERE status = 'Pago'")["total"]
    total_scans = fetchone("SELECT COALESCE(SUM(valor), 0) AS total FROM scans")["total"]

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

    stats = {
        "folha": float(folha or 0),
        "contas_pendentes": float(contas_pendentes or 0),
        "contas_pagas": float(contas_pagas or 0),
        "total_geral": float(folha or 0) + float(contas_pendentes or 0) + float(contas_pagas or 0) + float(total_scans or 0),
        "em_aberto": float(contas_pendentes or 0) + float(total_scans or 0),
        "quitado": float(contas_pagas or 0),
        "vencendo": vencendo,
        "atrasadas": atrasadas
    }

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
    try:
        execute("""
            INSERT INTO users (nome, usuario, senha_hash, role, ativo, criado_em)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            request.form.get("nome"),
            request.form.get("usuario"),
            generate_password_hash(request.form.get("senha"), method="pbkdf2:sha256"),
            request.form.get("role", "usuario"),
            request.form.get("ativo", "1"),
            datetime.now().isoformat()
        ))
        flash("Usuário criado com sucesso.", "success")
    except Exception as e:
        print("Erro ao criar usuário:", e)
        flash("Esse usuário já existe.", "error")

    return redirect(url_for("index"))


@app.route("/usuarios/toggle/<int:id>")
@login_required
@admin_required
def toggle_usuario(id):
    user = fetchone("SELECT ativo FROM users WHERE id = %s", (id,))
    if user:
        novo_status = 0 if user["ativo"] == 1 else 1
        execute("UPDATE users SET ativo = %s WHERE id = %s", (novo_status, id))
    return redirect(url_for("index"))


@app.route("/usuarios/excluir/<int:id>")
@login_required
@admin_required
def excluir_usuario(id):
    execute("DELETE FROM users WHERE id = %s", (id,))
    return redirect(url_for("index"))


# ================= SALÁRIOS =================
@app.route("/salarios/salvar", methods=["POST"])
@login_required
def salvar_salario():
    item_id = request.form.get("id")

    dados = (
        request.form.get("nome"),
        request.form.get("cargo"),
        request.form.get("salario"),
        request.form.get("data"),
        request.form.get("status", "Pendente")
    )

    if item_id:
        execute("""
            UPDATE salarios
            SET nome=%s, cargo=%s, salario=%s, data=%s, status=%s
            WHERE id=%s
        """, dados + (item_id,))
    else:
        execute("""
            INSERT INTO salarios (nome, cargo, salario, data, status)
            VALUES (%s, %s, %s, %s, %s)
        """, dados)

    return redirect(url_for("index"))


@app.route("/salarios/excluir/<int:id>")
@login_required
def excluir_salario(id):
    execute("DELETE FROM salarios WHERE id = %s", (id,))
    return redirect(url_for("index"))


# ================= CONTAS =================
@app.route("/contas/salvar", methods=["POST"])
@login_required
def salvar_conta():
    item_id = request.form.get("id")

    dados = (
        request.form.get("descricao"),
        request.form.get("categoria"),
        request.form.get("valor"),
        request.form.get("vencimento"),
        request.form.get("status", "Pendente"),
        request.form.get("codigo_barras")
    )

    if item_id:
        execute("""
            UPDATE contas
            SET descricao=%s, categoria=%s, valor=%s, vencimento=%s, status=%s, codigo_barras=%s
            WHERE id=%s
        """, dados + (item_id,))
    else:
        execute("""
            INSERT INTO contas (descricao, categoria, valor, vencimento, status, codigo_barras)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, dados)

    return redirect(url_for("index"))


@app.route("/contas/excluir/<int:id>")
@login_required
def excluir_conta(id):
    execute("DELETE FROM contas WHERE id = %s", (id,))
    return redirect(url_for("index"))


# ================= SCANNER =================
@app.route("/scans/salvar", methods=["POST"])
@login_required
def salvar_scan():
    arquivo_file = request.files.get("arquivo")
    nome_arquivo = arquivo_file.filename if arquivo_file and arquivo_file.filename else ""

    execute("""
        INSERT INTO scans (arquivo, descricao, valor, vencimento, status)
        VALUES (%s, %s, %s, %s, %s)
    """, (
        nome_arquivo,
        request.form.get("descricao"),
        request.form.get("valor"),
        request.form.get("vencimento"),
        "Pendente"
    ))

    return redirect(url_for("index"))


@app.route("/scans/excluir/<int:id>")
@login_required
def excluir_scan(id):
    execute("DELETE FROM scans WHERE id = %s", (id,))
    return redirect(url_for("index"))


# ================= EXPORTAR CSV =================
@app.route("/exportar_csv")
@login_required
def exportar_csv():
    contas = fetchall("SELECT * FROM contas ORDER BY id DESC")

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
        headers={"Content-Disposition": "attachment; filename=relatorio_40graus.csv"}
    )


@app.route("/health")
def health():
    return "OK"


try:
    init_db()
except Exception as e:
    print("Erro ao inicializar banco:", e)


if __name__ == "__main__":
    app.run(debug=True)