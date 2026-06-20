---
name: chronicle-register-dataset
description: |
  Use this skill when the user (or an agent flow) wants to **register a dataset
  that already lives at a `gs://` / `s3://` URI** (no byte upload), **author or
  correct a dataset's searchable metadata layer**, or **list / filter the
  dataset catalog**. Phrases like "register the dataset already in gs://…",
  "catalog this turbulence corpus we wrote to the bucket", "describe this
  dataset — the PDE it models, its boundary conditions, the variables and their
  shapes", "make this dataset searchable", "fix the dataset's metadata / add the
  PDE equation", "what fp64 Navier–Stokes datasets do we have", "list datasets
  with 3 spatial dims". A dataset is a plain asset (`asset_type="dataset"`)
  registered **by reference** to existing bytes, carrying an author-declared,
  searchable **metadata layer** — a long LaTeX-bearing description, the governing
  PDE, boundary/initial conditions, domain geometry, per-variable
  shape·dtype·units, and a free-form `properties` facet bag. To **upload** local
  bytes (presigned PUT) or **download** a dataset, use chronicle-dataset; for
  *reports* use chronicle-write-report; for a variation's *config* use
  chronicle-author-variation.
---

# Register dataset by reference + author its metadata

Catalog a dataset that **already lives at a `gs://` / `s3://` URI** — no byte
upload — and give it the author-declared **metadata layer** that makes a physics
dataset *describable, filterable, and searchable*: a long, math-bearing
description, the PDE it discretizes, its boundary/initial conditions, the domain
geometry, a per-variable table (shape · dtype · units), and an open bag of
`key=value` properties. Also update that metadata later and list/filter the
catalog.

Most large datasets are written **straight to GCS** (or live in an org's BYOB
bucket) and never flow through Chronicle's upload path — register-by-reference is
the common case, mirroring `hf_dataset`: the asset is created **`ready` in a
single call**, no presign/PUT/finalize. The registrant supplies the metadata;
Chronicle does **not** open the bytes to derive or verify shape/dtype/size — the
metadata layer is *descriptive*, author-declared, and a **mutable annotation**
you can correct and enrich after the fact.

This skill is the **register-by-reference + metadata** counterpart to
`chronicle-dataset` (which moves *local bytes* via presigned upload, and
downloads). When the data is already in the bucket, reach for this one.

## Transport — MCP-direct (no SDK needed)

This skill uses the **bundled MCP tools** directly — no `pip install`. (If the
`methodic` SDK happens to be installed and you prefer it, the SDK equivalents are
noted inline.) The bundled launcher resolves credentials from `~/.methodic` — see
the repo README "The MCP tools (bundled — zero config)". Register-by-reference,
metadata authoring, and catalog listing are pure CRUD/metadata — no local-git and
no bytes cross the model — so the bundled MCP tools are the default here.

The three tools this skill drives:

- **`chronicle.register_dataset`** — register an existing `gs://`/`s3://` URI as a
  `ready` `dataset` asset with its metadata layer, in one call.
- **`chronicle.update_dataset_metadata`** — patch the (mutable) metadata layer.
- **`chronicle.list_datasets`** — Postgres-side filtered listing on the promoted
  facets (`n_dims`, `precision`, `pde_family`, `geometry`, size, sort).

## The metadata layer (this is what makes a dataset searchable)

Everything below is **optional except a `description`** — a minimal dataset can
carry nothing else. But authoring real metadata is the whole point: it's what a
researcher searches on ("3D incompressible Navier–Stokes, periodic box, fp64")
when deciding whether a dataset fits their model. The full document is stored
canonically (`asset_config.metadata`); Chronicle denormalizes a few hot fields
into indexed columns for cheap filtered listing and projects the rest to search.

