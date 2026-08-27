from datetime import timezone

from bs4 import BeautifulSoup

from rss_generator.scraper import _from_html, _from_json_ld, canonical_url, parse_date


def test_extracts_json_ld_article():
    html = '''<script type="application/ld+json">{
      "@type":"NewsArticle", "headline":"Nueva noticia", "url":"/noticias/nueva",
      "description":"Descripción", "datePublished":"2026-08-25T10:30:00+02:00",
      "image":{"url":"/media/foto.jpg"}
    }</script>'''
    item = _from_json_ld(BeautifulSoup(html, "html.parser"), "https://www.colladovillalba.es/noticias")[0]
    assert item.title == "Nueva noticia"
    assert item.url == "https://www.colladovillalba.es/noticias/nueva"
    assert item.image == "https://www.colladovillalba.es/media/foto.jpg"
    assert item.published.hour == 8


def test_extracts_common_drupal_listing_markup():
    html = '''<div class="views-row"><article><h2><a href="/noticias/plan-municipal">Plan municipal</a></h2>
      <time datetime="2026-08-25T09:00:00Z">25 agosto</time>
      <p>Información del plan.</p><img data-src="/files/plan.jpg"></article></div>'''
    items = _from_html(BeautifulSoup(html, "html.parser"), "https://www.colladovillalba.es/noticias")
    assert items[0].description == "Información del plan."
    assert items[0].image.endswith("/files/plan.jpg")


def test_extracts_liferay_card_markup():
    html = '''<div class="card">
      <a class="card-title-image" href="https://www.colladovillalba.es/-/noticia?redirect=%2Fnoticias">
        <img src="/media/noticia.jpg">
      </a>
      <span class="date publish-date">27 de agosto de 26</span>
      <p><a class="card-title" href="https://www.colladovillalba.es/-/noticia?redirect=%2Fnoticias">Noticia municipal</a></p>
      <p class="card-text">Resumen de la noticia.</p>
    </div>'''
    item = _from_html(BeautifulSoup(html, "html.parser"), "https://www.colladovillalba.es/noticias")[0]
    assert item.title == "Noticia municipal"
    assert item.url == "https://www.colladovillalba.es/-/noticia"
    assert item.description == "Resumen de la noticia."
    assert item.published.isoformat() == "2026-08-27T00:00:00+00:00"
    assert item.image == "https://www.colladovillalba.es/media/noticia.jpg"


def test_normalizes_url_and_dates():
    assert canonical_url("/noticias/uno/?utm_source=x#top", "https://WWW.ColladoVillalba.es") == "https://www.colladovillalba.es/noticias/uno"
    assert parse_date("Tue, 25 Aug 2026 10:00:00 GMT").tzinfo == timezone.utc
    assert parse_date("una fecha desconocida") is None
