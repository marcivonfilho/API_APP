import json
import re
from app.llm.openai_client import client


class LocationExtractorService:
    """
    Extrai localização de uma mensagem do usuário.

    Estratégia:
    1. Coordenadas: regex direta (mais confiável e barata)
    2. Cidade/UF: LLM com saída JSON estruturada
    """

    def extract_coordinates(self, text: str):
        """
        Detecta coordenadas em formatos como:
        -15.6014, -56.0979
        lat -15.6014 lon -56.0979
        latitude -15.60 longitude -56.10
        """
        if not text:
            return None

        text = text.strip()

        # formato simples: -15.60, -56.10
        simple_pattern = r'(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)'
        match = re.search(simple_pattern, text)
        if match:
            lat = float(match.group(1))
            lon = float(match.group(2))
            if self._valid_lat_lon(lat, lon):
                return {
                    "has_location": True,
                    "location_type": "coordinates",
                    "city": None,
                    "uf": None,
                    "latitude": lat,
                    "longitude": lon,
                    "confidence": "high",
                }

        # formatos com rótulos
        labeled_pattern = (
            r'(?:lat|latitude)\s*[:=]?\s*(-?\d+(?:\.\d+)?)'
            r'.{0,30}?'
            r'(?:lon|long|longitude)\s*[:=]?\s*(-?\d+(?:\.\d+)?)'
        )
        match = re.search(labeled_pattern, text, re.IGNORECASE)
        if match:
            lat = float(match.group(1))
            lon = float(match.group(2))
            if self._valid_lat_lon(lat, lon):
                return {
                    "has_location": True,
                    "location_type": "coordinates",
                    "city": None,
                    "uf": None,
                    "latitude": lat,
                    "longitude": lon,
                    "confidence": "high",
                }

        return None

    def _valid_lat_lon(self, lat: float, lon: float) -> bool:
        return -90 <= lat <= 90 and -180 <= lon <= 180

    def extract(self, message: str) -> dict:
        """
        Retorna um dict padronizado:
        {
          "has_location": bool,
          "location_type": "city" | "coordinates" | None,
          "city": str | None,
          "uf": str | None,
          "latitude": float | None,
          "longitude": float | None,
          "confidence": "high" | "medium" | "low"
        }
        """
        if not message or not message.strip():
            return self._empty()

        # 1) coordenadas primeiro
        coord_result = self.extract_coordinates(message)
        if coord_result:
            return coord_result

        # 2) extração semântica por LLM
        return self._extract_city_with_llm(message)

    def _extract_city_with_llm(self, message: str) -> dict:
        prompt = f"""
Extraia localização geográfica da mensagem abaixo para uso em engenharia do vento no Brasil.

Objetivo:
Identificar se o usuário informou uma cidade/UF brasileira ou coordenadas.

Regras:
- Responda APENAS em JSON válido.
- Não invente localização.
- Se não houver localização explícita ou implicitamente clara, retorne campos nulos.
- Se houver cidade brasileira sem UF explícita, preencha apenas a cidade e deixe "uf" como null.
- Se houver cidade e UF, preencha ambos.
- Se houver coordenadas, preencha latitude e longitude.
- "location_type" deve ser apenas:
  - "city"
  - "coordinates"
  - null
- "confidence" deve ser apenas:
  - "high"
  - "medium"
  - "low"

Formato JSON obrigatório:
{{
  "has_location": true,
  "location_type": "city",
  "city": "Campo Grande",
  "uf": "MS",
  "latitude": null,
  "longitude": null,
  "confidence": "high"
}}

Se não houver localização:
{{
  "has_location": false,
  "location_type": null,
  "city": null,
  "uf": null,
  "latitude": null,
  "longitude": null,
  "confidence": "low"
}}

Mensagem:
{message}
""".strip()

        try:
            response = client.responses.create(
                model="gpt-4.1-mini",
                input=prompt,
                max_output_tokens=180
            )

            raw = (response.output_text or "").strip()

            # tenta extrair json mesmo se vier cercado de texto
            parsed = self._safe_parse_json(raw)

            return self._normalize_result(parsed)

        except Exception as e:
            print("ERRO LOCATION EXTRACTOR:", e)
            return self._empty()

    def _safe_parse_json(self, raw: str) -> dict:
        try:
            return json.loads(raw)
        except Exception:
            pass

        # fallback: tenta localizar o primeiro objeto json
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(raw[start:end + 1])
            except Exception:
                pass

        return self._empty()

    def _normalize_result(self, data: dict) -> dict:
        if not isinstance(data, dict):
            return self._empty()

        result = {
            "has_location": bool(data.get("has_location", False)),
            "location_type": data.get("location_type"),
            "city": data.get("city"),
            "uf": data.get("uf"),
            "latitude": data.get("latitude"),
            "longitude": data.get("longitude"),
            "confidence": data.get("confidence", "low"),
        }

        if result["location_type"] == "coordinates":
            try:
                lat = float(result["latitude"])
                lon = float(result["longitude"])
                if self._valid_lat_lon(lat, lon):
                    result["latitude"] = lat
                    result["longitude"] = lon
                    result["has_location"] = True
                    return result
            except Exception:
                return self._empty()

        if result["location_type"] == "city":
            city = result["city"]
            uf = result["uf"]

            if isinstance(city, str):
                city = city.strip().title()
            else:
                city = None

            if isinstance(uf, str):
                uf = uf.strip().upper()
                if len(uf) != 2:
                    uf = None
            else:
                uf = None

            if city:
                result["city"] = city
                result["uf"] = uf
                result["latitude"] = None
                result["longitude"] = None
                result["has_location"] = True
                return result

        return self._empty()

    def _empty(self) -> dict:
        return {
            "has_location": False,
            "location_type": None,
            "city": None,
            "uf": None,
            "latitude": None,
            "longitude": None,
            "confidence": "low",
        }