import json

from ..routes import AI_EXTENSIONS

async def test_pip_packages_list(jp_fetch):
    # When
    response = await jp_fetch("jupyter-ai-manager", "extensions")

    # Then
    assert response.code == 200
    payload = json.loads(response.body)
    default = sorted([ext["pip_package"] for ext in AI_EXTENSIONS])
    fetched = sorted([ext["pip_package"] for ext in payload["extensions"]])

    assert default == fetched
