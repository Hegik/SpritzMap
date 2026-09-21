#!/usr/bin/env python3
"""
Richtet den gemeinsamen Gebietslayer spritzmap:area_summary per GeoServer-REST-API ein (idempotent).

Einmalig ausführen – danach ist für neue Städte in GeoServer nichts mehr zu tun.
Nur Python-Standardbibliothek, läuft also überall mit python3.

Umgebungsvariablen:
  GEOSERVER_URL       z. B. https://geoserver.hegik.de/geoserver
  GEOSERVER_USER      Admin-Benutzer
  GEOSERVER_PASSWORD  Admin-Passwort
  DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD   Zugang, mit dem GeoServer die SpritzMap-DB liest
  STORE_NAME          optional, Standard "spritzmap_db" (bestehender Store wird wiederverwendet)
"""
import base64
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

HERE = Path(__file__).parent
WORKSPACE = "spritzmap"
LAYER = "area_summary"
STYLE = "spritz_index_style"
# Deutschland (grob) – nur Metadaten, die Stadt wird per viewparams gefiltert
BBOX = (5.8, 47.2, 15.1, 55.1)

env = os.environ.get
BASE = env("GEOSERVER_URL", "http://localhost:8080/geoserver").rstrip("/") + "/rest"
AUTH = "Basic " + base64.b64encode(f"{env('GEOSERVER_USER', 'admin')}:{env('GEOSERVER_PASSWORD', 'geoserver')}".encode()).decode()
STORE = env("STORE_NAME", "spritzmap_db")


def call(method: str, path: str, body: str | None = None, content_type: str = "application/xml") -> int:
    req = urllib.request.Request(BASE + path, method=method, data=body.encode() if body else None)
    req.add_header("Authorization", AUTH)
    if body:
        req.add_header("Content-Type", content_type)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status
    except urllib.error.HTTPError as e:
        if method == "GET" and e.code == 404:
            return 404
        sys.exit(f"{method} {path} → {e.code}: {e.read().decode(errors='replace')[:500]}")


def exists(path: str) -> bool:
    # Explizit JSON anfordern: ohne Formatangabe antwortet GeoServer bei Stilen mit 500
    return call("GET", path + ".json") == 200


def main() -> None:
    if not exists(f"/workspaces/{WORKSPACE}"):
        call("POST", "/workspaces", f"<workspace><name>{WORKSPACE}</name></workspace>")
        print(f"Workspace {WORKSPACE} angelegt")

    if not exists(f"/workspaces/{WORKSPACE}/datastores/{STORE}"):
        entries = {
            "dbtype": "postgis", "host": env("DB_HOST", "db"), "port": env("DB_PORT", "5432"),
            "database": env("DB_NAME", "spritzmap"), "user": env("DB_USER", "spritzmap"),
            "passwd": env("DB_PASSWORD", "spritzmap"), "schema": "public", "Expose primary keys": "true",
        }
        params = "".join(f'<entry key="{escape(k)}">{escape(v)}</entry>' for k, v in entries.items())
        call("POST", f"/workspaces/{WORKSPACE}/datastores",
             f"<dataStore><name>{STORE}</name><connectionParameters>{params}</connectionParameters></dataStore>")
        print(f"Datastore {STORE} angelegt")

    sql = (HERE / "area_summary.sql").read_text(encoding="utf-8")
    params = "".join(
        f"<parameter><name>{p}</name><defaultValue>1</defaultValue><regexpValidator>^[\\d]+$</regexpValidator></parameter>"
        for p in ("city_id", "drink_id")
    )
    minx, miny, maxx, maxy = BBOX
    bbox = f"<minx>{minx}</minx><maxx>{maxx}</maxx><miny>{miny}</miny><maxy>{maxy}</maxy><crs>EPSG:4326</crs>"
    feature_type = f"""<featureType>
  <name>{LAYER}</name><nativeName>{LAYER}</nativeName>
  <title>Spritz-Index je Gebiet</title>
  <srs>EPSG:4326</srs><projectionPolicy>FORCE_DECLARED</projectionPolicy>
  <nativeBoundingBox>{bbox}</nativeBoundingBox><latLonBoundingBox>{bbox}</latLonBoundingBox>
  <metadata><entry key="JDBC_VIRTUAL_TABLE"><virtualTable>
    <name>{LAYER}</name><sql>{escape(sql)}</sql><escapeSql>false</escapeSql>
    <keyColumn>area_id</keyColumn>
    <geometry><name>geom</name><type>MultiPolygon</type><srid>4326</srid></geometry>
    {params}
  </virtualTable></entry></metadata>
</featureType>"""
    ft_path = f"/workspaces/{WORKSPACE}/datastores/{STORE}/featuretypes"
    if exists(f"{ft_path}/{LAYER}"):
        call("PUT", f"{ft_path}/{LAYER}", feature_type)  # SQL aktualisieren
        print(f"Layer {WORKSPACE}:{LAYER} aktualisiert")
    else:
        call("POST", ft_path, feature_type)
        print(f"Layer {WORKSPACE}:{LAYER} angelegt")

    sld = (HERE / "lor_spritz_index.sld").read_text(encoding="utf-8")
    if exists(f"/workspaces/{WORKSPACE}/styles/{STYLE}"):
        call("PUT", f"/workspaces/{WORKSPACE}/styles/{STYLE}", sld, "application/vnd.ogc.sld+xml")
    else:
        call("POST", f"/workspaces/{WORKSPACE}/styles?name={STYLE}", sld, "application/vnd.ogc.sld+xml")
    call("PUT", f"/layers/{WORKSPACE}:{LAYER}",
         f"<layer><defaultStyle><name>{STYLE}</name><workspace>{WORKSPACE}</workspace></defaultStyle></layer>")
    print(f"Stil {STYLE} zugewiesen – fertig.")


if __name__ == "__main__":
    main()
