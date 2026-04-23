from flask import Blueprint, request, jsonify, send_file
from numpy import double
from app.core.config import Config
import psycopg2
from app.utils import (autenticateUser, verifyUser, cadasUser, update_password, check_and_process_image, calcular_velocidade, check_and_process_html)
from app.tools.isopleth_v0.service import V0Service

def init_routes(app, config):

    v0_service = V0Service()

    @app.route("/v0")
    def v0():
        lat = float(request.args.get("lat"))
        lon = float(request.args.get("lon"))

        result = v0_service.get_v0(lat, lon)

        if not result["ok"]:
            return jsonify(result), 404

        return jsonify(result)

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
        
    @app.route('/change_password', methods=['POST'])
    def change_password():
        try:
            email = request.form['email']
            current_password = request.form['current_password']
            new_password = request.form['new_password']

            # política mínima (profissional)
            if len(new_password) < 6:
                return jsonify({'message': 'Senha muito curta'}), 400

            # verifica se usuário existe
            if not verifyUser(email, config):
                return jsonify({'message': 'Usuário não encontrado'}), 404

            # confirma senha atual
            if not autenticateUser(email, current_password, config):
                return jsonify({'message': 'Senha atual incorreta'}), 401

            ok = update_password(email, new_password, config)
            if ok:
                return jsonify({'message': 'Senha alterada com sucesso'}), 200

            return jsonify({'message': 'Não foi possível alterar a senha'}), 500

        except Exception as e:
            return jsonify({'message': str(e)}), 500
    
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
    
    @app.route('/html_isopleta', methods=['GET'])
    def img_html_nbr():
        try:
            print('Entrei na rota html')
            map_type = request.args.get('map_type')
            if not map_type:
                return "Parâmetro 'map_type' é necessário", 400
            
            html_path = check_and_process_html(map_type, config)

            print(html_path)
            return send_file(html_path, mimetype='text/html')
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/calc_velocidade', methods=['POST'])
    def calc_velocity():
        try:
            data = request.form

            map_type = data['map_type']
            latitude = float(data['latitude'])
            longitude = float(data['longitude'])
            altura = float(data['altura'])
            fatorS1 = data['fatorS1']
            anguloTeta = float(data['anguloTeta'])
            dt = float(data['dt'])
            categoriaS2 = data['categoriaS2']
            rajadaS2 = data['rajadaS2']
            fatorCaracte = int(data['fatorS3'])

            print(latitude,longitude)
            
            if not map_type:
                return jsonify({"error": "Parâmetro 'map_type' é necessário"}), 400
            elif latitude is None or longitude is None:
                return jsonify({'error': 'latitude and longitude are required'}), 400

            velocity_VK, velocity_VD = double(calcular_velocidade(
                latitude,
                longitude,
                map_type,
                config,
                altura,
                fatorS1,
                anguloTeta,
                dt,
                categoriaS2,
                rajadaS2,
                fatorCaracte))

            return jsonify({
            'velocity': velocity_VK,
            'velocitys': velocity_VD
        }), 200
        except Exception as e:
            print(f"Error: {str(e)}")
            return jsonify({'error': str(e)}), 500
