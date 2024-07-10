from flask import request, jsonify, send_file
from numpy import double
import os
from utils import (autenticateUser, verifyUser, cadasUser, check_and_process_image, calcular_velocidade, check_and_process_html)

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
        
    '''
    @app.route('/map_location', methods=['POST'])
    def user_local():
        try:
            data = request.form
            #print('Received data:', data)

            latitude = float(data['latitude'])
            longitude = float(data['longitude'])
        
            map_type = request.form.get('map_type')

            if not map_type:
                return jsonify({"error": "Parâmetro 'map_type' é necessário"}), 400
            elif latitude is None or longitude is None:
                return jsonify({'error': 'latitude and longitude are required'}), 400
            
            # Processamento de localização e cálculo de proximidade da isopleta
            image_path, nearest_velocity= criar_ponto_dist_isopleta(latitude, longitude, map_type, config)

            return jsonify({
            'image_url': image_path,
            'nearest_velocity': nearest_velocity
        }), 200
        except Exception as e:
            print(f"Error: {str(e)}")
            return jsonify({'error': str(e)}), 500
    '''

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

            velocity_VK = double(calcular_velocidade(
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
            'velocity': velocity_VK
        }), 200
        except Exception as e:
            print(f"Error: {str(e)}")
            return jsonify({'error': str(e)}), 500
