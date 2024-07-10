import matplotlib
matplotlib.use('agg')
import matplotlib.pyplot as plt
import requests
import psycopg2
import logging
import os
import math
import geopandas as gpd
import pandas as pd
import folium
from shapely.geometry import LineString, MultiLineString
from sqlalchemy import create_engine
from shapely.geometry import Point
from bcrypt import checkpw

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
    
    #sql_municipios = "SELECT geom FROM br_uf_2022"
    #gdf_municipios = gpd.read_postgis(sql_municipios, engine, geom_col='geom')
    
    if map_type == 'isopleta_nbr': 
        sql_linha = "SELECT geometry, velocidade FROM isopleta_nbr"
        gdf_linha = gpd.read_postgis(sql_linha, engine, geom_col='geometry')
        engine.dispose()
        return gdf_linha
    elif map_type == 'isopleta_prop':
        sql_linha = "SELECT geometry, velocidade FROM isopleta_proposta"
        gdf_linha = gpd.read_postgis(sql_linha, engine, geom_col='geometry')
        engine.dispose()
        return gdf_linha
    elif map_type == 'isopleta_nbr_calc':
        sql_linha = "SELECT geom, velocidade FROM norma_nbr_velocidade"
        gdf_linha = gpd.read_postgis(sql_linha, engine, geom_col='geom')
        engine.dispose()
        return gdf_linha

def get_velocity_V0(user_location, gdf_linha):
    try:
        for _, row in gdf_linha.iterrows():
            if row['geom'].contains(user_location):
                velocidade = row['velocidade']
                return velocidade
        else:
            print("A localização do usuário não está dentro de nenhum polígono do shapefile.")
            return None
    except Exception as e:
        logging.error(f"Erro ao encontrar a isopleta mais próxima: {e}")
        raise    

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
    
def check_and_process_html(map_type, config):
    processed_images_dir = config['PROCESSED_IMAGES_DIR']
    html_filename = f"map_{map_type}.html"
    html_path = os.path.join(processed_images_dir, html_filename)
    
    if os.path.exists(html_path):
        print(f'HTML file {html_filename} already exists')
        return html_path
    else:
        print(f'Generating new HTML file {html_filename}')

        url = 'https://raw.githubusercontent.com/codeforamerica/click_that_hood/master/public/data/brazil-states.geojson'
        response = requests.get(url)
        brazil_geojson = response.json()

        gdf_linha = get_shapefiles(map_type, config)

        m = folium.Map(location=[-14.2350, -51.9253], zoom_start=4, tiles='cartodbpositron')
        
        folium.GeoJson(brazil_geojson, style_function=lambda x: {
            'fillColor': '#fafad2',
            'color': '#c0c0c0',
            'weight': 4,
            'fillOpacity': 0.1,
        }).add_to(m)

        for _, row in gdf_linha.iterrows():
            if isinstance(row.geometry, LineString):
                coords = [(coord[1], coord[0]) for coord in row.geometry.coords]
                folium.PolyLine(
                    locations=coords,
                    color='red',
                    weight=2,
                    popup=folium.Popup(f'Velocidade vento V0: <b>{row.velocidade:.2f} m/s</b>', max_width=300),
                    line_cap='round'
                ).add_to(m)
            elif isinstance(row.geometry, MultiLineString):
                for line in row.geometry.geoms:  # Acesse as sub-geometrias corretamente
                    coords = [(coord[1], coord[0]) for coord in line.coords]
                    folium.PolyLine(
                        locations=coords,
                        color='red',
                        weight=6,
                        popup=folium.Popup(f'Velocidade vento V0: <b>{row.velocidade:.2f} m/s</b>', max_width=300),
                        line_cap='round'
                    ).add_to(m)

        m.save(html_path)
        print(f'HTML file {html_filename} saved at {html_path}')

        html_path = os.path.join(processed_images_dir, html_filename)

        return html_path
    
def get_velocity_VK(alturaz, fatorS1, anguloTeta, dt, categoriaS2, rajadaS2, fatorS3, velocidadeV0):
    #Calculo Fator S1
    if fatorS1 == 'Terreno plano ou fracamente acidentado':
        fators1 = float(1)
    elif fatorS1 == 'Taludes e morros':
        if (anguloTeta <= 3):
            fators1 = float(1)
        elif (6 <= anguloTeta <= 17):
            tg_angulo = math.tan(math.radians(anguloTeta - 3))
            fators1 = float(1 + (2.5-(alturaz/dt)) *  tg_angulo)
        elif (anguloTeta >= 45) :
            fators1 = float(1 + (2.5-(alturaz/dt)) *  0.31)
        elif (3 < anguloTeta < 6):
            sfi3 = float(1)
            tg_angulo = math.tan(math.radians(anguloTeta - 3))
            sfs6 = float(1 + (2.5-(alturaz/dt)) *  tg_angulo)
            fators1 = float(sfi3 + ((anguloTeta - 3)/(6-3)) * (sfs6 - sfi3))
        elif (17 < anguloTeta < 45):
            tg_angulo = math.tan(math.radians(anguloTeta - 3))
            sfi17 = float(1 + (2.5-(alturaz/dt)) *  tg_angulo)
            sfs45 = float(1 + (2.5-(alturaz/dt)) *  0.31)
            fators1 = float(sfi17 + ((anguloTeta - 17)/(45-17)) * (sfs45 - sfi17))
    elif fatorS1 == 'Vales profundos':
        fators1 = float(0.9)

    #Calculo do Fator S2
    df_tb_parametros = pd.read_csv('tabela_parametros.csv')
    df_tb_frajada = pd.read_csv('tabela_fr_rajadas.csv')
    #Filtro para acessar os valores da categoria desejada
    df_categoria = df_tb_parametros[df_tb_parametros['Categoria'] == categoriaS2]
    #Filtro para acessar os valores de bm e p para a classe desejada
    bm = df_categoria.loc[df_categoria.index, rajadaS2].values[0]
    p = df_categoria.loc[df_categoria.index, rajadaS2].values[1]
    #Buscar o valor do Fator de Rajada
    fr = df_tb_frajada.loc[0, rajadaS2]
    #Realiza o calculo do S2
    fators2 = float(bm * fr * ((alturaz / 10) ** p))

    print(bm, fr, p)
    
    #Fator Estatistico S3
    df_tb_fs3 = pd.read_csv('tabela_fators3.csv')
    df_grupo = df_tb_fs3[df_tb_fs3['Grupo'] == fatorS3]
    fators3 = float(df_grupo.loc[df_grupo.index, 'S3'].values[0])

    velocidade_VK = format(float(velocidadeV0 * fators1 * fators2 * fators3), '.2f')
    print(velocidade_VK)
    print(fators1,fators2,fators3)

    return velocidade_VK   
    
def calcular_velocidade(latitude, longitude, map_type, config, altura, fators1, anguloteta, dt, categoriaS2, rajadaS2, fatorS3):
    gdf_linha = get_shapefiles(map_type, config)

    user_location = Point(longitude, latitude)

    velocidade_V0 = get_velocity_V0(user_location, gdf_linha)

    velocidade_V0 = float(40)

    velocidade_VK = get_velocity_VK(altura, fators1, anguloteta, dt, categoriaS2, rajadaS2, fatorS3, velocidade_V0)
    
    return velocidade_VK