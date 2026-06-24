# Changelog

All notable changes to this project are documented here. The format follows
[Conventional Commits](https://www.conventionalcommits.org); versions follow
[Semantic Versioning](https://semver.org).

## Unreleased

### Features

* **sampling:** forward generation params to kiro-cli via ACP _meta ([#32](https://github.com/ankitcharolia/kiro-gateway/pull/32)) ([b0adecb](https://github.com/ankitcharolia/kiro-gateway/commit/b0adecb25a3fa39c3513bd8789975b5776718cc9))

### Bug Fixes

* **auth:** enforce KIRO_GATEWAY_API_KEY on shim routes ([#39](https://github.com/ankitcharolia/kiro-gateway/pull/39)) ([5d37820](https://github.com/ankitcharolia/kiro-gateway/commit/5d378206e57d44a0d8a85ff87b0d068dc4606c33))
* **acp:** cancel the kiro-cli turn on client disconnect ([#41](https://github.com/ankitcharolia/kiro-gateway/pull/41)) ([a7ecedd](https://github.com/ankitcharolia/kiro-gateway/commit/a7ecedd3788a1a685d107c78ebfc4b21b06bdf19))

## 2.1.0 (2026-06-23)

### Features

* **anthropic:** accept system as string or list and mount shim under multiple base paths ([2e8c635](https://github.com/ankitcharolia/kiro-gateway/commit/2e8c635a9e9722fc41629402dcf929c3e4027a78))
* **shims:** normalize heterogeneous tool definitions to ACP shape ([389cd81](https://github.com/ankitcharolia/kiro-gateway/commit/389cd81d749d60a360e8e718176769133e15d77f))

### Refactoring

* **config:** rename PROXY_API_KEY to KIRO_GATEWAY_API_KEY ([910616a](https://github.com/ankitcharolia/kiro-gateway/commit/910616a4559562b158c40ba612d4b9ba50a400b9))
* **examples:** move client configs to examples/clients with consistent naming ([e49513e](https://github.com/ankitcharolia/kiro-gateway/commit/e49513eb4562da83cc90031d9c9a1295637babad))

### Documentation

* **integration:** add AI-harness client config examples ([3ba5cf2](https://github.com/ankitcharolia/kiro-gateway/commit/3ba5cf203921dcf1b79b0c42c813321cf0f6e88e))
* **integration:** add AI-harness integration section and Oh My Pi examples ([93a9bfc](https://github.com/ankitcharolia/kiro-gateway/commit/93a9bfc24e74d2daf26c6570287709a6a38064d8))

### Dependencies

* **deps:** update actions/cache action to v6 ([90b9394](https://github.com/ankitcharolia/kiro-gateway/commit/90b939420807cde674c7e490d48a467a7973df32))

## 2.0.0 (2026-06-19)

### Features

* **config:** add ACP_TRUST_TOOLS/ACP_WORKSPACE_DIR and env-var aliases ([89d7875](https://github.com/ankitcharolia/kiro-gateway/commit/89d7875ad8b070fd1564f1d1469637f638bf342d))
* **acp:** implement real ACP wire protocol with normalised dict events ([fdabe39](https://github.com/ankitcharolia/kiro-gateway/commit/fdabe39ef47255556a4f22e08b08a5c2372e501e))
* **shims:** live model catalogue, Responses/count_tokens/embeddings endpoints, large-output buffering ([27bbb8a](https://github.com/ankitcharolia/kiro-gateway/commit/27bbb8a672ef408f0e8f05699d59bd9a635a0d59))

### Bug Fixes

* use only KIRO_CLI_PATH, dynamic version from git tag via importlib.metadata ([7426c9a](https://github.com/ankitcharolia/kiro-gateway/commit/7426c9a04a8a5a984fbf6fb3108ad586ce771e58))
* correct kiro-cli command references throughout all docs ([fdaeb48](https://github.com/ankitcharolia/kiro-gateway/commit/fdaeb48cd127d90f0cf2e77feca46e636136585d))
* JsonRpcResponse.error must be Optional[JsonRpcError], not Optional[Dict] ([81fcf15](https://github.com/ankitcharolia/kiro-gateway/commit/81fcf155f0ba67bda309f13c262f1b98c55f072d))
* use bare 'initialize' method + drain kiro-cli stderr to debug protocol ([c904aec](https://github.com/ankitcharolia/kiro-gateway/commit/c904aece22deae3b1e08adccdec91358a132a0b5))

### Documentation

* rewrite README/AGENTS, refresh translations, add CLAUDE.md ([97b08dc](https://github.com/ankitcharolia/kiro-gateway/commit/97b08dc997b8ce397f36961233ce77f2ed12a7e0))
* update agent and architecture guides for the ACP feature set ([918f772](https://github.com/ankitcharolia/kiro-gateway/commit/918f772e8336dcce804a3b8ced633a7d1a54a875))
* add support/donation links across translated docs and funding config ([818f636](https://github.com/ankitcharolia/kiro-gateway/commit/818f6364a4ab80465edbd792c17bd37f0cef3f49))
* highlight support at the top and neutralize compliance wording ([1c3392f](https://github.com/ankitcharolia/kiro-gateway/commit/1c3392f908141af04775cbefaeb9a1981582c4b5))
* **python:** update Python prerequisite to 3.14+ ([a93909d](https://github.com/ankitcharolia/kiro-gateway/commit/a93909d7bb0bf9213c3631d0fba8c28f525d3328))

### Testing

* cover model catalogue, new endpoints, and stdout buffering ([8f56095](https://github.com/ankitcharolia/kiro-gateway/commit/8f56095f7b78e2a3509cfe7bb40394e9a4299b2d))

### Dependencies

* **deps:** update actions/setup-python action to v6 ([b25806e](https://github.com/ankitcharolia/kiro-gateway/commit/b25806e521e967086d9217c29fa2841684d900a5))
* **deps:** update softprops/action-gh-release action to v3 ([79bf8fb](https://github.com/ankitcharolia/kiro-gateway/commit/79bf8fbeaaf594645672e49e86c9a8f2c2c59329))
* **deps:** update actions/checkout action to v7 ([ae21c81](https://github.com/ankitcharolia/kiro-gateway/commit/ae21c812fb04987fdca3eb12453b050d6963b84b))

### Chores

* **docker:** bundle official Kiro CLI in image and mount credentials read-write ([ec2d138](https://github.com/ankitcharolia/kiro-gateway/commit/ec2d13884d5ae47ad52520e6e0efeccf7d10b0e9))
* **python:** standardize toolchain on Python 3.14 ([69f10ca](https://github.com/ankitcharolia/kiro-gateway/commit/69f10cab25131bf1e5f089753d2b2b709f352dc9))

## 1.1.0 (2026-06-13)

### Documentation

* update all language docs to reflect current ACP architecture ([c86cd86](https://github.com/ankitcharolia/kiro-gateway/commit/c86cd86317453496b54fe45b5675218877a74744))

### CI/CD & Build

* add GitHub Release workflow triggered on version tags ([184ca77](https://github.com/ankitcharolia/kiro-gateway/commit/184ca77125f8a2ef32ee68d0087448eb5adc29cd))

### Dependencies

* **deps:** update actions/checkout action to v6 ([4f055d1](https://github.com/ankitcharolia/kiro-gateway/commit/4f055d120920f7cd8e26deb6ba325a5ec1d68607))
* **deps:** update dependency python to 3.14 ([d62be02](https://github.com/ankitcharolia/kiro-gateway/commit/d62be022218d538241251c6ea972b3aa0801c89c))

## 1.0.2 (2026-06-13)

### Bug Fixes

* resolve Docker build failure, Trivy SARIF missing file, and CodeQL v3 deprecation ([90e9822](https://github.com/ankitcharolia/kiro-gateway/commit/90e9822a3fdd6f398d62bb1d8ac4bf2753d51fcb))
* remove GHCR visibility curl call that 404s before package exists ([e63f760](https://github.com/ankitcharolia/kiro-gateway/commit/e63f76079cc5e04c2c42e5fdfade006033e264b7))

### Dependencies

* **deps:** update dependency python ([8cb6421](https://github.com/ankitcharolia/kiro-gateway/commit/8cb642119644217800af05086dbd90907c2b9e11))
* **deps:** update docker/build-push-action action to v7 ([e137303](https://github.com/ankitcharolia/kiro-gateway/commit/e137303ea8cd47d47d4ce03594e785d5a53931c9))
* **deps:** update docker/build-push-action action to v7 ([5611c26](https://github.com/ankitcharolia/kiro-gateway/commit/5611c2616939ba13ac2ebaf23932a67c3e981c94))
* **deps:** update github artifact actions to v7 ([3c25864](https://github.com/ankitcharolia/kiro-gateway/commit/3c2586422e9d885235a1a75e158b7b353849c6f7))
* **deps:** update docker/setup-buildx-action action to v4 ([3b576a5](https://github.com/ankitcharolia/kiro-gateway/commit/3b576a55cfa0ed9f0831e6593816bc6dac4c0498))
* **deps:** update docker/login-action action to v4 ([58654a9](https://github.com/ankitcharolia/kiro-gateway/commit/58654a9b0b2e2ea86f511a8e6955031f850891b7))
* **deps:** update actions/cache action to v5 ([0739afc](https://github.com/ankitcharolia/kiro-gateway/commit/0739afccbeb99f096dc4484205efb35c6ac3636f))
* **deps:** update docker/metadata-action action to v6 ([198f75d](https://github.com/ankitcharolia/kiro-gateway/commit/198f75d8c38fbab17fb3a592819bb4927fece385))
* **deps:** update actions/checkout action to v4.3.1 ([0f36118](https://github.com/ankitcharolia/kiro-gateway/commit/0f36118a89277e8b2c1a834973417012f92a7182))
* **deps:** update actions/checkout action to v6 ([adb2a8d](https://github.com/ankitcharolia/kiro-gateway/commit/adb2a8d3b0c6d0e045d9e0f1c97cea3756a333c6))
* **deps:** update actions/attest-build-provenance action to v4 ([f4f8490](https://github.com/ankitcharolia/kiro-gateway/commit/f4f84909acbd6f4a94a35c1f3c1687e7790d8ed4))
* **deps:** update actions/setup-python action to v6 ([83558ab](https://github.com/ankitcharolia/kiro-gateway/commit/83558abde8e44a8c19f7be65b8bf13162571f402))
* **deps:** update docker/setup-qemu-action action to v4 ([bf0fbe5](https://github.com/ankitcharolia/kiro-gateway/commit/bf0fbe515d1698be325100c120d880281e73eff4))
* **deps:** update dependency python ([1a89d7a](https://github.com/ankitcharolia/kiro-gateway/commit/1a89d7a98f1860cd4025c3184c284ec930f2c9ad))

### Chores

* upgrade all GitHub Actions to Node.js 24-compatible versions ([afb39bc](https://github.com/ankitcharolia/kiro-gateway/commit/afb39bca5554f97387a33055e0315bb8b46c65fa))

## 1.0.0 (2026-06-13)

### Features

* Complete Kiro OpenAI Gateway implementation ([55ff790](https://github.com/ankitcharolia/kiro-gateway/commit/55ff790a342281f9f56f0e5b199fadc4a50d29a8))
* validation for .env file ([c2ef419](https://github.com/ankitcharolia/kiro-gateway/commit/c2ef41992f597726f335b2c2ebe56b0d79a75795))
* add first token timeout retry for streaming requests ([d00cc42](https://github.com/ankitcharolia/kiro-gateway/commit/d00cc42c56e679a03d145d8d85908d63af364df4))
* **tokenizer:** add token counting with tiktoken for usage tracking ([3b6140a](https://github.com/ankitcharolia/kiro-gateway/commit/3b6140a78dc6026802d766d473fb320add733e7c))
* **tokenizer:** add tiktoken fallback, fix multiplier for prompt_tokens, add tests ([1723fcf](https://github.com/ankitcharolia/kiro-gateway/commit/1723fcf8f8b68960be357a322f44810dfe2201a3))
* **debug_logger:** implement logs capture and storage ([01fc8f4](https://github.com/ankitcharolia/kiro-gateway/commit/01fc8f4cfa0c3ce878613515ebbf4b7bd202f329))
* add CORS middleware for OPTIONS preflight support ([c146803](https://github.com/ankitcharolia/kiro-gateway/commit/c146803ab1a75df9c28fa90f554496f9adfd6b57))
* add CLA message for PR contributions ([44959ea](https://github.com/ankitcharolia/kiro-gateway/commit/44959eaa2efacc5270ffc839973c323359608d47))
* add configurable streaming read timeout ([#9](https://github.com/ankitcharolia/kiro-gateway/pull/9)) ([079364d](https://github.com/ankitcharolia/kiro-gateway/commit/079364db6480bdb142831f5d2175e4e866adc7cb))
* enhance credential loading and logging in manual_api_test.py ([a287c27](https://github.com/ankitcharolia/kiro-gateway/commit/a287c2766542743ca142cc1472975098d3ab2e78))
* **auth:** add AWS SSO OIDC support for kiro-cli credentials ([#12](https://github.com/ankitcharolia/kiro-gateway/pull/12)) ([b994a02](https://github.com/ankitcharolia/kiro-gateway/commit/b994a0225ed8045662e513b2f9bb58d5f2911aef))
* implement fake reasoning with extended thinking support ([#11](https://github.com/ankitcharolia/kiro-gateway/pull/11)) ([9df35c0](https://github.com/ankitcharolia/kiro-gateway/commit/9df35c00a4eab4120c457d432b4589fa5c898f4d))
* add configurable server port/host ([#19](https://github.com/ankitcharolia/kiro-gateway/pull/19)) ([6b5f876](https://github.com/ankitcharolia/kiro-gateway/commit/6b5f8769bc5668389c7ac53b58e3d5421763e835))
* **api:** Anthropic Messages API support ([#15](https://github.com/ankitcharolia/kiro-gateway/pull/15)) ([8978b84](https://github.com/ankitcharolia/kiro-gateway/commit/8978b84936fa010eff54a5837eb9758f987e9f74))
* **anthropic:** add thinking content blocks for extended thinking ([90fcf0d](https://github.com/ankitcharolia/kiro-gateway/commit/90fcf0d275fb11ca60a92dfe6fffa57e1d55e614))
* add dynamic model resolution with client format normalization ([6ce52d9](https://github.com/ankitcharolia/kiro-gateway/commit/6ce52d9ed9584b0c442a973876830df97d240a1c))
* add DebugLoggerMiddleware to capture validation errors in debug logs ([#31](https://github.com/ankitcharolia/kiro-gateway/pull/31)) ([0ac42c5](https://github.com/ankitcharolia/kiro-gateway/commit/0ac42c54f1ab8ef261ce82a5eb5f8720fff636f8))
* **parsers:** add diagnostics for truncated tool call arguments ([#34](https://github.com/ankitcharolia/kiro-gateway/pull/34)) ([0c1b291](https://github.com/ankitcharolia/kiro-gateway/commit/0c1b29139d1a7bd053d382a062a210ad76e186e6))
* **startup:** add GitHub issues link to startup banner ([7b3b503](https://github.com/ankitcharolia/kiro-gateway/commit/7b3b5035954c324e1db5d077bbabfceb82284a85))
* **auth:** add support for social login SQLite credentials ([3b4ddd1](https://github.com/ankitcharolia/kiro-gateway/commit/3b4ddd15c5d789750275f18918a1628e39c3fd26))
* add Enterprise Kiro IDE support with unified AWS SSO OIDC format (#43, #45, #48) ([0639485](https://github.com/ankitcharolia/kiro-gateway/commit/0639485615b20d7668473c9b2f7f6ebc97484ac7))
* **proxy:** add HTTP/SOCKS5 proxy support for restricted networks ([b1e4872](https://github.com/ankitcharolia/kiro-gateway/commit/b1e48723d3ae44245dcdfb8593683c5c4e0f7ce8))
* **openai:** support Cursor flat format, inverted model names, and improve tool_results handling ([#49](https://github.com/ankitcharolia/kiro-gateway/pull/49)) ([936f798](https://github.com/ankitcharolia/kiro-gateway/commit/936f7983c9bc3473d50fcd7b3b84f7cb8954d72d))
* **errors:** add network error classification with user-friendly messages ([#53](https://github.com/ankitcharolia/kiro-gateway/pull/53)) ([80f33a2](https://github.com/ankitcharolia/kiro-gateway/commit/80f33a252e6564ebd6a8dfaa72e26c6718b9fb85))
* **model-resolver:** add alias system to resolve Cursor IDE conflict ([#59](https://github.com/ankitcharolia/kiro-gateway/pull/59)) ([365d4b3](https://github.com/ankitcharolia/kiro-gateway/commit/365d4b3496c9dd1ebe84f036a39f2a02d7041efd))
* add truncation recovery system (#34, #42, #56) ([f68d763](https://github.com/ankitcharolia/kiro-gateway/commit/f68d76354cf231dfcc526bd32e951b76afb842b0))
* **docker:** add Docker containerization with CI/CD ([#55](https://github.com/ankitcharolia/kiro-gateway/pull/55)) ([3919b37](https://github.com/ankitcharolia/kiro-gateway/commit/3919b374a30e0eeeec8553e0ceda51cb09c31305))
* **errors:** add centralized Kiro API error enhancement system (#10, #63) ([6ff94ce](https://github.com/ankitcharolia/kiro-gateway/commit/6ff94cecb642adeb6acbb2aa5b1f958b3c5bcc5b))
* **errors:** improve MONTHLY_REQUEST_COUNT error message ([#62](https://github.com/ankitcharolia/kiro-gateway/pull/62)) ([257623f](https://github.com/ankitcharolia/kiro-gateway/commit/257623f062947a50d3ce066cd554c821085a65c5))
* payload size guard with pre-flight check and auto-trim ([#73](https://github.com/ankitcharolia/kiro-gateway/pull/73)) ([6ce8e4c](https://github.com/ankitcharolia/kiro-gateway/commit/6ce8e4c201d9895c11a564aaddef52da90ad4dc1))
* **thinking:** add client thinking budget support for OpenAI and Anthropic APIs ([#111](https://github.com/ankitcharolia/kiro-gateway/pull/111)) ([1671fac](https://github.com/ankitcharolia/kiro-gateway/commit/1671fac03243f5c060eaf5a41a94d8ebbdfa7f52))
* **websearch:** add MCP tool emulation support ([#101](https://github.com/ankitcharolia/kiro-gateway/pull/101)) ([a6f10ff](https://github.com/ankitcharolia/kiro-gateway/commit/a6f10ffe5cf572dceb100013770c8bb964851713))
* **auth:** auto-detect API region from credentials (#132, #133) ([b597a56](https://github.com/ankitcharolia/kiro-gateway/commit/b597a5698ac7e3b033d1b4c9eb2d8ba693071676))
* **account-system:** add multi-account support with failover ([#93](https://github.com/ankitcharolia/kiro-gateway/pull/93)) ([d2634ce](https://github.com/ankitcharolia/kiro-gateway/commit/d2634ce035429bd4b77ffcbbf1cbcc2182ea13dc))
* **anthropic:** add /v1/messages/count_tokens endpoint ([5eaff39](https://github.com/ankitcharolia/kiro-gateway/commit/5eaff3913c9955060db75880069d248c0150bc9b))
* **models:** implement model discovery and pass-through to Kiro API ([a9ad27d](https://github.com/ankitcharolia/kiro-gateway/commit/a9ad27d5c9147b24d1f588303bcb64d228a883e6))
* ACP-compliant gateway wrapping kiro-cli ([3334910](https://github.com/ankitcharolia/kiro-gateway/commit/3334910767f9cb50ade3d41559666e1d995b7ae5))
* implement full ACP client, shim service, and all shim routes ([55e3012](https://github.com/ankitcharolia/kiro-gateway/commit/55e301252c525dd8cdc365767d749238be12d42a))
* full converter + streaming implementations (batch 3) ([3521dce](https://github.com/ankitcharolia/kiro-gateway/commit/3521dcefbc70571d6b942751ee958b0744377eb3))
* request parsing, thinking parser, tokenizer, truncation (batch 4) ([69f3152](https://github.com/ankitcharolia/kiro-gateway/commit/69f3152ab5daa8f444b55ad06cc3c28533227fbf))
* model resolver, payload guards, MCP tools, config expansion (batch 5) ([b80500f](https://github.com/ankitcharolia/kiro-gateway/commit/b80500fc7496b73902ad3170df91e5f93a352f7f))
* full test suite – conftest, pytest config, converter + streaming tests (batch 6) ([0b0642a](https://github.com/ankitcharolia/kiro-gateway/commit/0b0642a5dd1d83d4eb78dc193df0f637fc82a10f))

### Bug Fixes

* translate error messages to English ([067db7d](https://github.com/ankitcharolia/kiro-gateway/commit/067db7def6908a4ef2b6d22713cfe1be8239533d))
* **tests:** correct error message assertion in test_raises_for_empty_messages ([fa72f1f](https://github.com/ankitcharolia/kiro-gateway/commit/fa72f1f3200aa5b004c8536f07b4cecfe3cf86e4))
* handle Kiro API 400 "Improperly formed request" for long tool descriptions ([1e77cb5](https://github.com/ankitcharolia/kiro-gateway/commit/1e77cb5aa5d1d3bacfb4cc8ea7ec8e1580854903))
* update version to 1.0.1 and modify author attribution ([a8d7bf6](https://github.com/ankitcharolia/kiro-gateway/commit/a8d7bf68945c4f6c6962a4104490002216fd214b))
* add index to streaming tool_calls, handle tool messages, improve deduplication ([56a5b8a](https://github.com/ankitcharolia/kiro-gateway/commit/56a5b8af36f11ac7f7bf4730679e0f97421b56d5))
* update application version to 1.0.2 ([a1ebb3f](https://github.com/ankitcharolia/kiro-gateway/commit/a1ebb3f484543c91e0620560a82d7f9904f05818))
* improve error handling in chat completions endpoint to return structured JSON response ([60f9c1c](https://github.com/ankitcharolia/kiro-gateway/commit/60f9c1c35389b67bc1f91b42684e6e06be3a2625))
* normalize KIRO_CREDS_FILE path for cross-platform compatibility ([fe6f297](https://github.com/ankitcharolia/kiro-gateway/commit/fe6f2972b24f5c434e9d10d3767c4e01fbdf536d))
* read KIRO_CREDS_FILE without escape sequence processing for Windows paths ([199678f](https://github.com/ankitcharolia/kiro-gateway/commit/199678fa935a64efed65e950780d8d81b981758a))
* reduce default FIRST_TOKEN_TIMEOUT to 15 seconds ([78c553b](https://github.com/ankitcharolia/kiro-gateway/commit/78c553bfa6bf73d562e3df24905c92a1dbcbf72c))
* preserve tool_calls when merging assistant messages; add DEBUG_MODE with errors/all modes ([d30c8bc](https://github.com/ankitcharolia/kiro-gateway/commit/d30c8bcc9fef4ea11d045effbfb6ed4f31b343b2))
* add Cline support - sanitize tool schemas and handle empty descriptions ([2aa4eaf](https://github.com/ankitcharolia/kiro-gateway/commit/2aa4eaf03233ca3edce8f99738d5a4e46ea337fc))
* improve streaming error handling and prevent silent failures ([0918457](https://github.com/ankitcharolia/kiro-gateway/commit/09184575169071206e15c3df7053c64d703ea1fe))
* update CLA message for clarity and conciseness ([6ee805b](https://github.com/ankitcharolia/kiro-gateway/commit/6ee805b1a7ad3e4d5ae114fc1ea058a4ac65c0ec))
* update CLA label and message ([071ce68](https://github.com/ankitcharolia/kiro-gateway/commit/071ce6893464180b6cce6b1574ef7838d8081da3))
* update contributors list in CLA ([a1e7978](https://github.com/ankitcharolia/kiro-gateway/commit/a1e79783d3bdf62523ff4af08cac6ba0cdbcf857))
* use original KiroIDE User-Agent format ([fc83bdb](https://github.com/ankitcharolia/kiro-gateway/commit/fc83bdb9515ac034d633ccd4415701c1ceef95ec))
* remove duplicate log, reduce thinking buffer to 20 chars ([3106529](https://github.com/ankitcharolia/kiro-gateway/commit/3106529e5eb91b340897bab43289b884aa757799))
* **reasoning:** add system prompt legitimization for thinking tags ([5466570](https://github.com/ankitcharolia/kiro-gateway/commit/54665705b097788681a99e0578706294a168ed97))
* **auth:** don't send profileArn for AWS SSO OIDC (causes 403) ([#12](https://github.com/ankitcharolia/kiro-gateway/pull/12)) ([5cb5abd](https://github.com/ankitcharolia/kiro-gateway/commit/5cb5abde5bacc3ccdadab5b23db32e24ade56d37))
* **auth:** add detailed AWS SSO OIDC error logging ([#14](https://github.com/ankitcharolia/kiro-gateway/pull/14)) ([13a2479](https://github.com/ankitcharolia/kiro-gateway/commit/13a247937718f0a05963e99d311d232623f48011))
* **auth:** don't send scope in AWS SSO OIDC refresh ([#14](https://github.com/ankitcharolia/kiro-gateway/pull/14)) ([69795d1](https://github.com/ankitcharolia/kiro-gateway/commit/69795d186f078eb45e0b39e34a3b69bd84e5b6e6))
* **auth:** separate SSO region from API region for AWS SSO OIDC ([#16](https://github.com/ankitcharolia/kiro-gateway/pull/16)) ([d5ad4b1](https://github.com/ankitcharolia/kiro-gateway/commit/d5ad4b1f3a712105cd50600828596896ca9657a9))
* update contributors list in CLA ([dcf3f3f](https://github.com/ankitcharolia/kiro-gateway/commit/dcf3f3f402ed46105594b8ee4e1c3d7d66ff52f0))
* update CLA message for clarity ([3769733](https://github.com/ankitcharolia/kiro-gateway/commit/3769733a0f49d919984d8ac67d782fd8510dd1cc))
* **converters:** skip thinking tag injection when toolResults present ([#23](https://github.com/ankitcharolia/kiro-gateway/pull/23)) ([ee8b561](https://github.com/ankitcharolia/kiro-gateway/commit/ee8b5610bc0056ca41d1fda58aa5c870bfea22a2))
* **auth:** reload SQLite credentials before AWS SSO OIDC token refresh ([#22](https://github.com/ankitcharolia/kiro-gateway/pull/22)) ([a15cb82](https://github.com/ankitcharolia/kiro-gateway/commit/a15cb829df160dab226a8538f262b9c1cb2a1280))
* **auth:** retry SQLite reload on 400 for container token refresh ([#14](https://github.com/ankitcharolia/kiro-gateway/pull/14)) ([d1e9214](https://github.com/ankitcharolia/kiro-gateway/commit/d1e92144aafdd65711347579621fa7b3c3cd2199))
* **http:** add shared HTTP client with connection pooling ([#24](https://github.com/ankitcharolia/kiro-gateway/pull/24)) ([bb09c03](https://github.com/ankitcharolia/kiro-gateway/commit/bb09c0327c3e195a2fbd1d4443b2058ffc2194e8))
* **anthropic:** support system as content blocks for prompt caching ([5d93165](https://github.com/ankitcharolia/kiro-gateway/commit/5d931652a49a7282a9ede0420ee1f2892cc79353))
* convert tool_results to Kiro API format (toolUseId) ([947cbff](https://github.com/ankitcharolia/kiro-gateway/commit/947cbffe19eb500f1ce0c093d1fd705cfb148387))
* **converters:** handle orphaned tool_results and strip tool content when no tools defined ([1dca186](https://github.com/ankitcharolia/kiro-gateway/commit/1dca18644e92ec9fc18d82cc417b80f679bd10fa))
* **logging:** suppress noisy shutdown tracebacks on Ctrl+C ([ac58ac5](https://github.com/ankitcharolia/kiro-gateway/commit/ac58ac57d47ab0a9ce98c7f8f6383845baea44ef))
* **config:** update application version to 2.0-rc.1 ([bf4e516](https://github.com/ankitcharolia/kiro-gateway/commit/bf4e516556d125fd475c63b548d0c42add4828c7))
* update CLA contributors ([cbf9010](https://github.com/ankitcharolia/kiro-gateway/commit/cbf9010652b67f0b24a18fa3451a757c340e6071))
* **converters:** add placeholders for empty content after tool stripping ([#20](https://github.com/ankitcharolia/kiro-gateway/pull/20)) ([b3cb5d5](https://github.com/ankitcharolia/kiro-gateway/commit/b3cb5d5bd8f5ddb0429df40e94f191d3e3c8c11c))
* **converters:** convert tool content to text when tools not defined ([#20](https://github.com/ankitcharolia/kiro-gateway/pull/20)) ([f8e830c](https://github.com/ankitcharolia/kiro-gateway/commit/f8e830ca82f5fddd2b89af33110c0e9b3c2f0c18))
* standardize bug report title format and emphasize log requirement ([6afcbab](https://github.com/ankitcharolia/kiro-gateway/commit/6afcbab8955c9ed954141e0deed357db35ed85c9))
* **auth:** add graceful degradation for SQLite mode ([#14](https://github.com/ankitcharolia/kiro-gateway/pull/14)) ([c3b4379](https://github.com/ankitcharolia/kiro-gateway/commit/c3b43795e66628bd11ec07ca38fdc8cca9242417))
* **models:** add image content block support ([#30](https://github.com/ankitcharolia/kiro-gateway/pull/30)) ([bda15b0](https://github.com/ankitcharolia/kiro-gateway/commit/bda15b0e2e262c74dfe23a776b0e9bcdc6ffacc6))
* **config:** update application version to 2.0 ([#15](https://github.com/ankitcharolia/kiro-gateway/pull/15)) ([17dd8b4](https://github.com/ankitcharolia/kiro-gateway/commit/17dd8b49b0af617e5b6a470c48168371513f1173))
* **anthropic:** add ThinkingContentBlock to ContentBlock union ([#31](https://github.com/ankitcharolia/kiro-gateway/pull/31)) ([fa8a0f9](https://github.com/ankitcharolia/kiro-gateway/commit/fa8a0f966882021acbd8999971491b7814787616))
* **exceptions:** comment out request body logging in validation error handler ([e4a319d](https://github.com/ankitcharolia/kiro-gateway/commit/e4a319d09358487b992e5f0b1f849f5537d94a3a))
* **vision:** move images to userInputMessage.images for proper Kiro API handling ([#32](https://github.com/ankitcharolia/kiro-gateway/pull/32)) ([f4ee183](https://github.com/ankitcharolia/kiro-gateway/commit/f4ee183f326f50593b3f7d8ba5ff3e977d5b4864))
* **docs:** update feature descriptions ([8394347](https://github.com/ankitcharolia/kiro-gateway/commit/8394347b115493224b60e2b94e352bae21c5578c))
* update CLA contributors ([d920bcf](https://github.com/ankitcharolia/kiro-gateway/commit/d920bcf035a50b4f80736ef59c0e284162c758bf))
* add Connection: close header for streaming requests ([#38](https://github.com/ankitcharolia/kiro-gateway/pull/38)) ([49656fb](https://github.com/ankitcharolia/kiro-gateway/commit/49656fbca27e0c5e4fd0b890e2a90b8f5bd5d254))
* validate tool names against 64-char Kiro API limit ([#41](https://github.com/ankitcharolia/kiro-gateway/pull/41)) ([f918f50](https://github.com/ankitcharolia/kiro-gateway/commit/f918f50b826ef163de626f6fbb9fe1f88fc8cbf4))
* **auth:** persist refreshed AWS SSO OIDC tokens back to SQLite ([#43](https://github.com/ankitcharolia/kiro-gateway/pull/43)) ([fab6f56](https://github.com/ankitcharolia/kiro-gateway/commit/fab6f56f6b5fc87d14ee988de83a75d124a7c82f))
* **auth:** use correct AWS SSO OIDC CreateToken API format ([#43](https://github.com/ankitcharolia/kiro-gateway/pull/43)) ([3d86091](https://github.com/ankitcharolia/kiro-gateway/commit/3d860917bd0f35e32a7dda47b17cdeb2ed2cc724))
* update CLA contributors ([c62ce04](https://github.com/ankitcharolia/kiro-gateway/commit/c62ce040ef5c7ea11432b81a12304aaa8dca474a))
* **models:** add fallback list for DNS failure recovery ([#25](https://github.com/ankitcharolia/kiro-gateway/pull/25)) ([c33862b](https://github.com/ankitcharolia/kiro-gateway/commit/c33862bc0cf5931ea1bb67c51fce70a4be0ad95a))
* **converters:** handle Pydantic models in extract_text_content (#46, #50) ([80b100d](https://github.com/ankitcharolia/kiro-gateway/commit/80b100dd9d53511b777420511a4b7e467d6ad746))
* **routes:** use per-request clients for streaming to prevent CLOSE_WAIT leak ([#54](https://github.com/ankitcharolia/kiro-gateway/pull/54)) ([1c2e998](https://github.com/ankitcharolia/kiro-gateway/commit/1c2e99861b7bf0d909eb69ad3874c458a1ae4abc))
* update CLA contributors ([c4e5e03](https://github.com/ankitcharolia/kiro-gateway/commit/c4e5e03d8939f980925ca986ab680fee449a2019))
* **config:** use universal q.{region}.amazonaws.com endpoint for all regions ([#58](https://github.com/ankitcharolia/kiro-gateway/pull/58)) ([e57b58c](https://github.com/ankitcharolia/kiro-gateway/commit/e57b58c3a1f79d6cf7ec40d50000449e7978ad3f))
* **docker:** improve Docker configuration and CI/CD pipeline ([999d28d](https://github.com/ankitcharolia/kiro-gateway/commit/999d28daaa9095d543670a318bd3992deed38ee6))
* **tests:** read PROXY_API_KEY from config instead of hardcoded value ([ec1328c](https://github.com/ankitcharolia/kiro-gateway/commit/ec1328c3c57bf47c3f4eb8205340fc77c96411d1))
* **config:** restore timeout configuration warning ([9c7933c](https://github.com/ankitcharolia/kiro-gateway/commit/9c7933cf9f458a7c1fa98207f12a6776b25718dd))
* **thinking:** ensure response language matches user preference ([5460a3d](https://github.com/ankitcharolia/kiro-gateway/commit/5460a3d134f03264d8414ae5effe3ad7bbe1ad07))
* **converters:** ensure first message is user to prevent Improperly formed request ([#60](https://github.com/ankitcharolia/kiro-gateway/pull/60)) ([dd2a487](https://github.com/ankitcharolia/kiro-gateway/commit/dd2a487cc6f9493f134a2ba4946cfd9ac63fe009))
* **anthropic:** extract images from tool_result content blocks ([#57](https://github.com/ankitcharolia/kiro-gateway/pull/57)) ([c454c43](https://github.com/ankitcharolia/kiro-gateway/commit/c454c434c7b02ff7f0206e0a8ba1b5f463992a51))
* **openai:** extract images from tool messages for MCP screenshot support ([c957a43](https://github.com/ankitcharolia/kiro-gateway/commit/c957a435e997d6e88c5ce0d5bf78daf5a55e2cbc))
* **converters:** add support for unknown roles ([#64](https://github.com/ankitcharolia/kiro-gateway/pull/64)) ([ec80818](https://github.com/ankitcharolia/kiro-gateway/commit/ec808180d5e5823e88e06d42b55dfe7f23d9119c))
* **models:** add tool_reference content block support ([#90](https://github.com/ankitcharolia/kiro-gateway/pull/90)) ([b52c694](https://github.com/ankitcharolia/kiro-gateway/commit/b52c694d4795f7a865dcb978305b283f4ab9bb71))
* disable AUTO_TRIM_PAYLOAD by default ([#73](https://github.com/ankitcharolia/kiro-gateway/pull/73)) ([b46df61](https://github.com/ankitcharolia/kiro-gateway/commit/b46df610527669dc84ca08ab6771942e5a667cb2))
* **anthropic:** accurate token estimation for Anthropic API path ([#135](https://github.com/ankitcharolia/kiro-gateway/pull/135)) ([1901c76](https://github.com/ankitcharolia/kiro-gateway/commit/1901c76ca8742e862cf8ed2cb3908ad9ed339831))
* **streaming:** enable retry mechanism and return correct finish_reason on truncation ([#113](https://github.com/ankitcharolia/kiro-gateway/pull/113)) ([50fa948](https://github.com/ankitcharolia/kiro-gateway/commit/50fa948bb2d5e9721c842dec2160fbc24c45d56a))
* **auth:** preserve unknown fields in SQLite write-back ([#131](https://github.com/ankitcharolia/kiro-gateway/pull/131)) ([b71b30d](https://github.com/ankitcharolia/kiro-gateway/commit/b71b30d3cbd7c88d453299229465719e43c17e7c))
* **docker:** mount kiro-cli volume as rw and exclude .cache from image ([#97](https://github.com/ankitcharolia/kiro-gateway/pull/97)) ([25c7bc1](https://github.com/ankitcharolia/kiro-gateway/commit/25c7bc14f5042c55f68caa0fb2954f1423a6eceb))
* **auth:** truncate nanoseconds in SQLite expires_at parsing ([#78](https://github.com/ankitcharolia/kiro-gateway/pull/78)) ([95cd9e7](https://github.com/ankitcharolia/kiro-gateway/commit/95cd9e7cf4322545133fd63ba89d00d843327c96))
* **auth:** remove duplicate re import ([cb22e32](https://github.com/ankitcharolia/kiro-gateway/commit/cb22e32fe4fd792d7d6a4156b1dd3533ae628492))
* **streaming:** import stream_with_first_token_retry_anthropic in routes_anthropic ([#138](https://github.com/ankitcharolia/kiro-gateway/pull/138)) ([25ca50d](https://github.com/ankitcharolia/kiro-gateway/commit/25ca50dcbfdee1f1c8c1bca6a6363642a8d399ca))
* **docker:** exclude credentials.json and state.json from image ([7d652c6](https://github.com/ankitcharolia/kiro-gateway/commit/7d652c665f5096b04fead432543782ac40a8a803))
* **ci:** remove test artifacts before Docker build ([dfe744e](https://github.com/ankitcharolia/kiro-gateway/commit/dfe744eb6da5eb59bf7285c6e77e9b9a5e5d68d2))
* **docker:** remove runtime files from image build ([fdc29e0](https://github.com/ankitcharolia/kiro-gateway/commit/fdc29e05253e9aae703a59c7f7569656eaf0decc))
* **docker:** remove read-only credentials.json before writing ([1767d0e](https://github.com/ankitcharolia/kiro-gateway/commit/1767d0e0362f86adaf0bde8a389fa03409a02896))
* **docker:** grant write permissions to /app for kiro user ([50d6119](https://github.com/ankitcharolia/kiro-gateway/commit/50d6119202253a842602d4a82d428fb19aaf7c73))
* **main:** correct indentation for credentials.json save block ([0aa3b4e](https://github.com/ankitcharolia/kiro-gateway/commit/0aa3b4e21c92dac35527fcd77f0011f240ee40f5))
* **cli:** parse arguments before config validation for --version support ([c0912c1](https://github.com/ankitcharolia/kiro-gateway/commit/c0912c1c63909b314b8e3a00e2584ab684b86540))
* **endpoint:** migrate API from q.amazonaws.com to runtime.kiro.dev ([07d24fc](https://github.com/ankitcharolia/kiro-gateway/commit/07d24fc706fce3a40c39a2579bc0dcfdbe238e42))
* **endpoint:** improve runtime.kiro.dev migration ([90d0509](https://github.com/ankitcharolia/kiro-gateway/commit/90d0509b9ce5aa3f725214ec4e5342673cf7e50e))
* **parsers:** handle empty dict in streaming tool calls ([20d583f](https://github.com/ankitcharolia/kiro-gateway/commit/20d583f3b5242742299309bb66ec9d303cce1536))
* **errors:** enhance INVALID_MODEL_ID to mention subscription level ([576c2fe](https://github.com/ankitcharolia/kiro-gateway/commit/576c2feb1662007186d596a878af906a7404ca55))
* **converters:** replace "Continue" and "(empty)" with "(empty placeholder)" ([#171](https://github.com/ankitcharolia/kiro-gateway/pull/171)) ([b370ec5](https://github.com/ankitcharolia/kiro-gateway/commit/b370ec5de14d3cc48cd575f9b71cab1ff9e3832f))
* **gateway:** bug with profileArn fixed ([f65c41b](https://github.com/ankitcharolia/kiro-gateway/commit/f65c41b5e88237fc735d203832a04ebc61c3062a))
* correct action versions, Python version, and asyncio_mode in pytest CI ([0bb33d3](https://github.com/ankitcharolia/kiro-gateway/commit/0bb33d38c7d5e274d704cd8450dd71853135c275))
* add pydantic-settings and missing test deps to requirements.txt ([169d0d4](https://github.com/ankitcharolia/kiro-gateway/commit/169d0d4115f024991b4a2ea9d528670834c143ba))
* expose flat module-level aliases from Settings so __init__.py and tests can import them ([36eb208](https://github.com/ankitcharolia/kiro-gateway/commit/36eb20810ba6a513278eba636441c4ac5304a376))
* remove dead kiro.auth import from __init__.py; delete obsolete auth/account tests ([dbfa19a](https://github.com/ankitcharolia/kiro-gateway/commit/dbfa19afb597369a6e22b8dba64fcf4997fa71bf))
* remove dead kiro.cache import that broke all 28 test collections ([104b727](https://github.com/ankitcharolia/kiro-gateway/commit/104b727ade2b6c59cd821939ad09791555e7b7df))
* remove KiroHttpClient import from __init__.py; replace removed-module test ([d3a42ff](https://github.com/ankitcharolia/kiro-gateway/commit/d3a42ffeeeff8fb19baa5fb268e8756939c6e8bd))
* import router from routes_openai_shim (routes_openai removed) ([77184ca](https://github.com/ankitcharolia/kiro-gateway/commit/77184ca1512d038d4c89723647cf92ec218f00c8))
* **tests:** implement core stub modules — config, models, truncation, http_client, routes_openai ([6fcd30c](https://github.com/ankitcharolia/kiro-gateway/commit/6fcd30c5d39dcd39c820991dd766441f656170ab))
* **tests:** implement remaining stub modules — errors, cache, streaming, converters, etc. ([7b4b2b1](https://github.com/ankitcharolia/kiro-gateway/commit/7b4b2b1943669e646d24bb699eb22b1ae12535a2))
* **tests:** add conftest, pyproject.toml, __init__, ci.yml ([d412429](https://github.com/ankitcharolia/kiro-gateway/commit/d4124293f0c0585d094494b56c689f4b0f1580da))
* expand module APIs to match test expectations (batch 1) ([9b92cb7](https://github.com/ankitcharolia/kiro-gateway/commit/9b92cb70de5d0803d5772ec9a8cc9e387b60d32a))
* expand Pydantic models to match test expectations (batch 2) ([98f61dc](https://github.com/ankitcharolia/kiro-gateway/commit/98f61dc13c8b99ce9de09f93f80a4b8ff8612bf2))
* use setuptools.build_meta backend (fixes BackendUnavailable in CI) ([1036053](https://github.com/ankitcharolia/kiro-gateway/commit/103605366e016732bd32e1981e52333fef491eee))
* add missing ACPRequest/ACPMessage/ACPResponse/content-block models ([7554bf6](https://github.com/ankitcharolia/kiro-gateway/commit/7554bf6b78babf1d780b87e2384a385b5fd51004))
* add compliance-mode compat exports across all shim modules ([9086ba2](https://github.com/ankitcharolia/kiro-gateway/commit/9086ba2d84032337b27520d51304c8c550cb07cb))
* tell hatchling where the package lives (kiro/ dir) ([1b7f246](https://github.com/ankitcharolia/kiro-gateway/commit/1b7f246c09a7a805bb0f8bf99684312918c5edfe))
* add all models expected by tests/conftest.py ([b31debf](https://github.com/ankitcharolia/kiro-gateway/commit/b31debfc86dba1b272abf14b2423f672581255ef))
* add pytest-cov to dev deps so --cov flag is recognized in CI ([25992ba](https://github.com/ankitcharolia/kiro-gateway/commit/25992bac4f7306574adc9f170f11a4cd3379d3ae))
* **acp_models:** add ACPToolResult, ACPTool, JsonRpcRequest, PromptMessage compat aliases ([2d42ee8](https://github.com/ankitcharolia/kiro-gateway/commit/2d42ee8f9b9e6c97c512c632fa149813d1cbee3b))
* **model_resolver:** add get_capabilities, list_models, get_model_id_for_kiro ([efbdd7c](https://github.com/ankitcharolia/kiro-gateway/commit/efbdd7cf30b81e268b6f584602174f9ad38fb3f9))
* **tokenizer:** add count_tokens compat alias ([4ae74df](https://github.com/ankitcharolia/kiro-gateway/commit/4ae74df0c0b6414af2971b7bf4374e9f278b9cce))
* **payload_guards:** add guard_openai_request, guard_anthropic_request, check_payload_size ([39eea4c](https://github.com/ankitcharolia/kiro-gateway/commit/39eea4ca03dde3c49356e7c9ddb250e10eab43bc))
* **truncation_state:** add TruncationState, truncate_messages, estimate_conversation_tokens, get_tool_truncation ([e252bdf](https://github.com/ankitcharolia/kiro-gateway/commit/e252bdf59a68f90fd8622a63d9b90ef51ea100c2))
* **truncation_recovery:** add generate_truncation_tool_result ([a056c08](https://github.com/ankitcharolia/kiro-gateway/commit/a056c0807b6f17493691f4b4b2cc3d2d996c110c))
* **streaming_anthropic:** add acp_stream_to_anthropic_events and generate_thinking_signature ([b161dff](https://github.com/ankitcharolia/kiro-gateway/commit/b161dff3e7acedc77747d378060e9505f2738e27))
* **streaming_openai:** add stream_kiro_to_openai_internal compat alias ([75ebb3e](https://github.com/ankitcharolia/kiro-gateway/commit/75ebb3e063211be68591eae259e182b7b2bb2b01))
* **streaming_core:** add StreamResult dataclass ([c41d1f8](https://github.com/ankitcharolia/kiro-gateway/commit/c41d1f873a77e27018f48e6134993411253277aa))
* **thinking_parser:** add ThinkingParseResult alias for ParsedThinking ([a5692e9](https://github.com/ankitcharolia/kiro-gateway/commit/a5692e953b239a192cd62f19ba654fd84a65aea5))
* **parsers:** add find_matching_brace utility ([3e39cc0](https://github.com/ankitcharolia/kiro-gateway/commit/3e39cc02f8cfdcff68419d0ebb228e0a78b38107))
* **mcp_tools:** add call_kiro_mcp_api compat stub ([3a0e7f1](https://github.com/ankitcharolia/kiro-gateway/commit/3a0e7f1cce29da15dc579fe70d9a3736290cdc8a))
* **routes_anthropic:** export verify_anthropic_api_key for tests ([6853c72](https://github.com/ankitcharolia/kiro-gateway/commit/6853c72777a52d8de0cf45c279953cd798a1c485))
* **acp_models:** add ACPImageBlock, JsonRpcResponse ([504eed7](https://github.com/ankitcharolia/kiro-gateway/commit/504eed76347dfcf35df8813d5a1dbcacf28fe941))
* **models_anthropic:** add ThinkingConfig, Base64ImageSource ([b9398da](https://github.com/ankitcharolia/kiro-gateway/commit/b9398dae77c48943474f32fa874728f03ca932ea))
* **models_openai:** add OpenAIModel and full request/response models ([8189d9b](https://github.com/ankitcharolia/kiro-gateway/commit/8189d9bc8843c0bcc8637b9fd2cc1f9264902d5b))
* **model_resolver:** add extract_model_family compat export ([f65e0f4](https://github.com/ankitcharolia/kiro-gateway/commit/f65e0f42ab021ba734bab730393d4fd8b49f30df))
* **tokenizer:** add count_tools_tokens compat export ([8feb940](https://github.com/ankitcharolia/kiro-gateway/commit/8feb940f6195520c43591938bcca62fedb6a7b01))
* **payload_guards:** add trim_payload_to_limit compat export ([9f816ed](https://github.com/ankitcharolia/kiro-gateway/commit/9f816ed3bbda36f81d8f06332ffd67188608d0e1))
* **truncation_recovery:** add with_truncation_recovery, generate_truncation_user_message ([10899fc](https://github.com/ankitcharolia/kiro-gateway/commit/10899fcb0ef039146fed9a5d4a48ea624ba51b6e))
* **truncation_state:** add save_content_truncation compat export ([b07bcc4](https://github.com/ankitcharolia/kiro-gateway/commit/b07bcc42815fa17b3e65432fdd2b13b0c401a88c))
* **streaming_anthropic:** add format_sse_event compat export ([f8b9e07](https://github.com/ankitcharolia/kiro-gateway/commit/f8b9e07a04b3bea77bc32d7d20ce3ea0db15ba48))
* **streaming_core:** add FirstTokenTimeoutError ([a1a0987](https://github.com/ankitcharolia/kiro-gateway/commit/a1a098725843a7377939ef2137ff2b688e27795f))
* **streaming_openai:** add stream_with_first_token_retry ([551556b](https://github.com/ankitcharolia/kiro-gateway/commit/551556b6d0789402f3563596934f620dc8de879d))
* **parsers:** add find_matching_brace compat export ([ba11618](https://github.com/ankitcharolia/kiro-gateway/commit/ba11618c4e8d320795642d0ab2e55ce9f82ad00d))
* **thinking_parser:** add ThinkingParseResult ([5b1052f](https://github.com/ankitcharolia/kiro-gateway/commit/5b1052f1d6ece9668f6022431f336bc8f67480d2))
* **mcp_tools:** add call_kiro_mcp_api compat export ([f0be6f5](https://github.com/ankitcharolia/kiro-gateway/commit/f0be6f51fe90a9cba9a43f99d6beb1a6031adf91))
* **models_openai:** add ChatCompletionRequest, Message, FunctionCall aliases for conftest ([0855069](https://github.com/ankitcharolia/kiro-gateway/commit/08550695a1817cbbaa0ae19daf4a9ce55dc89ddf))
* **models_anthropic:** add TextContentBlock, ToolUseContentBlock aliases for conftest ([6b0b121](https://github.com/ankitcharolia/kiro-gateway/commit/6b0b1210353b6530cbb315fb8c43144335ec38f2))
* **acp_models:** add ACPMessage, ACPThinkingBlock for conftest ([66b23e2](https://github.com/ankitcharolia/kiro-gateway/commit/66b23e2968afa65524eb355488d7e6d91a53608e))
* restore all missing public symbols to pass 19 import errors in CI ([918cf4c](https://github.com/ankitcharolia/kiro-gateway/commit/918cf4c1b7d937342757c3e21757e490adbd4233))
* add missing aliases to resolve all 16 collection-time ImportErrors ([f672b1d](https://github.com/ankitcharolia/kiro-gateway/commit/f672b1db575f47f5f23d7644df85a02dcf1b2b88))
* restore full public APIs to resolve all 26 CI import errors ([62f552d](https://github.com/ankitcharolia/kiro-gateway/commit/62f552de0f19a6a846babcabc79678a184349db3))
* add missing exports to resolve all 12 CI import errors ([bec4600](https://github.com/ankitcharolia/kiro-gateway/commit/bec4600803a0cae6757ddf7827b670f818286fcd))
* add missing aliases across models, mcp_tools, and converters_anthropic to resolve 7 CI import errors ([0d5b578](https://github.com/ankitcharolia/kiro-gateway/commit/0d5b57804fd6aefd15426f8774898741a0b5c049))
* add ChatCompletionUsage alias, extract_system_prompt, generate_anthropic_web_search_sse, CapabilityError to resolve remaining 6 CI import errors ([a377a0a](https://github.com/ankitcharolia/kiro-gateway/commit/a377a0aed809dd748427d40f1d8484297cfb1b6f))
* add 4 missing exports to unblock test collection ([5f98ddb](https://github.com/ankitcharolia/kiro-gateway/commit/5f98ddb8a1b46bc4c347335b8d85c36d3d2b81c0))
* add missing convert_openai_messages_to_unified and related exports ([b87d52e](https://github.com/ankitcharolia/kiro-gateway/commit/b87d52e007ac4f3a824810d4cbe64bedcc49e646))
* widen ACPResponse.content type and add missing test fixtures ([08b011c](https://github.com/ankitcharolia/kiro-gateway/commit/08b011c92ecb298402bf1fbf25cbe93071190127))
* correct app import path in conftest (main.py is at repo root, not kiro.main) ([e0cb1c9](https://github.com/ankitcharolia/kiro-gateway/commit/e0cb1c99a71f98666a203f70dda6cd4a83cf8da8))
* add settings object to config.py so main.py imports resolve ([082fb76](https://github.com/ankitcharolia/kiro-gateway/commit/082fb76219a7f47a4625acf36b2a690f9ce5fc49))
* add ACPChatRequest and ACPChatResponse to acp_models ([ce2d7a8](https://github.com/ankitcharolia/kiro-gateway/commit/ce2d7a802dd6f3c6ed9d87f0229c316e39f300ee))
* mock ACPClient subprocess in integration test_client fixture ([f8458ab](https://github.com/ankitcharolia/kiro-gateway/commit/f8458ab4ae7ec4746cdf5c26d36c698a67ec0c9a))
* add mock_auth_manager fixture and update ModelResolver for testability ([6aa8c07](https://github.com/ankitcharolia/kiro-gateway/commit/6aa8c078c55d8a7186c7230230132bf821aeeae0))

### Refactoring

* improve timeout handling and logging in http_client and streaming ([da0a4de](https://github.com/ankitcharolia/kiro-gateway/commit/da0a4de8dcc38fafa5a099a89e1db2099bb8ee75))
* rename kiro_gateway to kiro ([9a5fa46](https://github.com/ankitcharolia/kiro-gateway/commit/9a5fa4667c8409ac14bfa636be40231bf989fbbb))
* update kiro_gateway naming to kiro ([f1668d0](https://github.com/ankitcharolia/kiro-gateway/commit/f1668d042a71fdc64ac43939eada5b3bc83bdf2a))
* rename OpenAI-specific modules with _openai suffix ([d95b61b](https://github.com/ankitcharolia/kiro-gateway/commit/d95b61b922096b3efc50dd4540a27baffdf23835))
* unify first token retry logic in core layer ([186cd6d](https://github.com/ankitcharolia/kiro-gateway/commit/186cd6d63bc3e1a09801666e589643e23e60f90e))
* **logging:** reduce merge_adjacent_messages log spam ([a1a59c3](https://github.com/ankitcharolia/kiro-gateway/commit/a1a59c3c626bc944fcf3bf5c8c8e2071366bea58))
* **tests:** remove test for logging request body at debug level ([88cfd3e](https://github.com/ankitcharolia/kiro-gateway/commit/88cfd3edd73701fa9bd0ef7276709f270d7d32e3))
* **deps:** migrate manual_api_test.py from requests to httpx ([11cd3f0](https://github.com/ankitcharolia/kiro-gateway/commit/11cd3f04d52c4da4c8b064d84824b91a8ae48d1d))
* **converters:** complete fix for unknown roles with alternating support ([#64](https://github.com/ankitcharolia/kiro-gateway/pull/64)) ([147e08a](https://github.com/ankitcharolia/kiro-gateway/commit/147e08a3273939b47903433259d74063664020af))
* **converters:** use "(empty)" instead of "." for synthetic user message ([58e8129](https://github.com/ankitcharolia/kiro-gateway/commit/58e81299cc39c701665e03cf5f374cfb13df1f42))
* **payload-guard:** improve trim logging message ([364f80f](https://github.com/ankitcharolia/kiro-gateway/commit/364f80fcf9e293b77b9c71b9c586c4b91195e174))
* **errors:** clarify last account error message wording ([a5292ca](https://github.com/ankitcharolia/kiro-gateway/commit/a5292ca04c7c6231e0b47673ac3f981f5a706e1e))
* delete old direct-API backend — all routes now go through ACP only ([eb0e676](https://github.com/ankitcharolia/kiro-gateway/commit/eb0e676fa9f3929c9c0b956136c5943206f56c92))

### Documentation

* Add initial architecture and .gitignore ([9d31962](https://github.com/ankitcharolia/kiro-gateway/commit/9d31962cc28561c60ad723ea95c1976028c31bd0))
* clarify PROXY_API_KEY is user-defined password ([b5b969f](https://github.com/ankitcharolia/kiro-gateway/commit/b5b969f1a44a50fafb4027d13203f46d7baec99f))
* reorder configuration options in README for clarity ([a9a4e1e](https://github.com/ankitcharolia/kiro-gateway/commit/a9a4e1ef372b606ca4c710ab9e9f4dfe8cbaf357))
* add Kiro IDE link to prerequisites ([003d84c](https://github.com/ankitcharolia/kiro-gateway/commit/003d84cf5e85f073a03c2949882cfae81e1c5092))
* update title in ARCHITECTURE.md to remove version number ([9223e07](https://github.com/ankitcharolia/kiro-gateway/commit/9223e0709bd4d9a50da90601214fe912a8d5111a))
* add English translation of ARCHITECTURE.md ([b0850b9](https://github.com/ankitcharolia/kiro-gateway/commit/b0850b955020aa68a306e329f0287018ae654a80))
* update architecture documentation to match codebase ([d709b23](https://github.com/ankitcharolia/kiro-gateway/commit/d709b2372a3c5fe4e09cd677298e9e6359ae2ffb))
* update debugging section with DEBUG_MODE configuration ([cb28c1e](https://github.com/ankitcharolia/kiro-gateway/commit/cb28c1e71c24af0b991681d649b3eee62db73458))
* clarify profileArn not needed for AWS SSO OIDC ([#12](https://github.com/ankitcharolia/kiro-gateway/pull/12)) ([85efa85](https://github.com/ankitcharolia/kiro-gateway/commit/85efa85a6fc64b71d0a786e0d87744269a552f84))
* update prerequisites and credentials section ([5c4fae1](https://github.com/ankitcharolia/kiro-gateway/commit/5c4fae1db9838abbe4d92f9b19d118024ea65da2))
* architecture for Anthropic API support ([#15](https://github.com/ankitcharolia/kiro-gateway/pull/15)) ([687042a](https://github.com/ankitcharolia/kiro-gateway/commit/687042af0185abbe479a91cfe3fe234740600ab4))
* **tests:** add documentation for issue #20 fix tests ([1adb6ba](https://github.com/ankitcharolia/kiro-gateway/commit/1adb6ba8d8957ab41694b95892e2a61fefaa44ac))
* update CONTRIBUTORS.md to include @kilhyeonjun's contributions ([e6fe364](https://github.com/ankitcharolia/kiro-gateway/commit/e6fe364a35afa838c634089724f2264a35396f9e))
* add donation section and GitHub funding config ([230a7a0](https://github.com/ankitcharolia/kiro-gateway/commit/230a7a0af02ea3fd0b067030ef8e395423374a0b))
* clarify git is optional, add ZIP download alternative ([#27](https://github.com/ankitcharolia/kiro-gateway/pull/27)) ([e6ae63f](https://github.com/ankitcharolia/kiro-gateway/commit/e6ae63f200f65304fc8b76a798639d87766971ef))
* **readme:** improve README UX ([0765579](https://github.com/ankitcharolia/kiro-gateway/commit/0765579eafdd65915a3ac416fc12f47620836b03))
* **i18n:** add README translations (ru, zh, es, id, pt, ja, vi, tr, ko) ([d43bf39](https://github.com/ankitcharolia/kiro-gateway/commit/d43bf39d7535cb33faabaea2c7b983cc8812b2c3))
* **i18n:** fix badge anchor links (ru, zh, es, id, pt, ja, vi, tr, ko) ([a8b2494](https://github.com/ankitcharolia/kiro-gateway/commit/a8b24947c84a2ba83f7327abe2c15836a57f068d))
* update model list and add tier-based availability notice ([#39](https://github.com/ankitcharolia/kiro-gateway/pull/39)) ([54e5a46](https://github.com/ankitcharolia/kiro-gateway/commit/54e5a46b1c54484adabf2304e26b02c24950b2bd))
* clarify Enterprise/Builder ID support and add Amazon Q Developer branding ([58c67e0](https://github.com/ankitcharolia/kiro-gateway/commit/58c67e0f46b31b6a15e0cdd8fdbff9369f276f95))
* clarify AWS SSO credentials configuration ([#43](https://github.com/ankitcharolia/kiro-gateway/pull/43)) ([91a02d2](https://github.com/ankitcharolia/kiro-gateway/commit/91a02d2a6bd14abd91b837e12dd27e5b2794a6db))
* **template:** update placeholders in bug report ([324073b](https://github.com/ankitcharolia/kiro-gateway/commit/324073b73b13233cdfd869f4a2ecacf2b5d4c326))
* **contributors:** add @saaj for regional endpoint fix ([#58](https://github.com/ankitcharolia/kiro-gateway/pull/58)) ([fe16356](https://github.com/ankitcharolia/kiro-gateway/commit/fe16356d7dedf0eb0a6e40dc128d8db9e3f423dc))
* **i18n:** add docker deployment section to all translated READMEs ([a51b1b4](https://github.com/ankitcharolia/kiro-gateway/commit/a51b1b4efc9d34b8e14a08045512473834fbf242))
* **contributing:** add project philosophy and focused changes guideline ([274b890](https://github.com/ankitcharolia/kiro-gateway/commit/274b890a9469f7748870af1fd9138415e0195e57))
* add Codex App to supported clients list ([#64](https://github.com/ankitcharolia/kiro-gateway/pull/64)) ([dd7d68f](https://github.com/ankitcharolia/kiro-gateway/commit/dd7d68f8d849845b513669e3bee7f3dca3a5b45c))
* **models:** add DeepSeek-V3.2, MiniMax M2.1, Qwen3-Coder-Next ([8c9d23b](https://github.com/ankitcharolia/kiro-gateway/commit/8c9d23b01892f2754004f84decd1eb07649042b1))
* add payload size guard settings to .env.example ([#73](https://github.com/ankitcharolia/kiro-gateway/pull/73)) ([188bb0a](https://github.com/ankitcharolia/kiro-gateway/commit/188bb0ac4c82410143196abb4dae68b1a2627f07))
* update funding links ([09c028b](https://github.com/ankitcharolia/kiro-gateway/commit/09c028b7056a8be2e73065ba07ec2e0e98d9c87c))
* **agents:** add feature parity and reverse engineering context ([7f95bdf](https://github.com/ankitcharolia/kiro-gateway/commit/7f95bdf622aa1447f66f5088ecc046b78ec1e3e7))
* enforce consistency and quality standards ([85f5e43](https://github.com/ankitcharolia/kiro-gateway/commit/85f5e43112c23ee0852fc02ef7eb5cb6c9c35ef1))
* update README — remove resolved limitations, add capability & tool-call docs ([1d19a08](https://github.com/ankitcharolia/kiro-gateway/commit/1d19a08f4c6fb44122ec4563041ec87fa6cbe018))
* restore PayPal sponsor link to README ([7cc49c0](https://github.com/ankitcharolia/kiro-gateway/commit/7cc49c04e818d3243bd45619ce4ef87bfeef7c8a))
* full README rewrite with compliance architecture, install guide, Docker; add docker-release CI ([d0286ba](https://github.com/ankitcharolia/kiro-gateway/commit/d0286baff3919b6f8122990d179cd32d5c7e2f3a))
* add OpenClaw to all harness references in README ([7374e95](https://github.com/ankitcharolia/kiro-gateway/commit/7374e950f40d9f165b64a1f7fc625ab44481dd82))
* add CI test pass badge to README ([993eac8](https://github.com/ankitcharolia/kiro-gateway/commit/993eac8a3bf736f6712df75da3dd301fdba0460c))
* add Buy Me a Coffee badge to README ([c800cb7](https://github.com/ankitcharolia/kiro-gateway/commit/c800cb7658d69b1c12e66a517b8063bae5769c83))

### Testing

* **core:** add coverage for streaming retry and tool stripping ([6b13314](https://github.com/ankitcharolia/kiro-gateway/commit/6b13314365376645767c0e186ef8c35d519d6460))
* **models:** add comprehensive Pydantic model validation tests ([3fa4c6a](https://github.com/ankitcharolia/kiro-gateway/commit/3fa4c6a9b07b79caa8a85c9c4d93d7fd76642c90))
* **auth:** update api_host test for new q.{region}.amazonaws.com endpoint ([dc3f5b6](https://github.com/ankitcharolia/kiro-gateway/commit/dc3f5b6c9d232339b7d893c6cea0cbb4a2cdaeb6))
* **account-system:** add comprehensive test suite and fix critical bugs ([#93](https://github.com/ankitcharolia/kiro-gateway/pull/93)) ([04cc949](https://github.com/ankitcharolia/kiro-gateway/commit/04cc94926d1778ba8ebd2c4233532d429f0046ad))
* replace old direct-API tests with ACP compliance + gateway behaviour test suite ([90bdbb3](https://github.com/ankitcharolia/kiro-gateway/commit/90bdbb376bacf73085670a9e63af79097685d69a))

### CI/CD & Build

* **docker:** replace runtime tests with structure tests ([d63f35f](https://github.com/ankitcharolia/kiro-gateway/commit/d63f35f6f07a3f5f58c18e3d892cf687c50950e8))
* make GHCR image public via org.opencontainers labels + package visibility ([e995b83](https://github.com/ankitcharolia/kiro-gateway/commit/e995b8378b8cb19082a9d0d96a66f1b89b45cd6d))
* pin matrix to Python 3.12 only (matches Dockerfile runtime) ([efa05d1](https://github.com/ankitcharolia/kiro-gateway/commit/efa05d13da1d7ee688fe6668e8621ddc5df9c5a1))

### Dependencies

* **deps:** update actions/checkout action to v6 ([3ed3c0b](https://github.com/ankitcharolia/kiro-gateway/commit/3ed3c0b6d2be5c65ffc03a9b5807b4fbd7b264a5))
* **deps:** update dependency python ([a17fb10](https://github.com/ankitcharolia/kiro-gateway/commit/a17fb10d5ea01197b8330a784e5b58012bbd0324))
* **deps:** update actions/setup-python action to v6 ([e9bb588](https://github.com/ankitcharolia/kiro-gateway/commit/e9bb588b7193d435be47b9e75dc4368499a74cb8))
* **deps:** update docker/build-push-action action to v7 ([d0c09ea](https://github.com/ankitcharolia/kiro-gateway/commit/d0c09ea8d650ed90d9f011311df4580fd5062dc2))

### Chores

* bump version to 1.0.3, centralize version constant ([26df641](https://github.com/ankitcharolia/kiro-gateway/commit/26df641ccddd837e5c7247fea23e32952c58d466))
* bump application version to 1.0.5 ([e687d2a](https://github.com/ankitcharolia/kiro-gateway/commit/e687d2ac640aa60ab706dcb47932405e46804243))
* bump application version to 1.0.6 ([a0da215](https://github.com/ankitcharolia/kiro-gateway/commit/a0da215600c24c31f3e291e0915c9b279b6f543c))
* add CLA signature for Kartvya69 ([3a06f86](https://github.com/ankitcharolia/kiro-gateway/commit/3a06f861ac225276a92a7a200a012bb08a100be8))
* bump version to 1.0.8 ([d43d494](https://github.com/ankitcharolia/kiro-gateway/commit/d43d494cdfbd418ab66c833e240c0b3da45d51f0))
* **i18n:** translate Russian comments and docstrings to English ([e262a21](https://github.com/ankitcharolia/kiro-gateway/commit/e262a21f4dd5d9eab17bbef29c93f4c6fd75ffdb))
* rename project to kiro-gateway ([57d29a3](https://github.com/ankitcharolia/kiro-gateway/commit/57d29a34642e0d4db0188b3d70257f92d8538578))
* update contributors list in CLA ([83203bf](https://github.com/ankitcharolia/kiro-gateway/commit/83203bfe3ed76966db08a5efd187edda43d23892))
* **log:** use INFO level for Kiro Desktop auth type ([b32ab04](https://github.com/ankitcharolia/kiro-gateway/commit/b32ab0465dfbd88a190a08b255f619e137a1c181))
* add debug log before sending request to Kiro API ([a25f73e](https://github.com/ankitcharolia/kiro-gateway/commit/a25f73eb280e4e50e296346f8b89a21d5738e686))
* **cla:** update contributors ([9dec9d9](https://github.com/ankitcharolia/kiro-gateway/commit/9dec9d9fa46c1983161a53baa88234a77fa52d70))
* **config:** remove legacy debug settings and startup warnings ([1be86cc](https://github.com/ankitcharolia/kiro-gateway/commit/1be86cc0c5cb83b4eb878be51680c5f0c0bc275d))
* bump version to 2.2 ([9040b53](https://github.com/ankitcharolia/kiro-gateway/commit/9040b535183becc2216e67adf4a24fb8ee123e3b))
* **contributors:** update contributors ([99b3d11](https://github.com/ankitcharolia/kiro-gateway/commit/99b3d11effc67fb37d112504869a59fa1b66f0f4))
* **contributors:** update contributors ([73715b4](https://github.com/ankitcharolia/kiro-gateway/commit/73715b4eda33350eeeb81f2e0afef6ed73193b05))
* bump version to 2.3 ([8bf3e88](https://github.com/ankitcharolia/kiro-gateway/commit/8bf3e88f85be10e2737f4b9324b6934272c47969))
* **cla:** update contributors ([31fb8e7](https://github.com/ankitcharolia/kiro-gateway/commit/31fb8e70921cca4a703dd16ff9d96d0485c03ae7))
* **cla:** update contributors ([6ada76c](https://github.com/ankitcharolia/kiro-gateway/commit/6ada76caa4fee21348d462c511733a2446a9209d))
* **cla:** update contributors ([e6f23c2](https://github.com/ankitcharolia/kiro-gateway/commit/e6f23c22fc5e9aa7a22e4c31af56cdc6f859afbd))
* **contributors:** recognize core contributors ([df9c296](https://github.com/ankitcharolia/kiro-gateway/commit/df9c2967b59efd6c081af1d361ba584ece2c916d))
* **cla:** update contributors ([8c8f1a1](https://github.com/ankitcharolia/kiro-gateway/commit/8c8f1a1da59c048486ba953e8ddaa7581ac896b6))
* add license headers and update contributors ([#73](https://github.com/ankitcharolia/kiro-gateway/pull/73)) ([35ee7ec](https://github.com/ankitcharolia/kiro-gateway/commit/35ee7ec22e07ef2cbe222c25dd4969826ad948a9))
* **cla:** update contributors ([5e9fd6d](https://github.com/ankitcharolia/kiro-gateway/commit/5e9fd6d21e6caca0278378e6e310bb9b7feacf40))
* **cla:** update contributors ([1a46d68](https://github.com/ankitcharolia/kiro-gateway/commit/1a46d6811c30958b22702393a41368f071453298))
* improve code documentation and remove unnecessary type counting ([#135](https://github.com/ankitcharolia/kiro-gateway/pull/135)) ([a709f57](https://github.com/ankitcharolia/kiro-gateway/commit/a709f57dc272c2bea58618d0b51f4b167511583c))
* **cla:** update contributors ([7c90917](https://github.com/ankitcharolia/kiro-gateway/commit/7c90917caf44be5eacdb79334dddf2652d2d4405))
* **cla:** update contributors ([52cef00](https://github.com/ankitcharolia/kiro-gateway/commit/52cef00b235b07862650ca2510b5f1b5c1eece3d))
* **contributors:** update list ([b129f5b](https://github.com/ankitcharolia/kiro-gateway/commit/b129f5beb50b218978737bc459e374765c536c09))
* **cla:** update list ([1a811e3](https://github.com/ankitcharolia/kiro-gateway/commit/1a811e31bc1f226dbe171b6ff7fa09350e77a8bd))
* bump version to 2.4-dev.10 ([d2644d2](https://github.com/ankitcharolia/kiro-gateway/commit/d2644d2d6f82a92a701fa86bc1b8deaecaa9a278))
* **contributors:** update list ([1940c36](https://github.com/ankitcharolia/kiro-gateway/commit/1940c361842e95d6a1766802d26c70ff3eab681d))
* **cla:** update list ([30561e2](https://github.com/ankitcharolia/kiro-gateway/commit/30561e2c3759493cf2bab2c4eead0d3e961cf7ce))
* **cla:** update list ([0398d74](https://github.com/ankitcharolia/kiro-gateway/commit/0398d74f15549bd771480da8fceb21916ce333e5))
* **cla:** update list ([cfa7c58](https://github.com/ankitcharolia/kiro-gateway/commit/cfa7c582ed0a926d69de25abdf70e5ad80c713d6))
* bump version to 2.4 ([6544d1f](https://github.com/ankitcharolia/kiro-gateway/commit/6544d1fac58325456c88066e4cd0e08753bc142e))
* remove redundant flat test (superseded by tests/unit/) ([8f846e8](https://github.com/ankitcharolia/kiro-gateway/commit/8f846e87dbbf79a0b2be21c07f72732f0b853ea3))
* remove redundant flat test (superseded by tests/unit/) ([84af498](https://github.com/ankitcharolia/kiro-gateway/commit/84af498d7ba94777e2fda770e2bbbe535ee25d71))
* remove redundant flat test (superseded by tests/unit/) ([d0c1b4e](https://github.com/ankitcharolia/kiro-gateway/commit/d0c1b4ed50a6c7278982bec260b500d910f0128c))
* remove redundant flat test (superseded by tests/unit/) ([ed4ced3](https://github.com/ankitcharolia/kiro-gateway/commit/ed4ced3cee98831ac2c0fdcc981223a246fea012))
* remove redundant flat test (superseded by tests/unit/) ([cde8e50](https://github.com/ankitcharolia/kiro-gateway/commit/cde8e50efbf631a7b5a822ebdac453a99b704776))
* remove redundant flat test (superseded by tests/unit/) ([242ab12](https://github.com/ankitcharolia/kiro-gateway/commit/242ab12b3e44e58df07262cd107fac54e17e9639))
* replace Jwadow with ankitcharolia as maintainer ([9dbfc03](https://github.com/ankitcharolia/kiro-gateway/commit/9dbfc03338885c94f34aa0858dcbfb423c255ac1))

### Other

* enforce single-account mode, disable multi-account failover ([e0a1948](https://github.com/ankitcharolia/kiro-gateway/commit/e0a194807cd6657f4f2a77bc4677bb911c46bdd8))
* strip credentials.json.example to single-account patterns only ([76cfd38](https://github.com/ankitcharolia/kiro-gateway/commit/76cfd3868262aa89ebbc14d84377b8bac614a40d))
* update README to remove multi-account promotion ([7848a58](https://github.com/ankitcharolia/kiro-gateway/commit/7848a58eb6f885f6f5e819ca8108d20700aafdd3))


