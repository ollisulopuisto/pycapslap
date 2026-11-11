# Vendored Punakynä engine

Upstream: https://github.com/ollisulopuisto/punakyna
Exact revision: `UPSTREAM_COMMIT`. Licence: `LICENSE` (MIT).

The Python engine files are copied at this revision, with one local correction:
`check_negation_agreement` folds input before comparing folded tables and emits
the real Finnish replacement `eivät` rather than `eivat`. Its regression tests
are in `pyside/tests/test_proofreading.py`. Upstream's
pyproject.toml sets `package = false`, so this is an explicit source pin rather
than a non-installable git dependency. Update all files together from a reviewed
revision, preserve the licence, update UPSTREAM_COMMIT, then run the adapter tests
and signed Mac bundle smoke test. No corpus, private rule source collection,
parser downloads or neural weights are included.
