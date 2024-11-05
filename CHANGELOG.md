# Change Log
All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](http://keepachangelog.com/) and this project adheres to [Semantic Versioning](http://semver.org/).


## v3.2.0 - 2024-11-05
### What's Changed
**Full Changelog**: https://github.com/obervinov/pyinstabot-downloader/compare/v3.1.3...v3.2.0 by @obervinov in https://github.com/obervinov/pyinstabot-downloader/pull/116
#### 🐛 Bug Fixes
* fix conflict between device metadata and user-agent in the `Downloader()` class
* fix the login strategy for exceptions
#### 💥 Breaking Changes
* `Downloader()` configuration has been changed. Please, check the new parameters in [README.md](README.md#bot-configuration-source-and-supported-parameters) and update Vault configuration
#### 🚀 Features
* add validator of settings between the config and session in the `Downloader()` class


## v3.1.3 - 2024-11-01
### What's Changed
**Full Changelog**: https://github.com/obervinov/pyinstabot-downloader/compare/v3.1.2...v3.1.3 by @obervinov in https://github.com/obervinov/pyinstabot-downloader/pull/115
#### 🐛 Bug Fixes
* remove the conflicting `_check_incomplete_transfers()` method with the queue processing thread from the `Uploader()` class - this is a deprecated mechanism
* rewrite the exception handling in the `Downloader()` class
* add exception handling for the `ChallengeRequired` in the `Downloader()` class
* other small improvements


## v3.1.2 - 2024-10-28
### What's Changed
**Full Changelog**: https://github.com/obervinov/pyinstabot-downloader/compare/v3.1.1...v3.1.2 by @obervinov in https://github.com/obervinov/pyinstabot-downloader/pull/114
#### 🐛 Bug Fixes
* general bug fixes and improvements
* add additional exception handling for the `Downloader()` class


## v3.1.1 - 2024-10-24
### What's Changed
**Full Changelog**: https://github.com/obervinov/pyinstabot-downloader/compare/v3.1.0...v3.1.1 by @obervinov in https://github.com/obervinov/pyinstabot-downloader/pull/113
#### 📚 Documentation
* [Bug: Update python version in README](https://github.com/obervinov/pyinstabot-downloader/issues/112)
#### 🐛 Bug Fixes
* add support for instagram's new link format (with post owner name)


## v3.1.0 - 2024-10-23
### What's Changed
**Full Changelog**: https://github.com/obervinov/pyinstabot-downloader/compare/v3.0.0...v3.1.0 by @obervinov in https://github.com/obervinov/pyinstabot-downloader/pull/111
#### 🚀 Features
* bump workflows to `2.0.2`
* bump dependencies versions
#### 💥 Breaking Changes
* bump python version to `3.12`
#### 🐛 Bug Fixes
* other general bug fixes and improvements
* fix not enough condition for `igtv` type of content for `Downloader()` class
* fix infinite loop in the `Downloader()` class when type of content not supported in condition
* [Bug: Do not start the release creation process when closing a PR](https://github.com/obervinov/pyinstabot-downloader/issues/104)
* [Bug: The application tries to use credentials to access the database that have already expired](https://github.com/obervinov/pyinstabot-downloader/issues/105)


## v3.0.0 - 2024-10-09
### What's Changed
**Full Changelog**: https://github.com/obervinov/pyinstabot-downloader/compare/v2.3.0...v3.0.0 by @obervinov in https://github.com/obervinov/pyinstabot-downloader/pull/102
#### 💥 Breaking Changes
* replacement of [instaloder](https://github.com/instaloader/instaloader) module with [instagrapi](https://github.com/subzeroid/instagrapi) module
* function with the `proxy' configuration has been moved to Vault
* remove the outdated storage types: `Dropbox` and `Mega` (Support for individual cloud providers removed in favour of `webdav` compatible providers)
* change of parameter configuration for `downloader-api` and `uploader-api` in the Vault. Please, check the new parameters in [README.md](README.md#bot-configuration-source-and-supported-parameters)
#### 🚀 Features
* replacement of [instaloder](https://github.com/instaloader/instaloader) module with [instagrapi](https://github.com/subzeroid/instagrapi) module
* replace the base image of project with `python:3.9.20` (Ubuntu instead of Alpine)


## v2.3.0 - 2024-10-04
### What's Changed
**Full Changelog**: https://github.com/obervinov/pyinstabot-downloader/compare/v2.2.1...v2.3.0 by @obervinov in https://github.com/obervinov/pyinstabot-downloader/pull/95
#### 💥 Breaking Changes
* now all user data is stored in the database
* psql credentials are now written out via Vault Database Engine
#### 🚀 Features
* bump workflow version to `1.2.9`
* bump vault-package to major version `3.0.0`
* bump users-package to major version `3.0.2`
* bump telegram-package to major version `2.0.1`
* add tests for database and metrics modules
* add proxy support for all dependencies with `requests` library
* [Switch reading of the database connection configuration to db engine](https://github.com/obervinov/pyinstabot-downloader/issues/33)
#### 🐛 Bug Fixes
* general bug fixes and improvements


## v2.2.1 - 2024-08-24
### What's Changed
**Full Changelog**: https://github.com/obervinov/pyinstabot-downloader/compare/v2.2.0...v2.2.1 by @obervinov in https://github.com/obervinov/pyinstabot-downloader/pull/94
#### 🐛 Bug Fixes
* [Bug: Correct the exception Cursor already close](https://github.com/obervinov/pyinstabot-downloader/issues/93)
* [Bug: Display the state of all additional bot threads in prometheus metrics](https://github.com/obervinov/pyinstabot-downloader/issues/92)


## v2.2.0 - 2024-08-20
### What's Changed
**Full Changelog**: https://github.com/obervinov/pyinstabot-downloader/compare/v2.1.8...v2.2.0 by @obervinov in https://github.com/obervinov/pyinstabot-downloader/pull/90
#### 🐛 Bug Fixes
* [Bug: Add validation of the received card from the database with a message queue](https://github.com/obervinov/pyinstabot-downloader/issues/86)
* [Bug: More than one status_message message registered in the database per user](https://github.com/obervinov/pyinstabot-downloader/issues/85)
* [Bug: Add a version to block the update of the user widget when the bot is launched](https://github.com/obervinov/pyinstabot-downloader/issues/84)
* [Bug: Invalid `help_for_reschedule_queue` message template](https://github.com/obervinov/pyinstabot-downloader/issues/83)
* [Bug: Error: cursor already closed](https://github.com/obervinov/pyinstabot-downloader/issues/82)
* [Bug: For some reason the bot tried to edit a message with the same content in the message](https://github.com/obervinov/pyinstabot-downloader/issues/65)
#### 🚀 Features
* bump workflow version to `1.2.8`
* [Feature request: Add support for `WebDav` as target storage](https://github.com/obervinov/pyinstabot-downloader/issues/81)
* [Prometheus metric support](https://github.com/obervinov/pyinstabot-downloader/issues/53)
* [Feature request: Add a bash script to configure vault and postgresql to the repository](https://github.com/obervinov/pyinstabot-downloader/issues/66)
* Add GH Actions Job for cleanup untagged images


## v2.1.8 - 2024-07-14
### What's Changed
**Full Changelog**: https://github.com/obervinov/pyinstabot-downloader/compare/v2.1.7...v2.1.8 by @obervinov in https://github.com/obervinov/pyinstabot-downloader/pull/80
#### 🐛 Bug Fixes
* [Bug: Incorrect name of the message template `wrong_reschedule_queue` causes a drop in the processing thread of incoming messages ](https://github.com/obervinov/pyinstabot-downloader/issues/75)
#### 🚀 Features
* Bump dependency versions for modules
* [Feature request: Replace separator for queue reschedule](https://github.com/obervinov/pyinstabot-downloader/issues/79)
* [Feature request: Add additional statistics on the user's widget](https://github.com/obervinov/pyinstabot-downloader/issues/78)


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
