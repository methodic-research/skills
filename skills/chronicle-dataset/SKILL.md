---
name: chronicle-dataset
description: |
  Use this skill when the user or an agent flow wants to upload dataset bytes or
  training data to a Chronicle experiment, attach data as an experiment or
  variation input, load or download an existing dataset, register a dataset by
  reference to gs:// or s3:// bytes, or describe and update dataset metadata so
  it is searchable. Example requests: "upload this dataset", "register the
  training data", "attach this .npz to the variation", "register the dataset
  already in gs://...", "make this dataset searchable", "fix the dataset
  metadata", "load the dataset", or "download the dataset". For reports use
  chronicle-write-report; for variation config changes use
  chronicle-author-variation.
---

# Dataset upload + load

Get a dataset into Chronicle as a binary asset and attach it to an experiment
or variation as an input — or pull an existing dataset back down. This is a
thin orchestration over the SDK's `chronicle.datasets` namespace; it never
makes raw HTTP calls.

Datasets are plain assets (`asset_type="dataset"`): there is no separate
dataset table. They carry a searchable, author-declared **metadata layer** (a
`metadata` document — see below) and are **full-text + semantically indexed on
that metadata** (the description, PDE, conditions, variable names, properties),
never the bytes. They're discoverable via `chronicle.search`
(`asset_types=["dataset"]` + facets like `precisions`, `pde_family`,
`properties`) and via the dataset catalog, in addition to the
experiment/variation link. The upload also records a provenance record
(per-component sha256 + size) so the bytes are verifiable later.

## Dataset metadata layer (this is what makes it searchable)

Beyond the bytes, a dataset carries an author-declared `metadata` document
(stored on `asset_config.metadata`) projected to Vertex search facets + the
promoted listing columns. **Author it** — this is the taste that makes a
physics dataset discoverable. Pass `metadata=` to `upload` / `register` /
`register_by_reference`, or set it later with `update_metadata`. Shape:

```python
metadata = {
    "schema_version": 1,
    # Long, math-bearing — Markdown + $…$ / $$…$$ LaTeX. The semantic-search payload.
    "description": (
        "Direct numerical simulation of 3D incompressible Navier–Stokes,\n"
        "$$\\partial_t \\mathbf{u} + (\\mathbf{u}\\cdot\\nabla)\\mathbf{u} "
        "= -\\nabla p + \\nu\\nabla^2\\mathbf{u},\\quad \\nabla\\cdot\\mathbf{u}=0$$\n"
        "on a triply-periodic box at $Re_\\lambda \\approx 240$, Kolmogorov-forced."
    ),
    "pde": {"family": "navier_stokes", "name": "Incompressible Navier–Stokes (DNS)",
            "equation_latex": "\\partial_t \\mathbf{u} + ..."},
    "boundary_conditions": ["periodic"],
    "initial_conditions": "random divergence-free, E(k) ∝ k^-5/3",
    "domain": {"geometry": "periodic_box", "spatial_dims": 3, "resolution": [256, 256, 256]},
    "variables": [
        {"name": "u", "role": "field", "shape": [1000, 3, 256, 256, 256], "dtype": "float64", "units": "m/s"},
        {"name": "p", "role": "field", "shape": [1000, 256, 256, 256], "dtype": "float64", "units": "Pa"},
    ],
    "properties": {"forcing": "kolmogorov", "solver": "pseudospectral"},  # free-form facets
}
```

Guidance:

- Write a real `description` with the governing PDE in LaTeX — it's embedded for
  semantic search and rendered (KaTeX) in the dataset detail UI.
- Fill the curated facets (`pde.family`, `boundary_conditions`,
  `initial_conditions`, `domain.geometry`) and the per-variable `variables`
  (shape + dtype + units). Chronicle rolls these up (max rank → `n_dims`, the
  distinct float precisions → `precisions`) for cheap filtered listing
  (`chronicle.datasets.list(precision="fp64", pde_family="navier_stokes")`).
- Use `properties` (string→string) for anything else worth faceting (forcing,
  solver, generator) — each becomes an exact-match search facet
  (`properties: ANY("forcing=kolmogorov")`) with no schema change.

