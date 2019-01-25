#!/bin/bash

date

# scan for changes
pipenv run python scan_pages.py

# check for changes files and push
git add -u

if [ $(git diff --cached | wc -l) -ne 0 ]; then

git commit -a -m "$(git status --porcelain | wc -l) files | $(git status --porcelain | sed '{:q;N;s/\n/, /g;t q}' | sed 's/^ *//g')" > /dev/null
git push > /dev/null 2>&1

fi
