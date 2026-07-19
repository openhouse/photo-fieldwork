# Recommendations for `photo-fieldwork`

**Prepared:** July 13, 2026
**Basis:** Hands-on use of `curate-apple-photos` for the v04-I editor field, followed by inspection of the current public repository and its local work in progress.
**Status:** Product and engineering recommendations with the highest-priority contracts implemented in Revision I. This is not a testimonial or independent audit.

## Executive recommendation

Treat `photo-fieldwork` as a local-first evidence system for visual archives, not merely a collection of scripts that creates Apple Photos albums.

The project already has an unusually good ethical and operational center:

- pixels must actually be inspected;
- source media stays local;
- holds and uncertainty remain visible;
- Photos writes are membership-only;
- a small test write precedes production;
- the result is independently verified against the Photos database.

Those principles held up during the v04-I run. The weak point was not the curatorial method. It was that several essential parts of the method still lived in improvised run-specific scripts and human memory. At whole-library scale, the skill needs stronger internal contracts around view assignment, evaluation strata, feedback, duplicate control, run state, report schemas, and the relationship between the final evaluated manifest and the write plan.

The recommended next release should make one promise:

> Given the same source snapshot, brief, configuration, evidence, and judgments, `photo-fieldwork` can explain, reproduce, resume, and independently verify the same editorial field without silently changing the meaning of a selection.

## What v04-I proved

The v04-I field was built from 603,137 visible still photographs. It retrieved 7,000 fresh candidates, locally inspected all 7,000 previews, created an exact 4,000-photo master, preserved 1,982 holds outside the master, and independently verified the final Photos commit. A 10-photo test album preceded production, the production write was rerun idempotently, and immutable SQLite verification found no missing, unexpected, or out-of-source memberships.

That is a meaningful success. It demonstrates that the project can:

1. Work across a genuinely large personal archive.
2. Preserve a local-only media boundary.
3. Separate editorial selection from safety review.
4. Create exact, versioned, editor-ready album structures.
5. Verify the result through a path independent of the writer.

It also exposed the places where the current implementation makes the operator carry too much state personally.

## Role-played discussion

The following is a simulated editorial and product discussion. It does not represent statements or endorsements by the named people.

**Prof. Ingeborg Gerdes:**
I think the strongest thing here is the refusal to treat an archive as a pile of interchangeable images. A field has edges, absences, recurrences, and relations. The software should preserve those relations as evidence, including why an image entered the field and why another was withheld.

**Jamie Burkart:**
I think the skill worked because it let structure grow out of the material. The next step is to give that process resilient form. I do not want the software to hide ambiguity; I want it to make ambiguity navigable without making the whole run groundless.

**Prof. Warren Sack:**
I think each selected image should carry an inspectable argument: retrieval evidence, visual evidence, assignment, judgment, and revision history. A score without its contributing claims is not yet an explanation.

**Prof. Margaret Morse:**
I think the contact sheet is not a secondary export. It is the editorial interface where sequence, repetition, social density, and atmosphere become visible. It deserves a stable manifest, navigation, and a record of decisions made through it.

**Hamel Husain:**
I think the product bottleneck is now evaluation design. The overall precision number can look healthy while an important view is failing. Build a benchmark suite from the actual failure modes, enforce stratum-level gates, and measure whether the skill improves rather than relying on confidence in the prompt.

**Future Professional Jamie:**
I think a future collaborator should be able to enter after an interruption, read the run state, see what is trusted, and continue without reconstructing my intentions from filenames. Resumability is part of professional care.

**Cyd Harrell:**
I think operator safety means predictable states, clear permissions, recoverable failures, and no ambiguous success. The system should say what happened, what did not happen, and what must be checked before the next irreversible action.

**Deborah Treisman:**
I think the system should permit a small project view to remain small. Two excellent, defensible images are better than a quota filled with weak approximations. Editorial confidence comes from disciplined omission.

**Chad Berkowitz:**
I think this is ready to become a serious product, but only if the next pass is ruthless about the core contracts. Fix assignment, evaluation, final-manifest integrity, and resumability first. Attractive secondary features can wait until those are boringly dependable.

