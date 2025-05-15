import asyncio
from plugins.ddg_image_search import DDGImageSearchPlugin
import json

class DummyHelper:
    pass  # Заменяет OpenAIHelper, он здесь не нужен

async def test():
    plugin = DDGImageSearchPlugin()
    result = await plugin.execute(
        function_name="search_images",
        helper=DummyHelper(),
        query="кот в очках",
        type="photo",
        region="wt-wt"
    )
    print(json.dumps(result, indent=2))

asyncio.run(test())
# Примечание: Этот тестовый код предназначен для проверки работы плагина DDGImageSearchPlugin.
# Он не является частью основного кода и может быть удален или изменен в зависимости от ваших нужд.
# Убедитесь, что у вас установлен asyncio и другие необходимые библиотеки.
# Также убедитесь, что у вас есть доступ к интернету, так как плагин выполняет запросы к DuckDuckGo.
# Убедитесь, что вы используете правильную версию Python (3.7 или выше), так как asyncio требует этой версии.
# Если вы хотите протестировать код, убедитесь, что у вас есть все необходимые зависимости и что вы находитесь в правильной среде выполнения.
