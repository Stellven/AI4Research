#!/bin/bash
# TVS Email Search - Shell Backend
# Usage: ./search-emails.sh <keyword>

KEYWORD="$1"
MAX_RESULTS=3

if [ -z "$KEYWORD" ]; then
  echo '{"error": "Missing keyword"}'
  exit 1
fi

# Search emails
SEARCH_OUTPUT=$(himalaya envelope list --page-size 10 --output json "subject $KEYWORD" 2>&1)

# Extract JSON from output (himalaya outputs warnings to stderr)
JSON_OUTPUT=$(echo "$SEARCH_OUTPUT" | grep '^\[' | head -1)

if [ -z "$JSON_OUTPUT" ]; then
  echo '{"total": 0, "keyword": "'"$KEYWORD"'", "emails": []}'
  exit 0
fi

# Count total
TOTAL=$(echo "$JSON_OUTPUT" | jq 'length')

# Get top N emails
TOP_EMAILS=$(echo "$JSON_OUTPUT" | jq ".[:$MAX_RESULTS]")

# For each email, read content and generate summary
RESULT='{"total": '$TOTAL', "keyword": "'"$KEYWORD"'", "emails": []}'

echo "$TOP_EMAILS" | jq -c '.[]' | while read -r EMAIL; do
  ID=$(echo "$EMAIL" | jq -r '.id')
  SUBJECT=$(echo "$EMAIL" | jq -r '.subject')

  # Read email content
  BODY=$(himalaya message read "$ID" 2>/dev/null | grep -v '^\[' | head -50 | tr '\n' ' ' | sed 's/"/\\"/g' | cut -c1-500)

  # Add to result
  echo "$EMAIL" | jq --arg body "$BODY" --arg summary "• $SUBJECT" '. + {body: $body, summary: $summary}'
done | jq -s '.' | jq --argjson total "$TOTAL" --arg keyword "$KEYWORD" '{total: $total, keyword: $keyword, emails: .}'
