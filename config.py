class Config:
    DEBUG = True
    JSON_AS_ASCII = False
    JSONIFY_PRETTYPRINT_REGULAR = False
    POSTGRES_HOST = 'localhost'
    POSTGRES_PORT = '5432'
    POSTGRES_DB = 'app_ventos'
    POSTGRES_USER = 'postgres'
    POSTGRES_PASSWORD = 'appventos'
    SQLALCHEMY_DATABASE_URI = 'postgresql://postgres:appventos@localhost/app_ventos'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    PROCESSED_IMAGES_DIR = r'C:\Users\marci\Documents\images_processed'