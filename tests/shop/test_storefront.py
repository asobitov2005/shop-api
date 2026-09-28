def test_shop_home_shows_product_catalog_and_checkout(client):
    response = client.get("/")

    assert response.status_code == 200
    assert "Yaqin" in response.text
    assert 'id="product-grid"' in response.text
    assert 'id="checkout-button"' in response.text


def test_shop_javascript_asset_is_served(client):
    response = client.get("/static/shop.js")

    assert response.status_code == 200
    assert "POST" in response.text
    assert "payment_url" in response.text