```jsonc
{
  "schema_version": 1,

  // The ONE field expected to be long. Markdown + inline/blocked LaTeX
  // ($…$ / $$…$$). Embedded for semantic search; rendered (KaTeX) in the UI.
  // Say what the data physically is, the governing PDE, and how it was generated.
  "description": "Direct numerical simulation of 3D incompressible Navier–Stokes,\n$$\\partial_t \\mathbf{u} + (\\mathbf{u}\\cdot\\nabla)\\mathbf{u} = -\\nabla p + \\nu\\nabla^2\\mathbf{u},\\quad \\nabla\\cdot\\mathbf{u}=0$$\non a triply-periodic box at $Re_\\lambda \\approx 240$, Kolmogorov-forced.",
  "summary": "DNS of forced isotropic turbulence, 3D incompressible NS, Re_λ≈240",

  "pde": {
    "family": "navier_stokes",                  // coarse class → promoted, facet-filterable
    "name": "Incompressible Navier–Stokes (DNS)",
    "equation_latex": "\\partial_t \\mathbf{u} + (\\mathbf{u}\\cdot\\nabla)\\mathbf{u} = -\\nabla p + \\nu\\nabla^2\\mathbf{u}",
    "parameters": { "reynolds_number": 240, "viscosity": 1.0e-4 }
  },

  "boundary_conditions": ["periodic"],          // string or array
  "initial_conditions": "Random divergence-free field, energy spectrum E(k) ∝ k^{-5/3}",

  "domain": {
    "geometry": "periodic_box",                 // coarse domain → promoted, facet-filterable
    "spatial_dims": 3,
    "extent": [6.283, 6.283, 6.283],
    "resolution": [256, 256, 256],
    "periodic": [true, true, true]
  },

  "variables": [                                // multi-variable: per-variable shape + dtype
    { "name": "u", "role": "field", "shape": [1000, 3, 256, 256, 256], "dtype": "float64", "units": "m/s", "description": "velocity field (3 components)" },
    { "name": "p", "role": "field", "shape": [1000, 256, 256, 256],    "dtype": "float64", "units": "Pa",  "description": "pressure" },
    { "name": "t", "role": "coord", "shape": [1000],                   "dtype": "float32", "units": "s",   "description": "time axis" }
  ],

  "temporal": { "num_timesteps": 1000, "dt": 0.002 },

  // Coarse roll-ups. Author them, or omit and let Chronicle derive them from
  // `variables`/`domain` (max rank → n_dims; distinct float precisions; counts).
  "structural": {
    "n_dims": 5,                                // max rank across variables ("cardinality of shape")
    "precisions": ["fp32", "fp64"],             // controlled vocab: fp16, bf16, fp32, fp64
    "variable_count": 3,
    "num_samples": 1000                         // leading-dim cardinality, when meaningful
  },

  // Free-form, arbitrary keys (string → string). Each becomes an exact-match
  // search facet `properties: ANY("key=value")` — no schema migration.
  "properties": {
    "forcing": "kolmogorov",
    "solver": "pseudospectral",
    "dealiasing": "2/3-rule",
    "generator": "JHTDB-style DNS"
  },

  "provenance": { "simulator": "in-house spectral DNS v2.3", "citation": "arXiv:2401.01234" }
}
```

### Authoring guidance — the taste this skill exists to capture

- **Write a real `description`.** This is the semantic-search payload and the one
  field that should be long: the governing PDE in LaTeX (`$…$` / `$$…$$`), what
  the data physically represents, and how it was generated. LaTeX is stored
  verbatim and rendered (KaTeX) in the dataset detail UI.
- **Fill the curated facets** — `pde.family`, `pde.name`, `pde.equation_latex`,
  `boundary_conditions`, `initial_conditions`, `domain.geometry`/`spatial_dims`/
  `resolution` — and the **per-variable `variables` table** (`name`, `role`,
  `shape`, `dtype`, `units`). Accurate `variables` make the `structural` roll-ups
  (`n_dims` = max rank, `precisions` = distinct float dtypes, `variable_count`,
  `num_samples`) correct, which is what powers cheap filtered listing.
