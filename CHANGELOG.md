# Changelog

## 1.0.0 (2026-03-11)


### Features

* add !orders command to display mock Etsy orders on demand ([10a0153](https://github.com/madisonewebb/shopkeep/commit/10a0153caf6794a698cb59d2b379327bdd0c0a26))
* add !shop command and COMMANDS.md ([2d828bf](https://github.com/madisonewebb/shopkeep/commit/2d828bf7300f873d6d26fc29acaf1cb2dcb657c8))
* Add mock API to Tiltfile and docker compose ([a581ddf](https://github.com/madisonewebb/shopkeep/commit/a581ddf335723039a5b2e435ab3d981c1966191f))
* add nginx ingress manifest for shopkeepbot.com ([5c967b9](https://github.com/madisonewebb/shopkeep/commit/5c967b93f3eafebb9198ece050a43200afd02a9e))
* add ORDER_CHANNEL_ID secret ([c6d0221](https://github.com/madisonewebb/shopkeep/commit/c6d0221cd1e0fbf36214c73070e81f193516f46c))
* add pre-commit (with taskfile) ([7ec3bb6](https://github.com/madisonewebb/shopkeep/commit/7ec3bb6e612a765acd6c8889414da547c49b7187))
* add SQLite persistence and order polling ([ce206ca](https://github.com/madisonewebb/shopkeep/commit/ce206ca485d64aa31e0f9ac9f26b3f7148266b64))
* add SQLite persistence and order polling ([1355910](https://github.com/madisonewebb/shopkeep/commit/1355910ae124dd2ec33495abfd0c20f7df947df6))
* add starter discord bot ([6fd384d](https://github.com/madisonewebb/shopkeep/commit/6fd384d2f57f7c656c54ec1d2a58d55e6fc0cbb6))
* bootstrap shop, listings, and receipts on first connect ([2a6c22c](https://github.com/madisonewebb/shopkeep/commit/2a6c22c8cb5f84926c0ef65c7b5fe98df674352f))
* bootstrap shop, listings, and receipts on first connect ([d6b2ac8](https://github.com/madisonewebb/shopkeep/commit/d6b2ac8d37b9b61dec20d195259be586eac499dc))
* create Dockerfile to containerize Discort bot ([2527a56](https://github.com/madisonewebb/shopkeep/commit/2527a563424167f3692314ab53e9c4fa4e191a81))
* filter !orders to last 30 days and non-completed, redesign order embed ([25eb869](https://github.com/madisonewebb/shopkeep/commit/25eb869f455afe9e3dd0a5cff151308015d702b1))
* implement docker-compose for container orchestration ([cffd94e](https://github.com/madisonewebb/shopkeep/commit/cffd94e62bf591525208a9ce35981a37b6522928))
* implement k8s manifests ([f99330c](https://github.com/madisonewebb/shopkeep/commit/f99330c70274ab6518b0f2352d32deecd58c6c6f))
* implement k8s manifests ([b5479c9](https://github.com/madisonewebb/shopkeep/commit/b5479c9da934818e03885a402433d5ed9bcb3945))
* implement mock Etsy API ([8b6165c](https://github.com/madisonewebb/shopkeep/commit/8b6165c5a6fe1b748101b3ea072b87fd783adc88))
* implement Tilt for local development ([37732e4](https://github.com/madisonewebb/shopkeep/commit/37732e458435052743f9f3b8159f84e4f4ee25e5))
* init ci workflow and update README ([82b4b3c](https://github.com/madisonewebb/shopkeep/commit/82b4b3c692ae04d717c5e0a126548941f39322b7))
* init dependabot ([fc278c0](https://github.com/madisonewebb/shopkeep/commit/fc278c03bb6f20a878bdef985ece6c36803f48b3))
* manage Discord token via GitHub Actions secret ([7393c89](https://github.com/madisonewebb/shopkeep/commit/7393c8953efc2b6d2df3e740ec5f813c78a8a2af))
* manage Discord token via GitHub Actions secret ([0744fcd](https://github.com/madisonewebb/shopkeep/commit/0744fcd4b2943a756c963e2167d7edd5e87dbd94))
* migrate commands to slash commands, add /help ([01f751a](https://github.com/madisonewebb/shopkeep/commit/01f751ac7ac7ff45e0373df3a2c22d1a7abde3f1))
* migrate from mock Etsy API to real Etsy API v3 ([99a3d94](https://github.com/madisonewebb/shopkeep/commit/99a3d946355b33d2d85a2bb84f9c9fc3b349f4a4))
* multi-tenant support with website onboarding ([9bfa4f9](https://github.com/madisonewebb/shopkeep/commit/9bfa4f981d95c8b1affc44d5c08d8ce21a5b8ed7))
* paginated /orders view with prev/next buttons ([2778322](https://github.com/madisonewebb/shopkeep/commit/27783222e6ae1a927b60cb69a4a1cc25b055fcbf))
* paginated /orders view with prev/next buttons ([a762f9f](https://github.com/madisonewebb/shopkeep/commit/a762f9f558ffbf382262c08fef7935ef53d7f06a))
* pre-merge improvements for multi-tenant branch ([82538e1](https://github.com/madisonewebb/shopkeep/commit/82538e1ed9f6b3138690290176ddcf03b64d4839))
* v1 of deploy workflow to home k3s cluster ([4e35c50](https://github.com/madisonewebb/shopkeep/commit/4e35c50b4891db7fd4c9ae7184394d9ff926cbb0))
* v1 of mock etsy api and client ([b4fb5b3](https://github.com/madisonewebb/shopkeep/commit/b4fb5b3d358c450a4771c34e1e87a52f4d6fb3d9))
* wire ORDER_CHANNEL_ID secret and SQLite PVC for k3s deploy ([150141a](https://github.com/madisonewebb/shopkeep/commit/150141aa9b0a28c33f54e1f2be305301ca80c7ad))


### Bug Fixes

* add applications.commands scope to bot invite URL, update !commands to /commands ([5af02be](https://github.com/madisonewebb/shopkeep/commit/5af02be7e444b6239114580826de0bd3f1c0486b))
* catch Etsy API exceptions in !shop and !orders commands ([b7c7b85](https://github.com/madisonewebb/shopkeep/commit/b7c7b853b9d9054c5a8804ae579b58e85dacf477))
* exclude PVC from kustomization, apply manually instead ([0c5df24](https://github.com/madisonewebb/shopkeep/commit/0c5df24ce669f563f34a67ea895d658b340e2cc7))
* exclude PVC from kustomization, apply manually instead ([47c6481](https://github.com/madisonewebb/shopkeep/commit/47c6481836fa9be28b21dc13c60f51e6ab7143ad))
* register existing guilds on startup and DM owners to complete setup ([c6a5e4a](https://github.com/madisonewebb/shopkeep/commit/c6a5e4a70adfaf238f5977f98d6819161952e986))
* remove namespace from kustomization to avoid SA permission error ([df32ca6](https://github.com/madisonewebb/shopkeep/commit/df32ca6e6ad00edbf491ce720207848de523d8eb))
* remove namespace from kustomization to avoid SA permission error ([a552651](https://github.com/madisonewebb/shopkeep/commit/a552651c60b1262be6785578daa4f5b9b4ae56de))
* resolve aiosqlite 'threads can only be started once' crash ([53c192c](https://github.com/madisonewebb/shopkeep/commit/53c192c48013b8f4a21cf6924e4bbe4d08de1d86))
* start poll loop only after bootstrap completes ([48740fb](https://github.com/madisonewebb/shopkeep/commit/48740fb338cfa1bb4d7347721c547f324444135d))
* sync slash commands to each guild on ready for instant propagation ([e835272](https://github.com/madisonewebb/shopkeep/commit/e83527278589ed41dacbb39b8a82b3e720704fa1))
* update file paths for new file structure ([1d3432c](https://github.com/madisonewebb/shopkeep/commit/1d3432c33b2c4c25a1d3e0a6d21e916970598690))
* use keystring:shared_secret format in Etsy shop lookup header ([99909a0](https://github.com/madisonewebb/shopkeep/commit/99909a0d0eea431ac3ce2000d3cf09b1805fc87e))
* use keystring:shared_secret format in EtsyClient authenticated headers ([6eeb03a](https://github.com/madisonewebb/shopkeep/commit/6eeb03a6a2d686d8c9b111807843ab6e46bdec3b))
* use PAT for GHCR login to allow new package creation ([6d196fe](https://github.com/madisonewebb/shopkeep/commit/6d196fe05a15b25bf8de841c76bebe6b4868c1d8))
* use snake_case keys to match Etsy API v3 response format ([745e6fc](https://github.com/madisonewebb/shopkeep/commit/745e6fc604f6d0ac69a211ec6430ceac0330dec9))
* use watchdog reloader so mock API hot-reloads on git pull ([d33c683](https://github.com/madisonewebb/shopkeep/commit/d33c683fbeefb76baf6eb994181da57aa82a7514))


### Refactoring

* delete duplicate discord_bot.py ([ac7596b](https://github.com/madisonewebb/shopkeep/commit/ac7596becf10405c72fc3ba9e5edaf055a6d75b4))
* move discord bot into src dir ([962c706](https://github.com/madisonewebb/shopkeep/commit/962c706babdda2571ff6c42fb1515a07ba538628))
* organize Dockerfiles into directory ([5c3bd14](https://github.com/madisonewebb/shopkeep/commit/5c3bd14ca466ececd6c7e5710e55ff9bb7c8799d))
* remove duplicate files ([0151624](https://github.com/madisonewebb/shopkeep/commit/01516241f5cba0354b0c0ed463f69cd223d5698e))


### Documentation

* add env.example ([396eade](https://github.com/madisonewebb/shopkeep/commit/396eadef27572a646f397aeaefdbf0bef19430d7))
* add initial README ([e1a3a77](https://github.com/madisonewebb/shopkeep/commit/e1a3a77ad17c262dec445de00086a56ab981bca1))
* add SETUP.md with completed work and remaining deployment steps ([8697898](https://github.com/madisonewebb/shopkeep/commit/8697898c20e4326a0c4948ebc58647066415ac69))
* simplify README and add bot commands section ([1b2b27e](https://github.com/madisonewebb/shopkeep/commit/1b2b27eee606247758bb00750f6beb58c9a23e11))
* update README for multi-tenant and real Etsy API ([e6d50de](https://github.com/madisonewebb/shopkeep/commit/e6d50de09424a224da7497186d2bad4da1d8523f))
* update README regarding Docker and Tilt ([0906a99](https://github.com/madisonewebb/shopkeep/commit/0906a9952b8f5111f33953913599f931bfee0358))
* update README with current tech stack and features ([23319f7](https://github.com/madisonewebb/shopkeep/commit/23319f7a4c909ddfef20b1d8cee2b0e7ac2e5927))
* update SETUP.md to reflect completed deployment ([774f5a0](https://github.com/madisonewebb/shopkeep/commit/774f5a0f1cb9c5986305fc311add64b50d523220))
* update SETUP.md with script vs website clarification and latest changes ([e9e5254](https://github.com/madisonewebb/shopkeep/commit/e9e52543663fa24b36bfab99ef4a7c00daa79f84))
