# Git and Antigravity Workflow

## Branching and commits

- `main` always passes tests. Work on `feature/<name>` branches and merge by pull request.
- One logical change per commit, Conventional Commit style:
  `feat(lexer): ...`, `fix(parser): ...`, `test: ...`, `docs: ...`, `chore: ...`.
- Tag each review: `git tag review-1 && git push --tags` (then `review-2`, `review-3`, `final`).
- Run the tests before every push: `python -m unittest discover -s tests -t .`

## Using Antigravity / Gemini Pro safely

1. Open the repo folder as the workspace so the agent can see `docs/`.
2. Always give it the specs: tell it to read `docs/GRAMMAR.md`, `docs/ISA.md` and
   `docs/VERIFIER_DESIGN.md` first, and to treat them as the source of truth.
3. Ask for one phase per task, and require tests in the same task.
4. Review the diff yourself before committing. You must be able to explain every
   line of the verifier at the viva.
5. Let the agent run the tests, but commit and push yourself.

### Prompt template: Review 2 (semantic analysis + codegen + VM)

> Read docs/GRAMMAR.md and docs/ISA.md. Implement `semantic/` (symbol table and
> type checker for int/bool, with the checks listed at the end of GRAMMAR.md),
> then `codegen/` (AST to bytecode using the compilation scheme in ISA.md,
> serializer for the .bc format, and a disassembler), then `vm/` (interpreter
> with value stack and call frames). Do not change the ISA. Add unittest tests
> for each module and an end-to-end test that compiles and runs every valid file
> in examples/ and checks printed output. Run the tests and keep them green.

### Prompt template: Review 3 (verifier + fuzzing)

> Read docs/VERIFIER_DESIGN.md and docs/ISA.md. Implement `verifier/` exactly as
> designed: decoder, jump-target check, worklist abstract interpreter with merge
> rules, and diagnostics using the listed rule names. Make the VM loader refuse
> to run unverified code (add an explicit `--unsafe` flag for demos only). Create
> tests/malicious/ with at least two crafted .bc files per rule, and a mutation
> fuzzer script that reports accepted/rejected counts and whether any accepted
> file crashes the VM. Add tests; keep all green.

## First-time GitHub setup

```bash
git init -b main              # skip if cloning the zip's .git folder
git add . && git commit -m "feat: review 1 front end and design docs"
git remote add origin https://github.com/<you>/secure-bytecode-vm.git
git push -u origin main
git tag review-1 && git push --tags
```
