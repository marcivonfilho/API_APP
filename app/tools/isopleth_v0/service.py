import psycopg2
from app.core.config import Config


class V0Service:

    # ===============================
    # CONFIGURAÇÕES
    # ===============================
    TABLE = "public.norma_nbr_velocidade"
    GEOM_COL = "geom"
    VALUE_COL = "velocidade"

    CITY_TABLE = "public.br_municipios_2022"
    CITY_GEOM_COL = "geom"
    CITY_NAME_COL = "nm_mun"
    CITY_UF_COL = "sigla_uf"

    CITY_FALLBACK_SRID = 4674

    # ===============================
    # CONEXÃO
    # ===============================
    def _get_conn(self):
        return psycopg2.connect(Config.POSTGRES_DSN)

    # ===============================
    # GEOMETRIA EM 4326
    # ===============================
    def _geom_4326_expr(self, col, fallback_srid=None):
        """
        Garante que a geometria esteja em 4326
        """
        if fallback_srid:
            return f"""
            CASE
                WHEN ST_SRID({col}) = 0
                    THEN ST_Transform(ST_SetSRID({col}, {fallback_srid}), 4326)
                WHEN ST_SRID({col}) != 4326
                    THEN ST_Transform({col}, 4326)
                ELSE {col}
            END
            """
        else:
            return f"""
            CASE
                WHEN ST_SRID({col}) != 4326
                    THEN ST_Transform({col}, 4326)
                ELSE {col}
            END
            """

    # ===============================
    # CONSULTA POR COORDENADAS
    # ===============================
    def get_v0_by_coordinates(self, lat: float, lon: float):

        with self._get_conn() as conn:
            with conn.cursor() as cur:

                geom_expr = self._geom_4326_expr(self.GEOM_COL)

                sql = f"""
                SELECT {self.VALUE_COL}
                FROM {self.TABLE}
                WHERE ST_Intersects(
                    {geom_expr},
                    ST_SetSRID(ST_MakePoint(%s, %s), 4326)
                )
                LIMIT 1;
                """

                cur.execute(sql, (lon, lat))
                row = cur.fetchone()

                if not row:
                    return {
                        "ok": False,
                        "error": "Nenhuma região encontrada para o ponto informado"
                    }

                v0 = float(row[0])

                # 🔴 zona hachurada
                if v0 == 0:
                    return {
                        "ok": True,
                        "zona_especial": True,
                        "tipo": "zona_hachurada",
                        "mensagem": "Região sem valor definido de V0 na NBR 6123",
                        "latitude": lat,
                        "longitude": lon,
                        "fonte": "Mapa de isopletas da NBR 6123"
                    }

                return {
                    "ok": True,
                    "tipo_entrada": "coordenada",
                    "latitude": lat,
                    "longitude": lon,
                    "v0": v0,
                    "fonte": "Mapa de isopletas da NBR 6123"
                }

    # ===============================
    # CONSULTA POR CIDADE
    # ===============================
    def get_v0_by_city(self, city: str, uf: str = None):

        with self._get_conn() as conn:
            with conn.cursor() as cur:

                city_geom_expr = self._geom_4326_expr(
                    self.CITY_GEOM_COL,
                    fallback_srid=self.CITY_FALLBACK_SRID
                )

                # ===============================
                # CASO COM UF
                # ===============================
                if uf:
                    sql_city = f"""
                    SELECT
                        {self.CITY_NAME_COL},
                        {self.CITY_UF_COL},
                        ST_Y(ST_Centroid({city_geom_expr})) AS lat,
                        ST_X(ST_Centroid({city_geom_expr})) AS lon
                    FROM {self.CITY_TABLE}
                    WHERE LOWER({self.CITY_NAME_COL}) = LOWER(%s)
                    AND UPPER({self.CITY_UF_COL}) = UPPER(%s)
                    LIMIT 1;
                    """
                    cur.execute(sql_city, (city, uf))
                    city_row = cur.fetchone()

                    if not city_row:
                        return {
                            "ok": False,
                            "error": f"Município '{city}/{uf}' não encontrado"
                        }

                    city_name, city_uf, lat, lon = city_row

                # ===============================
                # CASO SEM UF
                # ===============================
                else:
                    sql_matches = f"""
                    SELECT
                        {self.CITY_NAME_COL},
                        {self.CITY_UF_COL},
                        ST_Y(ST_Centroid({city_geom_expr})) AS lat,
                        ST_X(ST_Centroid({city_geom_expr})) AS lon
                    FROM {self.CITY_TABLE}
                    WHERE LOWER({self.CITY_NAME_COL}) = LOWER(%s)
                    ORDER BY {self.CITY_UF_COL};
                    """
                    cur.execute(sql_matches, (city,))
                    rows = cur.fetchall()

                    if not rows:
                        return {
                            "ok": False,
                            "error": f"Município '{city}' não encontrado"
                        }

                    # se houver mais de uma cidade com o mesmo nome, não escolhe arbitrariamente
                    ufs = sorted(list({r[1] for r in rows if r[1]}))

                    if len(rows) > 1 and len(ufs) > 1:
                        return {
                            "ok": True,
                            "ambiguous_city": True,
                            "city": city.title(),
                            "options": [
                                {"cidade": r[0], "uf": r[1]}
                                for r in rows
                            ]
                        }

                    city_name, city_uf, lat, lon = rows[0]

                # ===============================
                # CONSULTA V0 PELO CENTRÓIDE
                # ===============================
                result = self.get_v0_by_coordinates(lat, lon)

                if not result["ok"]:
                    return result

                if result.get("zona_especial"):
                    return {
                        "ok": True,
                        "zona_especial": True,
                        "tipo_entrada": "cidade",
                        "cidade": city_name,
                        "uf": city_uf,
                        "mensagem": result["mensagem"],
                        "fonte": result["fonte"]
                    }

                return {
                    "ok": True,
                    "tipo_entrada": "cidade",
                    "cidade": city_name,
                    "uf": city_uf,
                    "latitude_centroide": lat,
                    "longitude_centroide": lon,
                    "v0": result["v0"],
                    "fonte": result["fonte"]
                }

    # ===============================
    # COMPATIBILIDADE
    # ===============================
    def get_v0(self, lat: float, lon: float):
        return self.get_v0_by_coordinates(lat, lon)