**Sara Hendren:**
I think classification should remain assistive and contestable. The system must show why it inferred risk or relevance, preserve human override, and avoid turning people or environments into unexamined categories.

**Stephen Coles:**
I think contact sheets need typographic and spatial discipline. Identifiers, judgments, and evidence must remain legible at review scale, with stable coordinates that let an editor refer to an image without hunting for it again.

**Maggie Appleton:**
I think the project wants a provenance graph: source snapshot to candidate, candidate to inspection, inspection to judgment, judgment to master, master to plan, plan to receipt. Each edge should be explicit and hashable.

**Ramit Sethi:**
I think the value is in making a high-quality run cheaper to repeat. Count manual interventions, minutes of operator attention, reruns, and recovery steps. Productize the interventions that recur; do not merely document them as heroic craft.

**Shreya Shankar:**
I think uncertainty, sparse strata, repeated samples, and post-evaluation changes are first-class evaluation concerns. Freeze the proposal being evaluated, use fresh examples plus regression canaries, and block release when the final artifact is not the artifact that passed.

**Vivian Gornick:**
I think rejection is knowledge. The photographs that almost worked tell us what the archive and the project are not. Preserve that negative knowledge so every round does not have to rediscover it.

## Priority 0: make the core trustworthy at whole-library scale

### 1. Promote whole-library access to a first-class source adapter

At the time of the v04-I review, the committed skill described a 124,484-item wide album as the default immutable source while local work in progress added a `visible-library-stills://v1` source and whole-library inventory builder. Revision I completes that direction as a versioned source contract.

**Change:**

- Represent album, smart scope, and visible-library sources through one source interface.
- Record observed count, query/predicate version, creation time, Photos library identity, and an inventory checksum in a source manifest.
- Remove the hard-coded `603137` assertion from the builder. Compare against an explicit plan expectation or prior snapshot instead.
- Fail on unexpected drift before inspection or write, but provide a command that deliberately accepts and versions a new snapshot.
- Update `SKILL.md`, starter config, workflow docs, and tests to describe the same source model.

**Acceptance:** A new library count does not require a code edit, while an unacknowledged source change still blocks the run.

### 2. Separate candidate hypotheses from editorial assignment

During v04-I, candidates correctly carried several possible views. A strict assignment pass then chose quota-respecting views, but unassigned rows retained `candidate_views`. The generic selector could interpret the first candidate hypothesis as the final view and refill a weak view with images the strict assignment had intentionally rejected.

**Change:**

- Make `candidate_views` an immutable retrieval field.
- Add explicit `assigned_view`, `assignment_status`, `assignment_reason`, and `assignment_version` fields.
- Require selection to consume `assigned_view`; it must never infer a final assignment from `candidate_views`.
- Add statuses such as `assigned`, `unclassified`, `sparse-hypothesis`, `held`, and `rejected`.
- Fail validation when a selected row lacks a valid assignment.

**Acceptance:** A regression test proves that rejected hypotheses cannot silently repopulate a view.

### 3. Enforce per-view evaluation gates

Overall decisive precision can conceal a failing stratum. In v04-I, one round reached 84.31% overall while two views were at 40% and 60%. The written evaluation guidance already says no material view should remain below 0.65, but the core evaluator does not enforce that rule.

**Change:**

- Add configurable minimum decisive precision and maximum uncertainty rate per material view.
- Require a minimum sample size before a view can pass; inspect all selected items when a view is smaller than that floor.
- Report confidence intervals or clearly mark tiny samples as insufficient rather than treating two judgments as stable evidence.
- Allow a weak view to pass only by being explicitly relabeled `sparse-hypothesis` or returned to unclassified.
- Gate on coverage, decisive precision, uncertainty, safety review, and preview availability separately.

**Acceptance:** The evaluator returns failure when overall precision passes but any material view misses its gate.

### 4. Freeze the artifact that is evaluated and written

