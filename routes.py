from flask import request, jsonify, send_file
from utils import (autenticateUser, verifyUser, cadasUser, check_and_process_image)

def init_routes(app, config):

    # Rota de login
    @app.route('/login', methods=['POST'])
    def login():
        email = request.form['email']
        senha = request.form['senha']

        try:
            if autenticateUser(email, senha, config):
                return jsonify({'message': 'Login bem-sucedido'}), 200
            else:        
                return jsonify({'message': 'Credenciais inválidas'}), 401  
        except Exception as e:
            return jsonify({'message' : str(e)}), 500
    
    # Rota de Cadastramento do Usuário   
    @app.route('/caduser', methods=['POST'])
    def cadUser():
        nome = request.form['nome']
        sobrenome = request.form['sobrenome']
        email = request.form['email']
        senha = request.form['senha']
        tipoUser = request.form['tipoUser']

        try:
            if verifyUser(email, config):
                return jsonify({'message': 'Usuário já existe'}), 401
            else:
                cadasUser(nome, sobrenome, email, senha, tipoUser, config)
            return jsonify({'message': 'Usuário Cadastrado com Sucesso'}), 200
        except Exception as e:
            return jsonify({'message' : str(e)}), 500
    
    # Rota para buscar a imagem e mostrar para o usuario   
    @app.route('/img_isopleta', methods=['GET'])
    def img_nbr():
        try:
            map_type = request.args.get('map_type')
            if not map_type:
                return "Parâmetro 'map_type' é necessário", 400
            
            image_path = check_and_process_image(map_type, config)
            return send_file(image_path, mimetype='image/png')
        except Exception as e:
            return jsonify({'error': str(e)}), 500