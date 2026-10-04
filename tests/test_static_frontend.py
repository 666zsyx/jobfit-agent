# 验证同源静态前端页面和资源可访问。


def test_root_redirects_to_workbench(client):
    response = client.get("/", follow_redirects=False)

    assert response.status_code in {302, 307}
    assert response.headers["location"] == "/app"


def test_workbench_page_is_served(client):
    response = client.get("/app")

    assert response.status_code == 200
    assert "JobFit Agent 工作台" in response.text
    assert "/static/app.js" in response.text
    assert "/static/styles.css" in response.text
    assert 'id="username-input"' in response.text
    assert 'id="password-input"' in response.text
    assert 'id="login-button"' in response.text
    assert 'id="token-input"' not in response.text


def test_static_javascript_is_served(client):
    response = client.get("/static/app.js")

    assert response.status_code == 200
    assert "graph/stream" in response.text
    assert "human_confirmation" in response.text
    assert "getReader" in response.text
    assert "/api/auth/login" in response.text
    assert "restoreSession" in response.text


def test_static_stylesheet_is_served(client):
    response = client.get("/static/styles.css")

    assert response.status_code == 200
    assert ".layout" in response.text
    assert ".event-log" in response.text