The final master can currently change after an evaluation round without a cryptographic or structural guarantee that the write plan corresponds to the passed artifact.

**Change:**

- Give every proposal an immutable ID and content hash.
- Record hashes for source snapshot, candidate manifest, inspection evidence, judgment ledger, final master, write plan, and receipt.
- Require a full final audit after the last selection change. Targeted edge audits can supplement but not replace it.
- Make plan generation fail when the final master hash does not match the passed evaluation record.
- Make independent verification report the same chain.

**Acceptance:** Editing one selected UUID after evaluation invalidates the plan and forces a new final audit.

### 5. Make feedback and negative knowledge first-class data

Run-specific feedback scripts were needed to apply judgments, protect rejected IDs, and repair evaluation samples. One schema mismatch omitted `judgment` from an output CSV and produced zero evaluation coverage instead of failing at the point of corruption.

**Change:**

- Add supported `feedback validate`, `feedback apply`, and `feedback merge` commands.
- Define a versioned judgment schema with required fields and controlled vocabularies.
- Preserve append-only decisions with evaluator, timestamp, proposal ID, reason code, note, and superseded judgment.
- Maintain explicit exclusion, hold, and regression-canary ledgers.
- Fail loudly on missing required columns, unknown judgments, duplicate conflicting rows, or proposal mismatches.

**Acceptance:** Feedback cannot be silently dropped by a CSV writer, and prior rejects remain excluded unless explicitly reconsidered.

### 6. Add perceptual and sequence duplicate control

Photos metadata duplicate groups did not catch several near-identical frames in v04-I, including images represented in different formats. Duplicate control should happen before quota filling, not as a late editorial cleanup.

**Change:**

- Bundle local perceptual hashing or image-embedding clustering with no external upload.
- Record `perceptual_cluster_id`, distance, representative choice, and override reason.
- Add optional event/sequence clustering using capture time and coarse local context.
- Make per-view and master-level cluster caps configurable.
- Keep all cluster members inspectable even when only one can be selected.

**Acceptance:** Known cross-format and near-identical fixtures collapse into the same cluster, and the selector cannot overfill from one sequence.

### 7. Make privacy minimization structural

The initial whole-library inventory implementation copied exact latitude and longitude and recorded a raw local Photos database path in metadata. Those values may be useful privately, but the skill promises to keep exact locations out of reports. Revision I enforces that promise with explicit inventory profiles.

**Change:**

- Define `minimal`, `retrieval`, and `debug` inventory profiles.
- Default to coarse place tokens or `has_location`; exclude exact coordinates unless the brief explicitly requires them.
- Redact user names, absolute source paths, raw OCR, and exact locations from shareable reports.
- Label every artifact `private-operational`, `review-sensitive`, or `public-safe`.
- Add a report linter for forbidden fields and likely secrets.

**Acceptance:** Public-safe reports cannot contain exact coordinates, raw OCR, private paths, credentials, or unidentified personal names.

### 8. Turn run state into an actual state machine

`run-state.json` is created, but the v04-I run still required manual interpretation of phase completion. A long local Photos operation needs resumable checkpoints and a clear distinction between planned, running, interrupted, failed, and verified.

**Change:**

- Update state atomically at the start and end of every command.
- Record command, inputs, hashes, process/app receipt, completed batches, errors, and next valid actions.
- Add `status`, `resume`, and `doctor --run` commands.
- Emit structured progress and a heartbeat from the Photos integration.
- Detect stale receipts, partial preview exports, interrupted writes, and source drift.

**Acceptance:** After terminating a long inspection, `resume` continues from the last verified batch without duplicating work or hiding the interruption.

## Priority 1: improve editorial intelligence and operator experience

### 9. Replace opaque relevance scores with typed evidence

Generic visual labels such as `machine`, `table`, `sign`, or `container` produced false project and work-context matches. The system should distinguish visible action, environmental context, text evidence, album provenance, people association, and weak semantic resemblance.

