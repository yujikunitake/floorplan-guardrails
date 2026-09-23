# Changelog

## [1.1.5](https://github.com/yujikunitake/floorplan-guardrails/compare/v1.1.4...v1.1.5) (2026-09-23)


### Continuous Integration

* **repo:** show every change type in the changelog ([#27](https://github.com/yujikunitake/floorplan-guardrails/issues/27)) ([ab98d3d](https://github.com/yujikunitake/floorplan-guardrails/commit/ab98d3d02d31ae75b0f8cd094d55c3635c01475e))

## [1.1.4](https://github.com/yujikunitake/floorplan-guardrails/compare/v1.1.3...v1.1.4) (2026-09-23)


### Bug Fixes

* **notebook:** correct the size and time the student is promised ([#24](https://github.com/yujikunitake/floorplan-guardrails/issues/24)) ([7d7bd1d](https://github.com/yujikunitake/floorplan-guardrails/commit/7d7bd1d7ff2aa2f6b0c832c0fcc141d6981f66a9))


### Documentation

* **eval:** report the comparative round and its noise measurement ([#23](https://github.com/yujikunitake/floorplan-guardrails/issues/23)) ([c10bf09](https://github.com/yujikunitake/floorplan-guardrails/commit/c10bf097eaf3423abaa14080f5703381c458bcde))
* **notebook:** make the size provocation fail and say why ([#26](https://github.com/yujikunitake/floorplan-guardrails/issues/26)) ([2b4c83a](https://github.com/yujikunitake/floorplan-guardrails/commit/2b4c83a385f2d13fac483560dcbd32b86f0df609))

## [1.1.3](https://github.com/yujikunitake/floorplan-guardrails/compare/v1.1.2...v1.1.3) (2026-09-23)


### Bug Fixes

* **rules:** state how far each source was verified ([#21](https://github.com/yujikunitake/floorplan-guardrails/issues/21)) ([686fe4a](https://github.com/yujikunitake/floorplan-guardrails/commit/686fe4ab6043eca9755ccb1d442815c680fa96d4))

## [1.1.2](https://github.com/yujikunitake/floorplan-guardrails/compare/v1.1.1...v1.1.2) (2026-09-23)


### Bug Fixes

* **rules:** cite each source and use the nbr bathroom width ([#18](https://github.com/yujikunitake/floorplan-guardrails/issues/18)) ([0ee912a](https://github.com/yujikunitake/floorplan-guardrails/commit/0ee912a4c9a789355a549124e3155f304da6f03f))

## [1.1.1](https://github.com/yujikunitake/floorplan-guardrails/compare/v1.1.0...v1.1.1) (2026-09-21)


### Bug Fixes

* **generator:** accept any endpoint url the azure portal shows ([#15](https://github.com/yujikunitake/floorplan-guardrails/issues/15)) ([9d6234d](https://github.com/yujikunitake/floorplan-guardrails/commit/9d6234dc03f1bd14a6e5f470a890dc12b0ff5869))

## [1.1.0](https://github.com/yujikunitake/floorplan-guardrails/compare/v1.0.0...v1.1.0) (2026-09-21)


### Features

* **validator:** require at least one bathroom ([#12](https://github.com/yujikunitake/floorplan-guardrails/issues/12)) ([99bcf65](https://github.com/yujikunitake/floorplan-guardrails/commit/99bcf6540ccd9d249d8b76d804871b0ad71df6c7))

## 1.0.0 (2026-09-21)


### Features

* **eval:** add the evaluation harness and its report ([0b80535](https://github.com/yujikunitake/floorplan-guardrails/commit/0b80535f74498f42fb7696c4816b01235af1c97d))
* **generator:** add the maf agent with strict structured output ([37713c2](https://github.com/yujikunitake/floorplan-guardrails/commit/37713c250264bfe8c32ce1ab3320d3d4397066a4))
* **geometry:** add wall segments and overlap in pure python ([61fb4f8](https://github.com/yujikunitake/floorplan-guardrails/commit/61fb4f8af719169315e310ef11b3e9fbfe63450f))
* **loop:** add the correction loop and the jsonl run log ([80d9c7b](https://github.com/yujikunitake/floorplan-guardrails/commit/80d9c7bfad5de5ff5f119570e4b617c983193919))
* **notebook:** add the workshop notebook ([6f969eb](https://github.com/yujikunitake/floorplan-guardrails/commit/6f969ebf94072132d0f886cb172b75af9a0e00dd))
* **renderer:** draw plans and the iteration history ([5a7733d](https://github.com/yujikunitake/floorplan-guardrails/commit/5a7733d4ec2a4bd76953b1068f6d657245dc09cd))
* **rules:** add yaml ruleset loader with clear errors ([c2b22ba](https://github.com/yujikunitake/floorplan-guardrails/commit/c2b22ba4632826522d06c00bdc5597141f359070))
* **schema:** add pydantic models for the floor plan ([2782d8b](https://github.com/yujikunitake/floorplan-guardrails/commit/2782d8bb9c10025b7a3e205951a7fcced7a03ad6))
* **validator:** check every rule and report all violations ([b7c3fb5](https://github.com/yujikunitake/floorplan-guardrails/commit/b7c3fb5a08da917780428c1d8c12858e6f85f8d3))


### Bug Fixes

* **ci:** pin setup-uv to a published version tag ([a8fdb65](https://github.com/yujikunitake/floorplan-guardrails/commit/a8fdb655f961d3d61d2e2bb09fc5999b91af29f8))
