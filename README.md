# Sistema 40 Graus com Banco de Dados

## Como rodar no VS Code

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Abra no navegador:

```txt
http://127.0.0.1:5000
```

Login inicial:

```txt
Usuário: admin
Senha: 123456
```

Os dados ficam salvos no arquivo `database.sqlite3`. Para outros usuários verem os mesmos dados, todos precisam acessar o mesmo servidor onde o Flask está rodando.
