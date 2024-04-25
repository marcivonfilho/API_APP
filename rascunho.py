'''
@app.route('/testlogin')
def test():
   email = 'marcivon71@gmail.com'
   senha = 'MaR1206'
   if autenticateUser(email, senha):
      return jsonify({'message': 'Usuário existe e a senha está correta.'})
   else:
      return jsonify({'message': 'Usuário não encontrado ou senha incorreta.'})
'''

'''
@app.route('/testdb')
def test_db_connection():
    conn = pool_connect()
    if conn is not None:
        close_connect(conn)
        return jsonify({'message': 'Conexão com o banco de dados bem-sucedida'})
    else:
        return jsonify({'message': 'Erro ao conectar ao banco de dados'}), 500
'''