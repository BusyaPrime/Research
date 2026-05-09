# Contribution workflow

Use small branches and keep every commit tied to one reviewable change.

## Branch checklist

1. Start from `master`.
2. Create a branch with a scope prefix: `docs/`, `fix/`, `test/`, `refactor/`,
   `ci/`, or `chore/`.
3. Make the smallest coherent change.
4. Add or update tests when behavior changes.
5. Run the local checks that match the touched area.
6. Open a pull request with validation notes and linked issue.

## Commit style

Use Conventional Commits:

- `docs: add reproducible run notes`
- `test: cover configured adapter fallback`
- `fix: reject same-bar execution timestamps`
- `refactor: isolate report bundle writer`
- `ci: add release bundle verification step`

Avoid vague messages such as `update`, `fix`, `changes`, or `wip`.

## Pull request validation

At minimum, record:

- install command or dependency state;
- lint/typecheck result when Python code changed;
- pytest target(s) run;
- release smoke or reason it was not relevant;
- manual review notes for docs-only changes.

## Artifact discipline

Do not commit local `.env`, caches, generated dependency directories, ad hoc
notebooks, or release outputs unless the repository explicitly treats the
artifact as source-controlled evidence.
