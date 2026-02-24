docker_compose('./docker-compose.yml')

# Mock Etsy API resource
dc_resource(
    'mock-etsy-api',
    labels=['api']
)

# Discord Bot resource
dc_resource(
    'bot',
    labels=['discord-bot'],
    resource_deps=['mock-etsy-api']
)

# Live reload for mock API when files change
watch_file('src/etsy/mock_api.py')
watch_file('src/etsy/client.py')