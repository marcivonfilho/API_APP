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
    
#Essa função realiza a verificação se existe já o usuário cadastrado
def verifyUser(email):
    conn = pool_connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM ventos_user WHERE email = %s", (email,))
        count = cur.fetchone()[0]
        return count > 0
    except psycopg2.Error as e:
            print("Erro ao executar a consulta:", e)
            return False
    finally:
        close_connect(conn)

    
#Essa função realiza o cadastramento do usuario
def cadasUser(nome, sobrenome, email, senha, tipoUser):
    conn = pool_connect()
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO ventos_user (nome, sobrenome, email, senha, tipo_user) VALUES (%s, %s, %s, %s, %s)", (nome, sobrenome, email, senha, tipoUser))
        conn.commit()
    except psycopg2.Error as e:
        print("Erro ao cadastrar usuário:", e)
        raise
    finally:
        close_connect(conn)
    
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
   
#Aqui cria a rota de Cadastramento do Usuário   
@app.route('/caduser', methods = ['POST'])
def cadUser():
   nome = request.form['nome']
   sobrenome = request.form['sobrenome']
   email = request.form['email']
   senha = request.form['senha']
   tipoUser = request.form['tipoUser']

   try:
      if verifyUser(email):
         return jsonify({'message': 'Usuário já existe'}), 401
      else:
         cadasUser(nome, sobrenome, email, senha, tipoUser)
      return jsonify({'message': 'Usuário Cadastrado com Sucesso'}), 200
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