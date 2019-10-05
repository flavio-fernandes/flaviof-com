+++
author = "flaviof"
categories = ["main", "hacks"]
date = "2019-10-05T18:20:00-05:00"
tags = ["bash"]
title = "dynamic DNS update"
+++

A handy script for updating DNS of a domain in Google Cloud.

<!--more-->

Needed a way to access a system that has its address dynamically
assigned via DHCP. Then I remembered that I could just use my
[Google domain][google_syn_records] to get that address via DNS.
Google offers an easy way of updating any host in your domain
via [REST][]. All I needed was a little script to grab the current
IP and push it using [their API][google_dyndns_api].

Thus **[dyndns.sh][]**.

```
#!/bin/bash

# Usage: $0 [--force [<IP>]]

# Create a file called $DYNDNSINFO that has the
# dns host and access info. Example:
#
# # https://domains.google.com/m/registrar/flaviof.dev/dns
# USERNAME='flaviof'
# PASSWORD='superSecret'
# HOST='rh.flaviof.dev'

DYNDNSINFO='../.dyndnsauth'
#set -o xtrace
set -o errexit

function get_device() {
    ip route show default 2>/dev/null | grep 'default via ' | grep -oP "(?<= dev )[^ ]+" | head -1
}

function get_ip() {
    DEV=${1:-'bridge0'}
    ip -4 addr show $DEV 2>/dev/null | grep -oP "(?<=inet ).*(?=/)" | head -1
}

function update_dns() {
    USERNAME=$1
    PASSWORD=$2
    HOST=$3
    IP=$4

    wget --quiet \
     --user ${USERNAME} \
     --password ${PASSWORD} \
     --method POST \
     --header 'User-Agent: wget' \
     --header 'cache-control: no-cache' \
     --output-document \
     - "https://domains.google.com/nic/update?hostname=${HOST}&myip=${IP}"
    echo ''
}

DEV=$(get_device)
IP=$(get_ip $DEV)
cd "$(dirname $0)"
source ${DYNDNSINFO}
[ -n "${USERNAME}" ] || { >&2 echo "no USERNAME, no deal"; exit 1; }
[ -n "${PASSWORD}" ] || { >&2 echo "no PASSWORD, no deal"; exit 2; }
[ -n "${HOST}" ] || { >&2 echo "no HOST, no deal"; exit 3; }
[ -n "${IP}" ] || { >&2 echo "no ip, no deal"; exit 4; }

# check if this is needed at all by doing a dns lookup
if [ "$1" == "--force" ] || [ "$1" == "-f" ]; then
    CURR_DNS_IP=''
    [ -n "$2" ] && IP="$2"
else
    CURR_DNS_IP=$(dig ${HOST} +short 2>/dev/null)
fi

echo "x${CURR_DNS_IP}" | grep --quiet "${IP}" && \
    echo "${HOST} is ${IP} already: noop" || \
    update_dns ${USERNAME} ${PASSWORD} ${HOST} ${IP}
```

Then, I created file `../.dyndnsauth` as mentioned in the usage above and added this to cron:

```
$ crontab -l
MAILTO=""
*/20 * * * * /home/ff/bin/dyndns.sh >/dev/null 2>&1 ||:
```

The function [get_device][] is handy for getting the interface that my system is using to reach external networks.
And [get_ip][] is handy for getting the IP address on that device. Notice that I took a shortcut for cases when there
are more than one by grabbing the first choice.

If this is useful to you, put it in your path. And feel free to share it with your geek friends. :)

[google_syn_records]: https://support.google.com/domains/answer/6069273?hl=en "Google Synthetic records"
[REST]: https://restfulapi.net/ "REpresentational State Transfer"
[google_dyndns_api]: https://support.google.com/domains/answer/6147083 "Using the API to update your Dynamic DNS record"
[dyndns.sh]: https://gist.githubusercontent.com/flavio-fernandes/acb8d9031c54fe2f5c5050c0c3907f9c/raw/1c197d787e95b9c23881316553c475ced80fc100/dyndns.sh
[get_device]: https://gist.github.com/flavio-fernandes/acb8d9031c54fe2f5c5050c0c3907f9c#file-dyndns-sh-L17-L19
[get_ip]: https://gist.github.com/flavio-fernandes/acb8d9031c54fe2f5c5050c0c3907f9c#file-dyndns-sh-L21-L24
