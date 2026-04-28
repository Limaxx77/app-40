from werkzeug.security import generate_password_hash

senha = generate_password_hash("123456")
print(senha)