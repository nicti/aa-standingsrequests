# Change Log

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](http://keepachangelog.com/)
and this project adheres to [Semantic Versioning](http://semver.org/).

## [Unreleased] - yyyy-mm-dd

## [0.7.2] - 2021-05-10

### Fixed

- Corporations can not be disabled with global flag

## [0.7.1] - 2021-05-10

### Changed

- Reduced page load times for all pages

### Fixed

- Spinner now has correct colors in dark mode

## [0.7.0] - 2021-02-21

> **Update notes:** Please apply updated settings for all peridoc tasks to your local settings file in order to avoid unnecessary task spamming.

### Added

- It's now possible again to copy the name of characters to the clipboard with one click

### Changed

- Now automatically redirects managers to manage page if there are open requests
- Removed support for Django 2.2 & 3.0
- Migrated to allianceauth-app-utils
- Improved protection against transaction timeouts

### Fixed

- Some periodic tasks where called too often due an incorrect configuration

### [0.6.2] - 2020-09-22

### Changes

- Enable compatibility with Django 3
- Added Django 3 to test matrix

### Fixed

- No longer possible to click "Apply" when a character does not have the requested scoped

### [0.6.1] - 2020-09-21

### Added

- Now also shows a badge with the number of pending requests on the "Manager Request" menu

### Changed

- Removed dependency conflict with Auth regarding Django 3
- Removed `staticfile` compatibility issues with Django 3 from templates

Thank you Ariel Rin for your contribution!

### [0.6.0] - 2020-09-17

### Added

- Now shows a badge in the side menu with the number of pending requests to standing managers (requires Alliance Auth 2.8+)

### [0.5.3] - 2020-07-29

### Fixes

- Character name in revocations where hard to read in dark mode
- Minor bugfixes

### [0.5.2] - 2020-07-28

### Fixes

- Another internal error on "Manage requests" page and Revocations is not loading.

### [0.5.1] - 2020-07-28

### Fixes

- Internal error on "Manage requests" page and Revocations is not loading.

### [0.5.0] - 2020-07-22

This release is a big overhaul with many changes including new functionality and changes to the UI.

#### Please read before upgrading

- Please make sure you do not have any pending standing requests or pending standing revocations before updating to this version (e.g. manage requests page should be empty.)
- The app will now automatically sync in-game standing with Auth for all known alts. This means that: <br>a) users who already have standing in-game no longer need to request it.<br>b) app will automatically suggest to revoke a standing if an alt has standing in-game, but does not meet the requirements (e.g. scopes / permission) on Auth.<br>Note that you can deactivate this behavior through settings should you prefer to sync standings manually.
- The name of the periodic task `standings_requests.validate_standings_requests` has changed to `standings_requests.validate_requests`. Please make sure to update your settings accordingly.

### Added

- You can now also define a corporation as standing organization
- The app will automatically sync standing for alts known to Auth with in-game standing (can be deactivated).
- Users are now always notified when their standings change or their requests are rejected, e.g. once their standing request becomes effective or in case it gets revoked. (can be deactivated)
- The standing organization is now shown on the "create request" page
- Most pages now show icons for characters, corporations and alliances
- "Group standings" page now also shows which main has standing (if any)
- Corporations on "groups standings" page now also show to which alliance they belong
- First standings pull and updates now done automatically after adding a new token. No need to do this manually anymore.
- Added new tests and improved existing tests
- Added support for django-esi 2.x and backwards compatibility for 1.x

### Changed

- User's main no longer has to be outside the main organization to be allowed to request standing for an alt corporation ([#7](https://gitlab.com/basraah/standingsrequests/issues/7))
- UI improvements
- Performance improvements
- Removed undo feature for revocation (no longer relevant)
- Standings can currently not be revoked by managers through the app (will be re-added later). Workaround: Reset standing in game or remove permission for user.
- IDs in settings can now also be integers
- Timeout before actioned standings are reset can now be configured via setting
- Revocations will can no longer be stale and will not be purged automatically
- Improved maintainability (refactored database and code structure)
- Icons upgraded to Font Awesome v5
- Logging directed to extensions logger
- Fix tests for new Auth version

### Fixes

- Numerous bugfixes

## [0.4.1] - 2020-05-28

### Changed

- Updated dependency for django-esi to exclude 2.0
- Added timeout to ESI requests

## [0.4.0] - 2020-04-23

### IMPORTANT UPDATE NOTE

The Python package of the app has been renamed to "aa-standingsrequests". To avoid any naming conflicts please remove the previous version of the app from your venv before upgrading. You can remove the previous version with the following command:

```bash
pip uninstall standingsrequests
```

### Added

- App now appears on admin panel with it's current version and shows requests and eve name cache
- Thresholds for stale standings and revocations can now be configured via setting
- Automatic testing now includes Python 3.6, 3.7 and 3.8
- Flake8 added to automatic test suite

### Changed

- The Python package has been renamed to "aa-standingsrequests"
- Dropped support for Python 3.5
- "Standings Requests" now used as title everywhere in the app

### Fixed

- Memory leak fix with regards to ESI client
- NPC corps no longer appear in list for requesting corp standing ([#8](https://gitlab.com/basraah/standingsrequests/issues/10))

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