- **Use `properties` for anything else worth faceting** — forcing, solver,
  dealiasing, generator — with **stable, lowercased keys** (keys are normalized
  lowercase, `=` is reserved as the separator; values are coerced to strings).
  Each becomes `properties: ANY("forcing=kolmogorov")` in search with no schema
  change.
- **`precisions`** is a small controlled vocabulary — `fp16`, `bf16`, `fp32`,
  `fp64`. Per-variable `dtype` is free-form (`float64`, `int32`, …); the roll-up
  normalizes the float ones into that vocab.
- **`size_bytes`** is author-declared (descriptive). Supply it for
  register-by-reference so the catalog can show + sort on size.

## Inputs

- **`uri`** (register) — the existing `gs://…` or `s3://…` location of the bytes
  (a directory prefix for sharded/Zarr data, or a single object). **Not minted by
  Chronicle** — the bytes already exist there; register-by-reference never writes
  into the bucket (it may be a foreign/BYOB bucket Chronicle can't write to).
- **`metadata`** — the metadata document above. Author it; `description` at
  minimum.
- **`name`** (optional) — defaults sensibly; prefer a descriptive slug
  (`forced-isotropic-turbulence-256`).
- **`size_bytes`** (optional) — author-declared total stored bytes.
- **`content_type`** (optional) — e.g. `application/x-zarr`,
  `application/octet-stream`.
- **scope / visibility** (optional) — `organization_id` to register into an org
  (fill from `~/.methodic/config.yaml`'s recorded default when the user doesn't
  name one, and say which org was used); `public: true` for a public corpus
  (`everyone:Read`). Omit for personal scope.
- **`asset_id`** (update / inspect) — the dataset asset UUID for
  `update_dataset_metadata`.
- **filters** (list) — `n_dims` / `min_dims` / `max_dims`, `precision`
  (repeatable → array membership), `pde_family`, `geometry`, `min_size` /
  `max_size`, `order_by ∈ {size_bytes, created_at, num_samples}`.

## Workflow — register by reference

1. **Author the metadata** with the user (see the guidance above) — at minimum a
   real `description`; fill the curated facets, the `variables` table, and
   `properties` you know.

2. Call **`chronicle.register_dataset`** with the URI + metadata:

   ```jsonc
   {
     "uri": "gs://customer-bucket/turbulence/fit256/",   // existing bytes; not uploaded
     "name": "forced-isotropic-turbulence-256",
     "content_type": "application/x-zarr",
     "size_bytes": 13314398208,
     "metadata": { /* the metadata document above */ },
     "organization_id": "<org-uuid>"                     // optional; or public: true
   }
   ```

   The asset is created **`ready` in one call** — no presign/PUT/finalize.
   Chronicle validates the metadata's *shape* (not against the bytes),
   denormalizes the promoted columns, applies ACLs, and enqueues the search
   projection. The result (JSON in the tool's text content) carries the dataset
   `id`.

   *(SDK equivalent: `chronicle.datasets.register_by_reference(uri, name=…,
   metadata=…, size_bytes=…, visibility=…)`.)*

3. **Link it as an input** when it belongs to an experiment/variation — that's
   `chronicle-dataset`'s job (`chronicle.link_asset(experiment_id, asset_id,
   link: "input", variation?)`). Registration and linkage are independent: a
   dataset can sit in the catalog unlinked and be linked into many experiments
   later.

## Workflow — update / correct the metadata layer

The bytes (`uri`, `sha256`, `components`) are **immutable**; the **metadata layer
is a mutable annotation** — same family as the ACL list and the
deprecated/invalidated flags. This is what lets you fix a wrong boundary-condition
tag or add a missing PDE equation without minting a new asset.

```jsonc
// chronicle.update_dataset_metadata
{ "asset_id": "<id>", "metadata": { /* partial or full */ }, "size_bytes": 13314398208 }
```

A patch re-denormalizes the promoted columns and re-projects the dataset to
search. It does **not** touch the content blob or dedup identity. Requires
`Write` on the asset.

*(SDK equivalent: `chronicle.datasets.update_metadata(asset_id, metadata=…,
size_bytes=…)`.)*

## Workflow — list / filter the catalog

Cheap Postgres-side filtered listing on the promoted facets (no search
roundtrip) — the default for browsing the dataset catalog:

```jsonc
// chronicle.list_datasets
{ "pde_family": "navier_stokes", "precision": ["fp64"], "n_dims": 3,
  "min_size": 1000000000, "order_by": "size_bytes" }
```

Returns the datasets the caller can read (ACL-filtered), keyset-paginated. Use
`min_dims`/`max_dims` for a range and repeat `precision` for array membership.

*(SDK equivalent: `chronicle.datasets.list(n_dims=, precision=, pde_family=,
geometry=, min_size=, max_size=, order_by=)`.)*

For **full-text + semantic + arbitrary-`properties`** search (the long
description, the PDE prose, `properties: ANY("forcing=kolmogorov")`), use
**`chronicle.search`** with `asset_types: ["dataset"]` plus the dataset facets
(`precisions`, `pde_family`, `properties`). A dataset is discoverable via both
paths the moment it's registered (Postgres immediately; search within the index
cadence / on the write-through patch).

## After the skill completes

Tell the user:

1. The dataset asset **id**, its `name`, the `uri` it was registered against, and
   the declared `size_bytes` — and that it was created `ready` with no upload.
2. Its scope/visibility (which org, or public/personal) — so they know who can
   read it — and remind them it isn't linked to any experiment yet (point at
   `chronicle-dataset` to link it as an input).
3. For an **update**: which metadata fields changed and that the promoted columns
   + search projection were refreshed.
4. For a **list**: the filters applied and a short rundown of the matches (id,
   name, the facets that matter — `pde_family`, `n_dims`, `precisions`, size).

To set a dataset's visibility (private / organization / public) or share it with
a specific person or team independent of any experiment, use **`chronicle-share`**.

## Failure modes

- **`register_dataset` 400 — invalid `uri`** — the URI must be an existing
  `gs://…`/`s3://…` location. Register-by-reference does **not** create the bytes;
  upload them with `chronicle-dataset` (presigned PUT) first if they don't exist
  yet.
- **`register_dataset` / a create that omits scope** — a dataset needs an owning
  scope. Fill `organization_id` from `~/.methodic/config.yaml`'s recorded default
  (and say which org), pass it explicitly, or set `public: true` for a public
  corpus; omit entirely only for personal scope.
- **`update_dataset_metadata` 403** — the caller lacks `Write` on the asset.
  Surface the message verbatim; the metadata layer mutates only with asset
  `Write`.
- **Metadata-shape validation error** — Chronicle validates the metadata's
  *shape* (e.g. `precisions` vocab, `variables[].shape` a list of ints), never
  against the bytes. Fix the document and re-call; a mismatch between declared and
  actual shape is **not** caught here (introspection is deferred — the layer is
  descriptive).
- **Wrong skill for local bytes** — if the data is a **local file/directory** to
  push, this skill can't move bytes. Use `chronicle-dataset` (presigned PUT;
  directory → one component per file for GB-scale sharding), then optionally
  update its metadata here.
- **Older server without the dataset metadata layer** — `register_dataset` /
  `update_dataset_metadata` / `list_datasets` (and the `metadata` arg) need the
  Chronicle release that adds the dataset metadata layer. On a missing
  tool/endpoint, say so plainly and fall back to `chronicle-dataset`'s
  `register` / upload path (bytes + provenance only, no searchable metadata)
  rather than papering over the gap — and file it with `chronicle-feedback`.

## Requires

Nothing to install — uses the bundled MCP tools (`chronicle.register_dataset`,
`chronicle.update_dataset_metadata`, `chronicle.list_datasets`). Credentials come
from `~/.methodic` (`CHRONICLE_API_KEY` + `CHRONICLE_SERVER_URL`, or `methodic
auth login`); set `organization_id:` in `~/.methodic/config.yaml` to register
into an org by default. No `git` — this skill is API/metadata-only and moves no
bytes (the bytes already live at the `uri`).
