# Change Log
All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](http://keepachangelog.com/) and this project adheres to [Semantic Versioning](http://semver.org/).

## v2.1.7 - 2024-06-25
### What's Changed
**Full Changelog**: https://github.com/obervinov/pyinstabot-downloader/compare/v2.1.6...v2.1.7 by @obervinov in https://github.com/obervinov/pyinstabot-downloader/pull/74
#### 🐛 Bug Fixes
* fix exception when the post_id not found in the instagram content sources


## v2.1.6 - 2024-06-22
### What's Changed
**Full Changelog**: https://github.com/obervinov/pyinstabot-downloader/compare/v2.1.5...v2.1.6 by @obervinov in https://github.com/obervinov/pyinstabot-downloader/pull/70
#### 💥 Breaking Changes
* remove unused database `environment` attribute (permanent path in the Vault: `configurations/database`)
* remove unused environment variable `PROJECT_ENVIRONMENT`
* the automatic queue verification mechanism has been removed. Instead of this method, added functionality to update the queue processing time via a message to the bot
* change the structure of the table `messages`: add a new column `state` and `updated_at`, rename column `timestamp` to `created_at`
#### 🐛 Bug Fixes
* [Bug: Add a limit on the number of items in the queue to be displayed in the `Your last activity` message](https://github.com/obervinov/pyinstabot-downloader/issues/69)
* [Bug: Bot can't update status message](https://github.com/obervinov/pyinstabot-downloader/issues/62)
* [Bug: Crashes the queue processing thread when a post from the queue no longer exists in the content sources](https://github.com/obervinov/pyinstabot-downloader/issues/67)
* [Bug: queue rescheduler does not always work correctly](https://github.com/obervinov/pyinstabot-downloader/issues/64)
* [Bug: For some reason the bot tried to edit a message with the same content in the message](https://github.com/obervinov/pyinstabot-downloader/issues/65)
* Removed duplicates in rights checking
* Small refactoring code
#### 🚀 Features
* Bump dependency versions for modules and workflows
* Add button for rescheduling the queue


## v2.1.5 - 2024-05-29
### What's Changed
**Full Changelog**: https://github.com/obervinov/pyinstabot-downloader/compare/v2.1.4...v2.1.5 by @obervinov in https://github.com/obervinov/pyinstabot-downloader/pull/61
#### 🐛 Bug Fixes
* [Fix workflow for build docker images](https://github.com/obervinov/pyinstabot-downloader/pull/61)


## v2.1.4 - 2024-05-29
### What's Changed
**Full Changelog**: https://github.com/obervinov/pyinstabot-downloader/compare/v2.1.3...v2.1.4 by @obervinov in https://github.com/obervinov/pyinstabot-downloader/pull/60
#### 🐛 Bug Fixes
* [Fix workflow for build image per `tag` and `main` branch](https://github.com/obervinov/pyinstabot-downloader/pull/60)


## v2.1.3 - 2024-05-29
### What's Changed
**Full Changelog**: https://github.com/obervinov/pyinstabot-downloader/compare/v2.1.2...v2.1.3 by @obervinov in https://github.com/obervinov/pyinstabot-downloader/pull/59
#### 🐛 Bug Fixes
* [Fix workflow for build image per tag](https://github.com/obervinov/pyinstabot-downloader/pull/59)


## v2.1.2 - 2024-05-29
### What's Changed
**Full Changelog**: https://github.com/obervinov/pyinstabot-downloader/compare/v2.1.1...v2.1.2 by @obervinov in https://github.com/obervinov/pyinstabot-downloader/pull/55
#### 🚀 Features
* [Bump dropbox from 11.36.2 to 12.0.0](https://github.com/obervinov/pyinstabot-downloader/pull/55)


## v2.1.1 - 2024-05-29
### What's Changed
**Full Changelog**: https://github.com/obervinov/pyinstabot-downloader/compare/v2.1.0...v2.1.1 by @obervinov in https://github.com/obervinov/pyinstabot-downloader/pull/58
#### 🐛 Bug Fixes
* [Fix code scanning alert - pypa-setuptools: Regular Expression Denial of Service (ReDoS) in package_index.py](https://github.com/obervinov/pyinstabot-downloader/issues/57)
* [Fix code scanning alert - pypa-setuptools: Regular Expression Denial of Service (ReDoS) in package_index.py](https://github.com/obervinov/pyinstabot-downloader/issues/56)


## v2.1.0 - 2024-05-28
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
