# Procedures: one document per working cycle

A cycle is one round of: something to do at the bench, something the
tools measure, and whatever the bench says back that no tool can see.
Each gets its own document here, named by the date and the task.

They exist because the other three documents cannot do this job:

- `docs/build-guide.md` is the whole build, generated, and is the map.
- `docs/lab-notebook.md` is the record, generated from the log, and only
  ever holds what a tool actually measured.
- These are the working documents in between: short, one task, read on
  GitHub away from the terminal, and edited as the cycle goes.

## The loop

1. A procedure is pushed here before the work.
2. It is read on GitHub, at the bench.
3. The steps marked **you** are done by hand. The steps marked
   **the tools** are run from the workstation.
4. Anything the tools cannot see, a smell, a reading that looked odd, a
   connector that did not seat, is said in chat and written into the
   document's observations.
5. The document is updated and pushed. When the cycle closes, its
   outcome is written at the top and the measurements it produced are in
   the notebook, not here.

## What goes in one, and what does not

A procedure holds the **task**: what to touch, in what order, what to
look for, and what to report back. It holds **observations**, in the
operator's words, because those are evidence too and nothing else in
this repository has a place for them.

It does not hold measurements. A number that a tool produced belongs in
`docs/lab-log.jsonl` and reaches the notebook from there. A number typed
into a procedure is a second copy that will drift from the first, and a
reader comparing the two would have no way to tell which was lying.

## Naming

`YYYY-MM-DD-<task>.md`. One task, one file. A cycle that spans two days
keeps its original name and says so.
