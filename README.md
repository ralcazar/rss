# Feeds RSS de páginas municipales

Este proyecto convierte páginas que no ofrecen un RSS cómodo de usar en feeds RSS 2.0
independientes. Los archivos se regeneran cada cuatro horas y se publican gratuitamente
con GitHub Pages.

## Feed disponible

| Fuente | Archivo |
| --- | --- |
| [Noticias de Collado Villalba](https://www.colladovillalba.es/noticias) | `feeds/collado-villalba.xml` |

Cuando el repositorio esté en GitHub, la dirección que se debe añadir a Feedly será:

```text
https://USUARIO.github.io/REPOSITORIO/feeds/collado-villalba.xml
```

Sustituye `USUARIO` y `REPOSITORIO` por el propietario y el nombre del repositorio. El
workflow calcula esa dirección automáticamente, por lo que no hay que editar el código.

## Activación en GitHub

1. Sube el repositorio a GitHub y fusiona los cambios en la rama `main`.
2. Abre **Settings → Pages**.
3. En **Build and deployment → Source**, selecciona **GitHub Actions**.
4. Abre **Actions → Actualizar feeds RSS** y pulsa **Run workflow** para crear el primer
   feed sin esperar a la siguiente ejecución programada.
5. Copia la URL indicada arriba en Feedly.

El cron se ejecuta a los 17 minutos de las horas `00`, `04`, `08`, `12`, `16` y `20`
UTC. GitHub puede retrasar ligeramente los trabajos programados. También se despliega al
actualizar `main` y se puede ejecutar manualmente en cualquier momento.

## Ejecución local

Requiere Python 3.11 o posterior:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
python -m rss_generator --base-url https://USUARIO.github.io/REPOSITORIO
python scripts/validate_feeds.py site/feeds
python -m pytest -q
```

Los feeds quedan en `site/feeds`. El generador conserva y combina las entradas de un feed
anterior, elimina duplicados mediante su URL canónica y mantiene como máximo 50 noticias.
En GitHub Actions se intenta descargar primero la versión ya publicada para conservar
noticias que hayan desaparecido de la portada.

## Añadir otra página

Añade un objeto a `sources.json`; cada identificador produce un XML separado:

```json
{
  "id": "nombre-estable",
  "title": "Título que verá Feedly",
  "description": "Descripción de la fuente",
  "url": "https://example.org/noticias",
  "language": "es-ES"
}
```

El extractor reconoce primero datos estructurados Schema.org (`NewsArticle`, `Article` y
`BlogPosting`) y después estructuras HTML habituales. Puesto que cada web puede tener una
maquetación distinta, al incorporar una fuente nueva se debe añadir un caso específico si
ninguno de esos formatos está presente, junto con su correspondiente prueba.

## Formato y tolerancia a errores

Cada feed incluye URL propia mediante Atom, idioma, fecha de construcción, TTL, GUID
permanentes, fechas RFC 822, contenido enriquecido y metadata Media RSS para imágenes. Es
RSS 2.0 en UTF-8 y puede ser consumido por Feedly.

Si una descarga falla temporalmente y existe una versión anterior, se vuelve a publicar
esa versión. Si nunca se ha podido obtener ninguna noticia, el trabajo falla en lugar de
desplegar un feed vacío, haciendo visible el problema en GitHub Actions.
