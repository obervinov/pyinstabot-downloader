# Change Log
All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](http://keepachangelog.com/) and this project adheres to [Semantic Versioning](http://semver.org/).


## v2.1.0 - 2024-05-24
### What's Changed
**Full Changelog**: https://github.com/obervinov/pyinstabot-downloader/compare/v2.0.0...v2.1.0 by @obervinov in https://github.com/obervinov/pyinstabot-downloader/pull/37
#### 🐛 Bug Fixes
* [GitHub Actions: delete redundant jobs in the main branch b to make workflow more logical](https://github.com/obervinov/pyinstabot-downloader/issues/23)
#### 📚 Documentation
* [Update documentation release/v2.1.0](https://github.com/obervinov/pyinstabot-downloader/issues/26)
* Update repository issues template
#### 💥 Breaking Changes
* Add `PostgreSQL` support to the bot stack (instead of `Vault`). All bot data except `configurations` and `user data` is now stored in the database.
* Remove outdated method for processing full account data per link of `user profile`.
* Move all configuration of components form `environment variables` to the `Vault`.
#### 🚀 Features
* [Change the structure of the secret configurations in Vault](https://github.com/obervinov/pyinstabot-downloader/issues/54)
* [A new concept for processing input messages](https://github.com/obervinov/pyinstabot-downloader/issues/32)
* [Add PostgreSQL support to the bot stack](https://github.com/obervinov/pyinstabot-downloader/issues/30)
* [Add support env files in docker compose](https://github.com/obervinov/pyinstabot-downloader/issues/28)
* [Extend users attributes and add automatic rate limit control](https://github.com/obervinov/pyinstabot-downloader/issues/14)
* [Add the method for processing multiline messages](https://github.com/obervinov/pyinstabot-downloader/issues/20)
* [Rollback to old environment variable names PB_VAULT_APPROLE_ID PB_VAULT_APPROLE_SECRETID](https://github.com/obervinov/pyinstabot-downloader/issues/27)
* [Move parameter `session` to the vault configuration](https://github.com/obervinov/pyinstabot-downloader/issues/24)


## v2.0.0 - 2023-09-16
### What's Changed
**Full Changelog**: https://github.com/obervinov/pyinstabot-downloader/compare/v1.0.1...v2.0.0 by @obervinov in https://github.com/obervinov/pyinstabot-downloader/pull/7

In this release, the approach with issue and github project was implemented already at the very last stages of release preparation, so:
- issue contains a list of mixed issues
- these issue are duplicated in the readme sections
#### 🐛 Bug Fixes
* [Update dependencies: 2023.06.13](https://github.com/obervinov/pyinstabot-downloader/issues/6)
* [Update the project code and fix bugs](https://github.com/obervinov/pyinstabot-downloader/issues/13)
* [Redundant login and password reading from vault](https://github.com/obervinov/pyinstabot-downloader/issues/16)
* [The status is "None" when an exception occurred when uploading to mega, and the retry method](https://github.com/obervinov/pyinstabot-downloader/issues/15)
#### 📚 Documentation
* [Update project repository: 2023.06.13](https://github.com/obervinov/pyinstabot-downloader/issues/8)
#### 💥 Breaking Changes
* [Update dependencies: 2023.06.13](https://github.com/obervinov/pyinstabot-downloader/issues/6)
* [Update the project code and fix bugs](https://github.com/obervinov/pyinstabot-downloader/issues/13)
#### 🚀 Features
* [Update dependencies: 2023.06.13](https://github.com/obervinov/pyinstabot-downloader/issues/6)
* [Added the support GitHub Actions](https://github.com/obervinov/pyinstabot-downloader/issues/10)
* [Update project repository: 2023.06.13](https://github.com/obervinov/pyinstabot-downloader/issues/8)
* [Update the project code and fix bugs](https://github.com/obervinov/pyinstabot-downloader/issues/13)
* [Check the download history for the specified post](https://github.com/obervinov/pyinstabot-downloader/issues/17)


## v1.0.1 - 2022-11-06
### What's Changed
**Full Changelog**: https://github.com/obervinov/pyinstabot-downloader/compare/v1.0.0...v1.0.1
#### 📚 Documentation
* updated the documentation in the file [README.md](https://github.com/obervinov/pyinstabot-downloader/blob/main/README.md) and changed license to `MIT` by @obervinov in https://github.com/obervinov/pyinstabot-downloader/pull/2 and https://github.com/obervinov/pyinstabot-downloader/pull/3
#### 🚀 Features
* added `flake8` and fixed warnings by @obervinov in https://github.com/obervinov/pyinstabot-downloader/pull/1



## v1.0.0 - 2022-11-05
### What's Changed
**Full Changelog**: https://github.com/obervinov/pyinstabot-downloader/commits/v1.0.0
#### 💥 Breaking Changes
* project release
