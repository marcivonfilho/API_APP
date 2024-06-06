import requests
import psycopg2
import os
import geopandas as gpd
from sqlalchemy import create_engine
from bcrypt import checkpw
import matplotlib
matplotlib.use('agg')
import matplotlib.pyplot as plt

def pool_connect(config):
    try:
        conn = psycopg2.connect(
            host = config['POSTGRES_HOST'],
            port = config['POSTGRES_PORT'],
            database = config['POSTGRES_DB'],
            user = config['POSTGRES_USER'],
            password = config['POSTGRES_PASSWORD']
        )
        return conn
    except psycopg2.Error as e:
        print("Erro ao conectar ao banco de dados:", e)
        return None

def close_connect(conn):
    if conn is not None:
        conn.close()

def autenticateUser(email, senha, config):
    try:
        conn = pool_connect(config)
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

def verifyUser(email, config):
    conn = pool_connect(config)
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

def cadasUser(nome, sobrenome, email, senha, tipoUser, config):
    conn = pool_connect(config)
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO ventos_user (nome, sobrenome, email, senha, tipo_user) VALUES (%s, %s, %s, %s, %s)", 
                    (nome, sobrenome, email, senha, tipoUser))
        conn.commit()
    except psycopg2.Error as e:
        print("Erro ao cadastrar usuário:", e)
        raise
    finally:
        close_connect(conn)

def get_shapefiles(map_type, config):
    url_database = config['SQLALCHEMY_DATABASE_URI']
    engine = create_engine(url_database)
    
    sql_municipios = "SELECT geom FROM br_municipios_2022"
    gdf_municipios = gpd.read_postgis(sql_municipios, engine, geom_col='geom')
    
    if map_type == 'isopleta_nbr': 
        sql_linha = "SELECT geom FROM isopleta_nbr"
    elif map_type == 'isopleta_prop':
        sql_linha = "SELECT geom FROM isopleta_proposta"
    
    gdf_linha = gpd.read_postgis(sql_linha, engine, geom_col='geom')
    engine.dispose()
    return gdf_municipios, gdf_linha

def check_and_process_image(map_type, config):
    processed_images_dir = config['PROCESSED_IMAGES_DIR']
    image_filename = f"map_{map_type}.png"
    image_path = os.path.join(processed_images_dir, image_filename)
    if os.path.exists(image_path):
        return image_path
    else:
        gdf_municipios, gdf_linha = get_shapefiles(map_type, config)
        fig, ax = plt.subplots(figsize=(10, 10))
        gdf_municipios.boundary.plot(ax=ax, linewidth=1, color='lightgray', alpha=0.7)
        gdf_linha.plot(ax=ax, color='red')
        plt.savefig(image_path, format='png')
        plt.close(fig)
        return image_path