Add a per-view evidence breakdown with positive and negative rules. Preserve model name, model version, confidence, and source for machine-generated evidence. Let the config say, for example, that a technical-work view requires visible action or project-specific corroboration, not merely an object that often appears in offices.

### 10. Build a durable review surface around contact sheets

Generate a page manifest that records page, row, column, UUID, assigned view, safety status, and proposal ID. Support multiple preview roots, corrupt-preview placeholders, exact sample order, and stable labels. A lightweight local HTML review surface could add keyboard judgments and notes while keeping the canonical data in the judgment ledger.

### 11. Automate quota relaxation without lowering standards

When a project view has little defensible visual evidence, the system should shrink that view and return capacity to unclassified or stronger views. It should never fill a quota by lowering its evidence threshold. Emit a `sparse-hypothesis` report explaining the available evidence and editorial consequence.

### 12. Optimize retrieval as a measured subsystem

The original term-by-term wildcard retrieval became a bottleneck across roughly 600,000 assets, requiring a run-specific fast retrieval path. Consolidate matching into indexed, set-based queries; consider SQLite FTS for normalized text fields; cache query results by snapshot hash; and record query plans and timings.

Set performance budgets from measured baselines rather than guessed wall-clock targets. Track source size, matched size, peak memory, elapsed time, and operator wait time.

### 13. Sample for learning, not just coverage

Each round should combine:

- fresh, previously unseen examples;
- score-boundary examples;
- every sparse or weak view;
- a stable regression-canary set;
- safety and privacy edge cases;
- a random slice of unclassified images.

Do not repeatedly spend the sample budget on the same easy positives. Store the sampling reason on every row.

### 14. Measure social and event diversity explicitly

`minimum_named_people_fraction` is useful but can be satisfied by many images of the same person or event. Add optional floors and caps for unique people groups, events/sequences, dates, places at a safe granularity, and person-free environments. These are compositional controls, not claims about identity.

### 15. Separate field creation from publication selection

Keep the 4,000-photo editor field generous. Add a downstream workflow for page-specific shortlists that reviews rights, consent, caption accuracy, crop suitability, accessibility text, and public-safety context. That should be a separate command or skill so publication pressure does not contaminate archival field construction.

## Priority 2: make the project maintainable and transferable

### 16. Build a skill benchmark suite from real failure modes

Use paired evaluations: current committed skill versus the proposed skill. Run both from clean contexts and compare correctness, intervention count, runtime, and recovery behavior.

Recommended benchmark scenarios:

1. **Small known album:** 500-photo source, exact 100-photo field, fast deterministic path.
2. **Whole visible library:** thousands of fresh candidates, local inspection, people context, safety holds, exact master.
3. **Sparse project evidence:** one view has only a few defensible images and must shrink rather than fill weakly.
4. **Assignment regression:** rejected candidate hypotheses must not become assigned views.
5. **Evaluation imbalance:** overall precision passes while one material stratum fails.
6. **Interrupted inspection:** stop mid-batch, resume, and obtain the same result.
7. **Privacy trap:** fixtures contain a login screen, exact location, identity document, minor, and raw OCR.
8. **Duplicate trap:** near-identical images, burst frames, and the same visual in different formats.
9. **Final-manifest drift:** alter the master after evaluation and confirm plan generation blocks.
10. **Idempotent write:** rerun test and production plans and independently verify unchanged memberships.

Core assertions should include:

- exact target and unique still-photo membership;
- every selected image has decodable local pixel evidence;
- zero hold/master overlap;
- every material view passes its own gate or is marked sparse;
- final master hash matches the evaluated proposal and write plan;
- no external upload;
- no forbidden private fields in shareable reports;
- independent verification finds no missing, unexpected, duplicate, or out-of-source memberships;
- interrupted and repeated operations converge on the same verified result.

### 17. Version schemas and publish migration notes

Version the config, inventory, inspection result, judgment, master, plan, receipt, run-state, and verification schemas. Validate at every boundary. When fields change, provide a migration command or a clear incompatibility message.

### 18. Reduce duplicated entry points

