#Utilizou-se Flask, psycopg2
#conda info --envs      conda activate flaskenv
#conda install -c conda-forge flask
#conda install -c conda-forge psycopg2-binary
#conda install -c conda-forge bcrypt
#conda install -c conda-forge pandas
#conda install -c conda-forge geopandas matplotlib

from flask import Flask
from config import Config
from routes import init_routes

app = Flask(__name__, static_url_path='/images_processed', static_folder=r'C:\Users\marci\Documents\images_processed')
app.config.from_object(Config)

init_routes(app, app.config)

#Essa linha de código inicializa o server HTTP
if __name__ == "__main__":
   app.run(host='0.0.0.0', port=5000, threaded=True)