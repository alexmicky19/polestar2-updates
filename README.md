# Polestar 2 Software Updates — Unofficial Tracker

A single-page tracker of every released Polestar 2 software version and its
official release notes, styled after the
[Polestar 4 updates tracker](https://jaybizzle.github.io/polestar4-updates).

**Not affiliated with or endorsed by Polestar.** Version notes © Polestar.

## What it shows

- The latest documented software version (currently **P5.1.17**).
- The full release history, newest first, each version expandable to its
  official release notes (model-year sub-sections preserved).
- Live search across versions and notes, plus expand/collapse-all.

## Source & the "no dates" caveat

Data is taken from the
[Polestar 2 owner's manual — Software updates](https://www.polestar.com/uk/manual/polestar-2/2027/software-updates/)
(UK, model-year 2027 view, which lists all historical versions).

Unlike newer Polestar models (3/4/5), whose updates are served through Polestar's
`support-car-content` release-notes API **with dates**, the Polestar 2
(project code `P319`) publishes updates only through the owner's manual, which
gives version numbers and notes but **no release dates**. So this tracker shows
the full changelog and version history, but cannot compute "days between
releases" or predict the next update.

## Updating the data

The version data is currently baked into `index.html`. To refresh after a new
release, re-capture the version list from the manual page and update the `DATA`
array near the bottom of `index.html`.

## License

Code: MIT. Release note text is © Polestar and reproduced here for reference.
