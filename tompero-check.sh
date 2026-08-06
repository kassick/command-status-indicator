#!/bin/bash

# Returns 1 if we have a token file with a valid requester token

TOKEN_FILE=~/.config/tompero/requester_token

if [ ! -f "$TOKEN_FILE" ]; then
    echo "No token file" > /dev/stderr
    echo '{"status": "'missing'"}'
    exit 0
fi

exp=$(cat "$TOKEN_FILE" | cut -d \. -f 2 | base64 --decode | jq .exp)
ts=$(date "+%s")

if [ -z "$exp" ] || [ -z "$ts" ]; then
    echo Error trying to parse timestamp or token expiration > /dev/stderr
    echo '{"status": "'invalid'"}'
    exit 0
fi

if (( $ts >= $exp )); then
    echo Expired, get new token > /dev/stderr
    echo '{"status": "'expired'"}'
    exit 0
fi

echo Token is valid, expires in $(( ($exp - $ts) / 60 )) minutes > /dev/stderr
echo '{"status": "'valid'"}'
exit 0