### Register a dataset already in GCS (no upload)

Most large datasets are written straight to GCS and never flow through
Chronicle. Register them **by reference** — created `ready` in one call:

```python
asset = chronicle.datasets.register_by_reference(
    "gs://customer-bucket/turbulence/fit256/",    # existing bytes; not uploaded
    name="forced-isotropic-turbulence-256",
    metadata=metadata,
    size_bytes=13_314_398_208,                     # author-declared
    visibility="org",                              # or "public" / "private"
)
chronicle.datasets.link(asset["id"], experiment_id, variation=variation)  # link like any dataset
```

### Update / correct metadata later

```python
chronicle.datasets.update_metadata(asset_id, metadata=metadata, size_bytes=size)
```

The bytes (`uri` / `sha256` / `components`) are immutable; `metadata` +
`size_bytes` are a **mutable annotation** — editing them recomputes the promoted
columns and re-projects the dataset to search. Requires `Write` on the asset.

You can also pass `metadata=` directly to `upload` (Chronicle-hosted bytes) so
a freshly-uploaded dataset is searchable immediately.

## Sizing — single PUT per component, no multipart

Each component is a **single presigned PUT** — there is no multipart upload.

- **MB-scale** (a reference field, a small `.npz`) → one file, one component.
- **GB-scale** → pass a **directory**: `upload` makes one component per file,
  which is the sharding mechanism. On GCS the presigned write URL is a
  *resumable* session, so a large single object also works; the S3 fallback
  caps a single PUT, so prefer file-level sharding for portability. Split a
  huge monolithic array into per-shard files before uploading.

## Inputs

- **`path`** (upload) — a single file *or* a directory of shards.
- **`experiment_id`** — the Chronicle experiment UUID. Resolve in order:
  1. Explicit argument from the user
  2. `methodic` config (`~/.config/methodic/current_experiment`)
  3. Detect from cwd if inside a clone of the experiment repo
  4. Prompt the user
