#Utilizou-se Flask, psycopg2
#conda info --envs      conda activate flaskenv
#conda install -c conda-forge psycopg2-binary
#conda install -c conda-forge bcrypt
#conda install -c conda-forge pandas
#conda install -c conda-forge geopandas matplotlib

from flask import Flask, request, jsonify, send_file
from config import Config
import psycopg2
import geopandas as gpd
from sqlalchemy import create_engine
from sqlalchemy.engine.url import URL
from bcrypt import checkpw
import matplotlib
matplotlib.use('agg')
import matplotlib.pyplot as plt
from io import BytesIO

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
    try:
        conn = pool_connect()
        with conn.cursor() as cur:
            cur.execute("SELECT senha FROM ventos_user WHERE email = %s", (email,))
            senha_cam = cur.fetchone()[0].strip()
            if senha_cam:
                senha1 = senha.encode('utf-8')
                senha2 = senha_cam.encode('utf-8')
                if checkpw(senha1, senha2):
                    return True
            return False
    except psycopg2.Error as e:
        print("Erro ao executar a consulta:", e)
        return False
    except Exception as e:
        print("Erro inesperado:", e)
        return False
    finally:
        if conn:
            close_connect(conn)
    
#Essa função realiza a verificação se o usuário já é cadastrado
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

#Essa função busca os arquivos shapefiles no banco de dados   
def get_shapefiles_nbr():
    url_database = 'postgresql://postgres:appventos@localhost/app_ventos'
    engine = create_engine(url_database)
    # Query para municipios do shapefile
    sql_municipios = "SELECT geom FROM br_municipios_2022"
    gdf_municipios = gpd.read_postgis(sql_municipios, engine, geom_col='geom')

    # Query para linhas do shapefile
    sql_linha = "SELECT geom FROM isopleta_nbr"
    gdf_linha = gpd.read_postgis(sql_linha, engine, geom_col='geom')

    engine.dispose()
    return gdf_municipios, gdf_linha

#Essa função busca os arquivos shapefiles no banco de dados   
def get_shapefiles_proposta():
    url_database = 'postgresql://postgres:appventos@localhost/app_ventos'
    engine = create_engine(url_database)

    # Query para municipios do shapefile
    sql_municipi = "SELECT geom FROM br_municipios_2022"
    gdf_municipi = gpd.read_postgis(sql_municipi, engine, geom_col='geom')

    # Query para linhas do shapefile
    sql_lin = "SELECT geom FROM isopleta_proposta"
    gdf_lin = gpd.read_postgis(sql_lin, engine, geom_col='geom')

    engine.dispose()
    return gdf_municipi, gdf_lin
    
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
   
#Aqui cria a rota para buscar a imagem e mostrar para o usuario   
@app.route('/img_nbr', methods=['GET'])
def img_nbr():
    try:
        gdf_municipios, gdf_linha = get_shapefiles_nbr()
        
        fig, ax = plt.subplots(figsize=(10, 10))
        gdf_municipios.boundary.plot(ax=ax, linewidth=1, color='lightgray', alpha=0.7)
        gdf_linha.plot(ax=ax, color='red')

        img = BytesIO()
        plt.savefig(img, format='png')
        img.seek(0)
        return send_file(img, mimetype='image/png')
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
#Aqui cria a rota para buscar a imagem e mostrar para o usuario   
@app.route('/img_proposta', methods=['GET'])
def img_prop():
    try:
        gdf_municipi, gdf_lin = get_shapefiles_proposta()
        
        fig, ax = plt.subplots(figsize=(10, 10))
        gdf_municipi.boundary.plot(ax=ax, linewidth=1, color='lightgray', alpha=0.7)
        gdf_lin.plot(ax=ax, color='red')

        img = BytesIO()
        plt.savefig(img, format='png')
        img.seek(0)
        return send_file(img, mimetype='image/png')
    except Exception as e:
        return jsonify({'error': str(e)}), 500

#Essa linha de código inicializa o server HTTP
if __name__ == "__main__":
   app.run()