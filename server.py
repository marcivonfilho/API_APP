#Utilizou-se Flask, psycopg2
#conda info --envs      conda activate flaskenv
#conda install -c conda-forge flask
#conda install -c conda-forge psycopg2-binary
#conda install -c conda-forge bcrypt
#conda install -c conda-forge pandas
#conda install -c conda-forge geopandas matplotlib
#conda install -c conda-forge  firebase-admin

import os
from dotenv import load_dotenv
load_dotenv()
from app.api.chat_routes import chat_bp

import firebase_admin
from firebase_admin import credentials

from flask import Flask
from flask_cors import CORS
from app.core.config import Config
from app.api.routes import init_routes


app = Flask(
    __name__,
    static_url_path="/images_processed",
    static_folder=r"C:\Users\marci\Documents\images_processed",
)

app.config.from_object(Config)

CORS(app)

app.register_blueprint(chat_bp)

#cred = credentials.Certificate(r"C:\caminho\serviceAccountKey.json")
#firebase_admin.initialize_app(cred)

init_routes(app, app.config)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, threaded=True)
