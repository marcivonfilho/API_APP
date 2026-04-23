import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from app.tools.isopleth_v0.service import V0Service
from app.tools.location_extractor.service import LocationExtractorService


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    return ascii_text.lower()


@dataclass
class V0LookupResult:
    handled: bool = False
    markdown: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    fontes: list[dict[str, str]] = field(default_factory=list)


class V0LookupService:
    def __init__(
        self,
        location_extractor: LocationExtractorService | None = None,
        v0_service: V0Service | None = None,
    ) -> None:
        self.location_extractor = location_extractor or LocationExtractorService()
        self.v0_service = v0_service or V0Service()

    def should_handle(self, question: str) -> bool:
        text = _normalize_text(question)
        asks_v0 = (
            "velocidade basica" in text
            or "v0" in text
            or "v_0" in text
        )
        if not asks_v0:
            return False

        has_coordinate_hint = bool(
            re.search(r"-?\d+(?:[\.,]\d+)?\s*,\s*-?\d+(?:[\.,]\d+)?", text)
            or ("lat" in text and ("lon" in text or "long" in text))
        )
        has_place_hint = bool(
            re.search(r"\b(em|para|na|no|cidade|municipio|munic[ií]pio)\b", text)
        )
        conceptual_hint = bool(
            "segundo a norma" in text
            or "o que e" in text
            or "defina" in text
            or "conceito" in text
        )
        return has_coordinate_hint or (has_place_hint and not conceptual_hint)

    def lookup(self, question: str) -> V0LookupResult:
        if not self.should_handle(question):
            return V0LookupResult(handled=False)

        location = self.location_extractor.extract(question)
        if not location.get("has_location"):
            return V0LookupResult(
                handled=True,
                markdown=(
                    "Para consultar a velocidade básica do vento, preciso que você informe "
                    "a cidade/UF ou as coordenadas do ponto. Exemplo: `Cuiabá/MT` ou "
                    "`lat -15.6014 lon -56.0979`."
                ),
                data={"location": location},
            )

        try:
            if location.get("location_type") == "coordinates":
                result = self.v0_service.get_v0_by_coordinates(
                    float(location["latitude"]),
                    float(location["longitude"]),
                )
            elif location.get("location_type") == "city":
                result = self.v0_service.get_v0_by_city(
                    str(location["city"]),
                    location.get("uf"),
                )
            else:
                return V0LookupResult(handled=False)
        except Exception as exc:
            return V0LookupResult(
                handled=True,
                markdown=(
                    "Não consegui consultar o mapa de isopletas agora. A extração da "
                    "localização funcionou, mas a consulta ao banco/PostGIS retornou erro.\n\n"
                    f"**Detalhe técnico:** {exc}"
                ),
                data={"location": location, "error": str(exc)},
            )

        return self._format_result(location, result)

    def _format_result(self, location: dict[str, Any], result: dict[str, Any]) -> V0LookupResult:
        fontes = [{
            "fonte": "Mapa de isopletas da NBR 6123",
            "pagina": "",
            "secao": "5.1",
            "tipo_conteudo": "figura",
            "colecao": "ferramenta_v0",
        }]

        if result.get("ambiguous_city"):
            options = result.get("options") or []
            option_lines = "\n".join(
                f"- {item.get('cidade')}/{item.get('uf')}"
                for item in options
            )
            return V0LookupResult(
                handled=True,
                markdown=(
                    "Encontrei mais de um município com esse nome. Para consultar o "
                    "$V_0$ com segurança, informe também a UF.\n\n"
                    f"{option_lines}"
                ),
                data={"location": location, "result": result},
                fontes=fontes,
            )

        if not result.get("ok"):
            return V0LookupResult(
                handled=True,
                markdown=(
                    "Não encontrei uma região de isopleta para a localização informada.\n\n"
                    f"**Detalhe:** {result.get('error', 'consulta sem resultado')}"
                ),
                data={"location": location, "result": result},
                fontes=fontes,
            )

        if result.get("zona_especial"):
            place = self._place_label(result, location)
            return V0LookupResult(
                handled=True,
                markdown=(
                    f"Para **{place}**, o ponto cai em uma região especial do mapa de "
                    "isopletas da NBR 6123, sem valor direto de $V_0$ definido na base.\n\n"
                    "Nesse caso, a consulta deve ser tratada com atenção técnica e pode "
                    "exigir avaliação específica do mapa/critério normativo."
                ),
                data={"location": location, "result": result},
                fontes=fontes,
            )

        v0 = result.get("v0")
        place = self._place_label(result, location)
        coordinates = self._coordinate_line(result)
        markdown = (
            f"Para **{place}**, a velocidade básica do vento obtida no mapa de "
            f"isopletas da NBR 6123 é:\n\n"
            f"$$V_0 = {float(v0):.0f}\\,m/s$$\n\n"
            "Esse valor é a velocidade básica usada como entrada para o cálculo da "
            "velocidade característica do vento, junto com os fatores $S_1$, $S_2$ e $S_3$.\n"
            f"{coordinates}\n\n"
            "**Fonte:** mapa de isopletas da NBR 6123."
        )
        return V0LookupResult(
            handled=True,
            markdown=markdown,
            data={"location": location, "result": result},
            fontes=fontes,
        )

    def _place_label(self, result: dict[str, Any], location: dict[str, Any]) -> str:
        if result.get("cidade"):
            return f"{result.get('cidade')}/{result.get('uf')}"
        if location.get("city"):
            uf = f"/{location.get('uf')}" if location.get("uf") else ""
            return f"{location.get('city')}{uf}"
        lat = result.get("latitude") or location.get("latitude")
        lon = result.get("longitude") or location.get("longitude")
        return f"lat {lat}, lon {lon}"

    def _coordinate_line(self, result: dict[str, Any]) -> str:
        lat = result.get("latitude_centroide") or result.get("latitude")
        lon = result.get("longitude_centroide") or result.get("longitude")
        if lat is None or lon is None:
            return ""
        return f"\nCoordenada de referência da consulta: lat {float(lat):.5f}, lon {float(lon):.5f}."
