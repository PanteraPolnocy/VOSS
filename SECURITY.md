# Security Policy

## Supported Versions

Anything that is present in this repository can be asked about. Forks of the code, custom modifications - I cannot answer questions about these.

## Reporting a Vulnerability

- Use GitHub reporting system
- Send an e-mail to panterapolnocy+github@gmail.com (checked on a daily basis)

Any fixed vulnerabilities will have a mention of the reporter's name (credited), unless explicitly stated otherwise.

## What counts as one here

The usual, of course: a way to make the tools run something they should not, or write somewhere they should not. And because this skill deals with people's health, these as well:

- a tool that prints an answer to a gate question, or lets anything from a personal file slip into an error message, a log, or a file nobody asked for
- a private file (`personal.json`, `household.md`, anything in `images/private/`) that ends up in the public build, or a private package or page that gets written into a git working tree
- a tool that prints a dose, calls a combination "safe" because nothing is on file for it, or answers from a database without naming its source
- data in this repository that its licence does not allow to be passed on, or a credit line that has gone missing

Two things are by design, and not vulnerabilities.

The gate on a personal file is a soft lock. The file is plain JSON, and whoever can open it can read it. [docs/limits.md](docs/limits.md) says so at length. Keep the file where only you can reach it.

What he writes and prints for you is plain text too. A page (a card, a passport, a brief, a timetable, a note) is meant to be read by whoever you hand it to, and once a gate is open the tools print what is on file, because reading it back is what they are for. A code scanner reports that as private data stored and logged in clear text. Here it is the feature: a page is written only when you have seen it and asked for it.

## Keep health data out of reports

Never attach a personal file, a private package or a household file to an issue, a pull request or a report, and never paste one in. A made-up file that shows the same fault is enough; `tests/fixtures/` has one to start from.
