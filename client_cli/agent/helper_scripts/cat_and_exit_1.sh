#!/usr/bin/env bash
# Fake editor that prints the file content and exits with failure.
# Use as EDITOR/JJ_EDITOR/GIT_EDITOR to capture what an interactive
# command would show (e.g. jj squash, git commit) without completing it.
printf 'EDITOR_FILE_CONTENT_BEGIN\n'
sed 's/^/  /' "$1"
printf '\nEDITOR_FILE_CONTENT_END\n'
exit 1
