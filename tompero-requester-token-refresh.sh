#!/bin/bash

tompero login
TOKEN=$(tompero auth requester-token get)

if [ "$?" = 0 ]; then
    echo Token Refreshed:
    echo "$TOKEN" | cut -d \. -f 2 | base64 --decode | jq
else
    echo Failed to fetch token ...
    echo "$TOKEN"
fi

sleep 3
