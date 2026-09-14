---
status: approved design; independently reviewed; pending written specification approval
authority: narrow repair to the approved Phase 0A-1 cloud-probe design
supersedes: none
last-verified: 2026-09-14
---

# Phase 0A-1 preflight import-boundary repair design

## Problem and observed evidence

The approved Phase 0A-1 order requires the versioned, read-only cloud preflight to run
before any package installation. On the current AutoDL host, the clean Agent-EX checkout
at `14cffa67bcdc36d2e4f2f8628812259a322bb9d1` uses the image-provided Python 3.12.3.
Starting `python -m agent_ex.calibration.cli preflight` first executes
`agent_ex/__init__.py`. That module eagerly imports the formal network implementation,
whose deliberate runtime guard rejects the image-provided `networkx==3.5` instead of the
project lock `networkx==3.6.1`. No preflight record was written.

The failure is an import-boundary defect, not a reason to relax the dependency guard or
install a package before preflight. The cloud checkout remains clean, the GPU is idle,
and the preflight output path remains absent.

## Approved approach

Retain the existing stable top-level Agent-EX public API, but resolve its exported
objects lazily. Replace eager top-level imports with a fixed, auditable mapping from
every name in `agent_ex.__all__` to its defining module and attribute. Implement module
`__getattr__` to import the defining module only on first access, verify that the
resolved attribute exists, cache the resolved object in the package globals, and return
it. Implement `__dir__` so introspection continues to expose the stable public names.

The mapping is static source code. It must have exact key equality with `__all__`; no
runtime discovery, wildcard import, plugin loading, environment-dependent export, or
fallback search is permitted. An unknown attribute must raise the normal
`AttributeError`. A dependency/version failure raised when a caller actually requests a
network-bound symbol must remain visible and unchanged.

Python still imports `agent_ex.calibration` and the calibration CLI for the preflight
command, but it no longer imports the formal network, storage, engine, prompt, or other
unrelated top-level exports merely because the parent package was initialized. The
existing command name, cloud preflight schema, canonical hashing, Git binding,
create-only output, and no-network/no-install behavior remain unchanged.

This design narrows and corrects Task 9 of the 2026-09-10 implementation plan. Before
the project is installed, the installed console entry point `agent-ex-phase0a1` and the
current `platform/scripts/phase0a1-preflight.sh` wrapper are forbidden: either can
resolve stale globally installed code, and the entry point does not exist in a clean
checkout. The only permitted pre-install bootstrap is the image Python executing the
module from the verified source checkout, with an absolute source path:

```sh
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=/root/autodl-tmp/agent-ex-phase0a1/platform/src \
/root/miniconda3/bin/python -m agent_ex.calibration.cli preflight \
  --output /root/autodl-tmp/agent-ex-phase0a1-evidence/preflight.json
```

Immediately before this command, the same interpreter and `PYTHONPATH` must import
`agent_ex`, resolve `agent_ex.__file__`, and fail unless that file lies below the
absolute `platform/src` directory of the clean checkout whose HEAD has just been
verified. The output must be an absolute create-only path outside the Git checkout.
After the project is installed from that verified checkout, the console entry point may
be used for later commands. No pre-existing global entry point can establish source
binding for the authoritative preflight.

## Compatibility boundary

The repair must preserve:

- every existing string and order in `agent_ex.__all__`;
- `from agent_ex import <public-name>` behavior and object identity after resolution;
- direct submodule imports such as `from agent_ex import protocol`;
- the original defining module recorded on exported classes and functions;
- the exact `networkx==3.6.1` guard whenever a network-dependent symbol is requested;
- the existing package wheel and editable-install entry points.

The repair does not change protocol values, model/runtime candidates, formal authority,
cloud schemas, network algorithms, event semantics, or experiment behavior. It does not
authorize installing dependencies, downloading the model, starting vLLM, or sending a
model request.

## Verification design

TDD begins with an isolated subprocess regression that injects a minimal fake
`networkx` module reporting version `3.5`, imports `agent_ex`, and invokes the Phase 0A-1
CLI help path. On the current eager implementation it must fail with the existing
network-version error; after the repair it must succeed and prove that
`agent_ex.network` was not loaded. A paired assertion must access a network export and
prove that the original version guard still fails closed.

A separate clean-bootstrap subprocess must model the pre-install source-tree path, not
an editable or wheel installation. It exposes only the checkout's absolute
`platform/src` as Agent-EX source, blocks imports of every declared project dependency
(`networkx`, `jsonschema`, and `yaml`/PyYAML), runs CLI help and argument parsing, and
asserts that the imported `agent_ex.__file__` resolves below that exact source tree.
It must also assert that formal network, storage, engine, protocol, and validation
modules were not loaded. This proves that bootstrap parsing itself does not silently
depend on the locally installed development environment. Tests that exercise actual
preflight collection may explicitly supply the image-provided non-network bootstrap
dependencies only where the collection path genuinely requires them; they may not
weaken or replace the clean-bootstrap test.

Additional tests must prove exact equality between the lazy-export mapping and
`__all__`, successful resolution and caching of every public export in the locked local
environment, normal unknown-attribute failure, direct submodule compatibility, and
wheel-install behavior. The focused installation/CLI/calibration suites, Ruff, format,
pip, and diff checks must pass before committing.

Before replacing the failed cloud checkout, write a sanitized failed-preflight receipt
outside Git and hash it. The receipt must bind the cloud host/session identifier, exact
source-bound command form, image Python and observed NetworkX versions, checkout HEAD
and clean/dirty state, exit code, bounded error summary, intended output path, and an
explicit check that the output does not exist. It must identify the attempt as
`failed_preflight` and grant no smoke, install, model-download, server-start, or run
authority. Credential values and environment dumps are forbidden. A later committed
sanitized log records the receipt's SHA-256 and its external archive location; it does
not commit the receipt itself.

After the local repair is committed and that failure receipt is sealed, create a new
exact-HEAD Git bundle, verify its SHA-256 on the AutoDL data disk, replace the failed
clean checkout with a newly cloned checkout at that exact commit, verify the loaded
source path as specified above, and rerun the versioned preflight through the sole
source-bound bootstrap before any install.
The resulting JSON must be copied back outside Git and reopened locally with
`CloudPreflight.from_payload`; its canonical `record_hash`, `git_commit`, `git_dirty`,
single-GPU observation, and calibration-only/no-formal-authority flags must all verify.

## Failure handling

Any mapping drift, import of `agent_ex.network` during the preflight bootstrap, changed
public object identity, dependency-guard bypass, dirty cloud checkout, existing output
file, hash mismatch, or schema mismatch fails closed. The failed cloud checkout and
absent preflight record are evidence only; they must not be relabeled as a successful
preflight. A missing or invalid failed-attempt receipt blocks replacement of the failed
checkout. A source path outside the exact verified checkout blocks preflight. No
runtime installation may begin until the repaired authoritative preflight has been
produced and reopened successfully.
