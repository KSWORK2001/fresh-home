#!/usr/bin/env bash
# Build AND SIGN both widgets using the local Tizen identity
# (author cert generated from the Tizen Developer CA + sdk-public distributor).
set -euo pipefail
cd "$(dirname "$0")"
node sign.js ../launcher ../freshhome-launcher-signed.wgt
node sign.js ../homekey ../freshhome-homekey-signed.wgt
echo "signed packages ready:"
ls -la ../freshhome-*-signed.wgt
