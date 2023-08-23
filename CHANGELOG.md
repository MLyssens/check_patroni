# Change log

## Unreleased

### Added

* Add `sync_standby` as a valid replica type for `cluster_has_replica`. (contributed by @mattpoel)

### Fixed

* Fix the `node_is_alive` check. (#31)
* Fix the `cluster_has_replica` and `cluster_node_count` checks to account for
  the new replica state `streaming` introduced in v3.0.4 (#28, reported by @log1-c)

### Misc

* Move packaging metadata into pyproject.toml 
* Create CHANGELOG.md
* Add tests for the output of the scripts in addition to the return code

## check_patroni 0.2.0 - 2023-03-20

### Added

* Add a `--save` option when state files are used
* Modify `-e/--endpoints` to allow a comma separated list of endpoints (#21, reported by @lihnjo)
* Use requests instead of urllib3 (with extensive help from @dlax)
* Change the way logging is handled (with extensive help from @dlax)

### Fix

* Reverse the test for `node_is_pending`
* SSL handling

### Misc

* Several doc Fix and Updates
* Use spellcheck and isort
* Remove tests for python 3.6
* Add python tests for python 3.11

## check_patroni 0.1.1 - 2022-07-15

The initial release covers the following checks :

* check a cluster for
  + configuration change
  + presence of a leader
  + presence of a replica
  + maintenance status
* check a node for
  + liveness
  + pending restart status
  + primary status
  + replica status
  + tl change
  + patroni version
