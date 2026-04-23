import requests


url = "http://127.0.0.1:5000/api/chat"

payload = {
    "message": "Qual coeficiente devo usar para pressão interna?",
    "debug": True,
}

print(f"Enviando pergunta: {payload['message']}\n")

try:
    response = requests.post(url, json=payload, timeout=90)
    response.raise_for_status()

    dados = response.json()
    print("RESPOSTA DA IA:\n")
    print(dados.get("resposta", "Sem resposta."))
    print(f"\nFONTES CONSULTADAS: {dados.get('fontes')}")
    print(f"MODO: {dados.get('modo')}")
    uso = dados.get("uso") or {}
    if uso:
        print("\nUSO DE TOKENS:")
        print(f"- input_tokens: {uso.get('input_tokens')}")
        print(f"- output_tokens: {uso.get('output_tokens')}")
        print(f"- total_tokens: {uso.get('total_tokens')}")
        input_details = uso.get("input_tokens_details") or {}
        output_details = uso.get("output_tokens_details") or {}
        print(f"- cached_tokens: {input_details.get('cached_tokens')}")
        print(f"- reasoning_tokens: {output_details.get('reasoning_tokens')}")
    print(f"TEMPO: {dados.get('tempo_ms')} ms")

except requests.exceptions.RequestException as e:
    print(f"Erro de conexao ou na API: {e}")
