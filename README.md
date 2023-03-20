# build-metrics-reporter

## Summary

This repository contains the source code for `rapids-build-metrics-reporter.py`, which is a small Python script that can be used to generate a report that contains the compile times and cache hit rates for RAPIDS library builds.

It is intended to be used in the `build.sh` script of any given RAPIDS repository like this:

```sh
if ! rapids-build-metrics-reporter.py 2> /dev/null && [ ! -f rapids-build-metrics-reporter.py ]; then
  echo "Downloading rapids-build-metrics-reporter.py"
  curl -sO https://raw.githubusercontent.com/rapidsai/build-metrics-reporter/v1/rapids-build-metrics-reporter.py
fi

PATH=".:$PATH" rapids-build-metrics-reporter.py
```

The logic in the excerpt above ensures that `rapids-build-metrics-reporter.py` can be used in CI (where it will be pre-installed in RAPIDS CI images) and local environments (where it will be downloaded to the local filesystem).

## Versioning

To avoid the overhead of a PyPI package for such a trivial script, this repository uses versioned branches to track breaking changes.

Any breaking changes should be made to new versioned branches (e.g. `v2`, `v3`, etc.).
