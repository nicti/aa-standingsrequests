# Change Log

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](http://keepachangelog.com/)
and this project adheres to [Semantic Versioning](http://semver.org/).

## [Unreleased] - yyyy-mm-dd

### Added

### Changed

### Fixed

## [0.3.8] - 2020-01-15

### Fixed

- AA title and side menu showed twice in browser during installation ([#10](https://gitlab.com/basraah/standingsrequests/issues/10))

## [0.3.7] - 2020-01-15

### Added

- CI/CD setup with 1st batch of unit tests

### Fixed

- Fixing of minor bugs found by unit tests

## [0.3.6] - 2020-01-13

### Fixed

- Error 500 when trying to add token during installation for the first time ([#9](https://gitlab.com/basraah/standingsrequests/issues/9))

## [0.3.5] - 2019-10-12

### Added

- Standing requests for corporation can now be disabled via setting. Disabling it hugely improves performance and load times of requests pages ([#6](https://gitlab.com/basraah/standingsrequests/issues/6))

- Added Spinners to all pages, that load data asynchronously, which improves user experience

### Changed

- Requests page: Characters and corporations are now loaded asynchronously and a spinner is shown which improves user experience ([#6](https://gitlab.com/basraah/standingsrequests/issues/6))

- Now gives clear feedback if tables are empty, e.g. if they are no requests to manage. Before it was often unclear if a table was empty or still loading.

- Improved installation instructions in README