- **`variation`** (optional) — variation index (or plaintext name → resolve to
  index first) to link the dataset as a *variation* input. Omit to link at the
  *experiment* level (shared across the experiment's variations).
- **`asset_type`** (default `dataset`) — free-form; use a more specific type
  (e.g. `reference_field`) when it helps downstream consumers.
- **`source`** / **`provenance`** (optional) — `source` is a one-line origin
  string (a URL, a generator command, a parent run); `provenance` is a dict of
  domain facts you know (`shape`, `rows`, `schema`, generator config). Both are
  merged into the stored provenance record — the sha256/size/component facts
  are computed for you.
- **`sensitive`** (optional) — when true, link with `propagate_acl=False` so
  the dataset does **not** inherit the experiment's reader ACLs. Default this
  from the user's intent — see "**Sharing is a delegation**" below and **confirm
  before broadly sharing a dataset the user doesn't own**.
- For **load**: **`asset_id`** + a **`dest`** directory.

> **⚠️ An experiment-level link is a delegation — confirm before sharing a
> dataset the user doesn't own.** A `propagate_acl=True` experiment-level link
> (the default) stamps the experiment's reader ACLs onto the dataset — it
> **shares the dataset with everyone who can read the experiment: now, anyone
> invited later, and the whole org or public if the experiment's visibility
> widens.** Before linking a dataset the user **doesn't own** this way, confirm
> they intend that exposure; otherwise link it `sensitive` (`propagate_acl=False`).
>
> A propagating link also **requires Administer on the dataset** (you're editing
> its ACL). Linking a dataset shared with you **read-only** with
> `propagate_acl=True` is refused (`not authorized`) — either its owner shares it
> (chronicle-share, or a transfer), or link it `propagate_acl=False`. This is
> Chronicle's link-time delegation model (authz.md "…delegated at link time").

## Workflow — upload

```python
from methodic import Chronicle

chronicle = Chronicle.from_env()  # CHRONICLE_SERVER_URL + CHRONICLE_API_KEY

# Upload the bytes, record provenance, and link as an input in one call.
ref = chronicle.datasets.upload(
    path,                                  # file → 1 component; dir → 1 per file
    name=name,                             # optional; defaults to the file/dir name
    asset_type="dataset",
    content_type="application/octet-stream",
    source=source,                         # e.g. "generated by tools/make_field.py"
    provenance={"shape": [128, 128], "rows": 4096},  # optional domain facts
    link_experiment=experiment_id,         # link as input now…
    link_variation=variation,              # …at the variation level (omit → experiment-level)
    propagate_acl=not sensitive,           # False keeps a sensitive dataset off experiment ACLs
)

print(f"dataset {ref.asset_id} — {len(ref.components)} component(s), "
      f"{ref.provenance['size_bytes']} bytes")
for c in ref.provenance["components"]:
    print(f"  {c['component']}  sha256={c['sha256'][:12]}…  {c['size_bytes']}B")
```

To link an **existing** dataset to a new variation, either pass it at
variation creation (`variations.create(..., input_asset_ids=[ref.asset_id])`)
or call `chronicle.datasets.link(asset_id, experiment_id, variation=...)`.

## Workflow — load

```python
from methodic import Chronicle

chronicle = Chronicle.from_env()

dest = chronicle.datasets.load(asset_id, "./data")   # downloads every component
prov = chronicle.datasets.provenance(asset_id)        # the recorded provenance, or None
print(f"loaded into {dest}; provenance: {prov}")
```

## Driving the upload yourself (very large / custom transfer)

When you need to manage the component PUTs yourself (resumable retries,
externally generated bytes), `register` creates the asset + presigned URLs
without uploading:

```python
info = chronicle.datasets.register(
    components=["shard-0000.npz", "shard-0001.npz"],
    name="big-dataset",
    provenance={"rows": 10_000_000},
)
for comp, url in info.upload_urls.items():
    chronicle.assets.upload_component(url, local_paths[comp], "application/octet-stream")
chronicle.assets.finalize(info.asset_id)
chronicle.datasets.link(info.asset_id, experiment_id, variation=variation)
```

## After the skill completes

Tell the user:

1. The dataset asset id, its component count + total size, and the experiment
   (and variation) it's linked to as an input.
2. Whether ACL propagation was applied (so they know who can read it) — call
   out when `sensitive` kept it off the experiment's readers.
3. For a load: the destination directory and the recorded provenance.

To share this dataset with a specific person or team, or set its visibility
(private / organization / public) independent of its experiment, use
**`chronicle-share`**.

## Failure modes

- **`upload` / `link` 403** — the caller lacks `Write` on the experiment.
  Surface the message verbatim; the key needs experiment Write (or the dataset
  must be uploaded unlinked and linked by someone who has it).
- **`link` 409 "experiment/variation is committed"** — inputs freeze on
  commit. Link the dataset *before* committing the variation/experiment, or
  add a new (open) variation.
- **GB-scale single file on S3** — a single presigned PUT can't carry it.
  Shard into a directory of files (one component each) and upload the
  directory; don't try to stream a multi-GB monolith through one PUT.
- **Variation-input ACLs don't propagate** — linking at the *variation* level
  does not stamp experiment readers onto the asset (the server only propagates
  for *experiment*-level links). A worker reads a variation-input dataset via
  the experiment's containment; if you need every experiment member to read it
  directly, link at the experiment level with `propagate_acl=True`.
- **Wrong asset type for a report** — datasets are binary inputs. A written
  findings/takeaways document is a *report* — use chronicle-write-report, not
  this skill.
- **MCP `upload_asset` error "must declare its owning scope"** — an unlinked
  upload (`link: "none"`) needs `scope: "user"` or `scope: "organization"` +
  `organization_id`. Prefer linking as an input at upload time; fall back to
  an explicit scope + `chronicle.link_asset` later only when the target
  experiment/variation doesn't exist yet.
- **400 `asset_org_mismatch` / "contradicts the experiment's organization"** —
  you passed `organization_id` on a *linked* upload and it differs from the
  experiment's org. Linked creates inherit the experiment's org/team; drop the
  `organization_id` (it's for standalone/unlinked registration only).

## MCP-native agents

An agent driving Chronicle through the MCP server (not the Python SDK) has
`chronicle.upload_asset` for the **single-file / small-inline** upload case
(inline base64 ≤2 MiB, or a presigned `upload_url` for a single large object)
and `chronicle.load_asset(asset_id)` to mint presigned **read** URLs +
provenance for an existing dataset's components. Multi-file / sharded datasets
are this skill's job — the SDK splits a directory into components, which the
one-shot MCP tools deliberately don't.

**A dataset is an INPUT — always pass `link: "input"`.** Inputs are what the
experiment/variation *consumes* (datasets, reference fields, weights);
outputs are artifacts a *run produced*. A dataset uploaded with
`link: "output"` lands on the wrong side of the experiment record (the
Outputs tab) and corrupts lineage. Concretely:

- **Variation-scoped dataset** → `chronicle.upload_asset(..., link: "input",
  variation: <idx>)`. No ACL propagation (workers read it via the
  experiment's containment).
- **Experiment-shared dataset** → omit `variation`; experiment-level input
  links propagate the experiment's reader ACLs — a **delegation** (see the
  callout under Parameters): confirm before sharing a dataset the user doesn't
  own, and note a propagating link **requires Administer on the dataset**
  (disable with `propagate_acl: false` for a sensitive or read-only-shared one).
- **Order matters**: inputs freeze at commit. Upload + link *before*
  committing the variation/experiment; after commit the input link is
  refused (the freeze is the point — add a new open variation instead).
- **Existing asset** (uploaded earlier with `link: "none"`, or reused from a
  parent experiment) → `chronicle.link_asset(experiment_id, asset_id,
  link: "input", variation?)`. Same freeze + invalidation gates as REST.
- **Proposing a variation around a dataset** →
  `chronicle.propose_variation(..., input_asset_ids: [<asset_id>])` links it
  as a variation input at creation time; upload the bytes first.
- **Unlinked upload** (`link: "none"`, the default) requires an explicit
  owning scope so the asset isn't orphaned: `scope: "user"` for personal, or
  `scope: "organization"` + `organization_id` (resolve via
  `chronicle.list_scopes`; optional `visibility`, org-wide by default in a
  *declared* org context).
- **Linked uploads inherit the experiment's org/team — omit
  `organization_id`.** A `link: "input"`/`"output"` upload with no scope
  declared is attributed to the linked experiment's org/team automatically
  (a dataset created as part of an experiment belongs to the experiment's
  scope, not the uploading identity's). Inheritance needs no org membership —
  the experiment `Write` already checked is the authority — and it does *not*
  broaden default visibility (no org-wide-by-default on an inherited scope;
  declare `visibility` explicitly if you want that). Passing an
  `organization_id` that contradicts the experiment's org is rejected (REST:
  400 `asset_org_mismatch`; MCP: "contradicts the experiment's organization").

**Register-by-reference + metadata over MCP.** For a dataset whose bytes already
live in GCS/S3, an MCP agent calls `chronicle.register_dataset(uri, name,
metadata?, size_bytes?, public?` / `organization_id?)` — created `ready` in one
call, no upload. To author or correct a dataset's metadata layer afterward, use
`chronicle.update_dataset_metadata(asset_id, metadata?, size_bytes?)`. Both take
the same `metadata` document shown in "Dataset metadata layer" above. Discovery
is `chronicle.search` with `asset_types: ["dataset"]` + the dataset facets
(`precisions`, `pde_family`, `properties`).

## Requires

- `pip install methodic-research` (the `chronicle.datasets` namespace;
  `register_by_reference` / `update_metadata` / the `metadata=` arg need the
  release that adds the dataset metadata layer)
- `CHRONICLE_API_KEY` + `CHRONICLE_SERVER_URL` exported (or `methodic auth
  login` already done)
- Optional: a default organization via `organization_id:` in
  `~/.methodic/config.yaml` (or `$CHRONICLE_ORGANIZATION_ID`) — dataset
  creates that omit `organization_id` then attribute to that org; pass
  `methodic.PERSONAL` to force a personal-scope upload.
- No `git` — this skill moves bytes via the API; no repo checkout needed.
