#Utilizou-se Flask, psycopg2
#conda info --envs      conda activate flaskenv
#conda install -c conda-forge psycopg2-binary

from flask import Flask, request, redirect, jsonify
from config import Config
import psycopg2

app = Flask(__name__)
app.config.from_object(Config)

#Criar conexão com o banco de dados
def pool_connect():
    try:
        conn = psycopg2.connect(
            host = app.config['POSTGRES_HOST'],
            port = app.config['POSTGRES_PORT'],
            database = app.config['POSTGRES_DB'],
            user = app.config['POSTGRES_USER'],
            password = app.config['POSTGRES_PASSWORD']
        )
        return conn
    except psycopg2.Error as e:
        print("Erro ao conectar ao banco de dados:", e)
        return None

#Fechar conexão com o banco de dados
def close_connect(conn):
    if conn is not None:
        conn.close()

#Essa função realiza a verificação das credenciais do usuário
def autenticateUser(email, senha):
    conn = pool_connect()
    if conn is not None:
        try:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM ventos_user WHERE email = %s AND senha = %s LIMIT 1", (email, senha))
            exists = cur.fetchone() is not None
            return exists
        except psycopg2.Error as e:
            print("Erro ao executar a consulta:", e)
            return False
        finally:
            close_connect(conn)
    else:
        return False
    
#Aqui cria a rota de login
@app.route('/login', methods = ['POST'])
def login():
   email = request.form['email']
   senha = request.form['senha']

   try:
      if autenticateUser(email,senha):
         return jsonify({'message': 'Login bem-sucedido'}), 200
      else:
         return jsonify({'message': 'Credenciais inválidas'}), 401  
   except Exception as e:
       return jsonify({'message' : str(e)}), 500
   

@app.route('/testlogin')
def test():
   email = 'marcivon71@gmail.com'
   senha = 'MaR1206'
   if autenticateUser(email, senha):
      return jsonify({'message': 'Usuário existe e a senha está correta.'})
   else:
      return jsonify({'message': 'Usuário não encontrado ou senha incorreta.'})


#Essa linha de código inicializa o server HTTP
if __name__ == "__main__":
   app.run()