Clarify one supported invocation path for users and one module API for tests. The package already has `photo_fieldwork.__main__`, a shell wrapper, core CLI code, and skill-local scripts. Document which layer owns each responsibility and migrate recurring run-specific helpers into tested package commands.

### 19. Add machine-readable and human-readable report contracts

One verifier currently writes Markdown regardless of the extension passed to `--report`. Make format selection explicit: valid JSON for `.json`, Markdown for `.md`, or an output directory that always receives both. Test report schemas and render public-safe summaries from structured data.

### 20. Keep `SKILL.md` lean and move mechanics into references

The skill should remain the operational spine: invariants, phases, stop conditions, and required artifacts. Put source-adapter details, schema tables, evaluation mathematics, troubleshooting, and Apple Photos implementation notes in focused references. This will make the skill easier for an agent to follow without weakening its standards.

## Implemented in Revision I

Revision I implements or establishes the following v04-I findings as repository contracts:

- a first-class visible-library still source in the Swift app and bridge;
- a read-only whole-library inventory builder;
- switches to disable classification or face detection when they are unnecessary;
- candidate controls for excluding generated albums and requiring material outside a prior corpus;
- preservation of all Vision labels during inspection merge;
- more graceful contact-sheet handling of corrupt previews;
- preview-export verification;
- independent verification against the visible-library source.

Revision I also removes the hard-coded library count, adds data-minimization profiles, separates assignments from retrieval hypotheses, enforces per-view gates, validates structured feedback, binds plans to evaluated master hashes, adds local perceptual clustering, writes contact-sheet indexes, types verifier reports, lints public-safe reports, and records atomic run-state transitions. The remaining recommendations form the next benchmark and product milestones below.

## Suggested implementation sequence

### Milestone A: contracts and correctness

1. Version schemas.
2. Separate candidate and assigned views.
3. Add per-view release gates.
4. Add append-only judgment and exclusion ledgers.
5. Hash the evaluated master and bind it to plans and receipts.
6. Add final post-change audit enforcement.

### Milestone B: whole-library reliability

1. Finish the source adapter and inventory snapshot manifest.
2. Remove hard-coded counts and private-field leakage.
3. Replace wildcard retrieval with indexed set-based retrieval.
4. Add perceptual/sequence duplicate clustering.
5. Implement atomic run state, progress, and resume.

### Milestone C: editorial interface and evaluation

1. Add stable contact-sheet manifests or a local review surface.
2. Add typed evidence and negative constraints.
3. Add automatic sparse-view quota relaxation.
4. Add fresh-sample and regression-canary policies.
5. Add diversity controls beyond a named-person fraction.

### Milestone D: release discipline

1. Run the benchmark matrix against committed and proposed versions.
2. Publish aggregate timing, intervention, and correctness results.
3. Update the skill and public documentation from observed behavior.
4. Cut a versioned release with migration notes and a known-good example run.

## Definition of done for the next serious release

The release is ready when:

- whole-library inventory requires no machine-specific code edit;
- source drift is detected and deliberately versioned;
- candidate hypotheses cannot become assignments implicitly;
- all material views meet their own evaluation gates;
- uncertainty and tiny samples are reported honestly;
- every final change triggers a final frozen-master audit;
- plans are cryptographically bound to the evaluated master;
- feedback, holds, and rejects survive every round as structured data;
- perceptual duplicate control happens before final selection;
- private fields are structurally excluded from shareable outputs;
- a stopped inspection can resume safely;
- test and production writes are idempotent;
- an independent verifier confirms exact membership and source containment;
- the benchmark suite passes from a clean checkout.

## Final view

`photo-fieldwork` should keep its moral seriousness. The project is valuable because it treats selection as accountable work: local pixels, human judgment, uncertainty, privacy, and independent verification all matter.

The courageous next move is not to add more curatorial language. It is to encode the existing standard of care deeply enough that the software can carry it under pressure. Once assignment, evaluation, provenance, and recovery are dependable, the project will be more than a personal archive workflow. It will be a credible pattern for working responsibly with large, intimate visual collections.
