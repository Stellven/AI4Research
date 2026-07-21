#!/bin/bash

FILE=~/.claude/personality-anchor.txt

if [ -f "$FILE" ]; then
    cat "$FILE"
else
    exit 0
fi
