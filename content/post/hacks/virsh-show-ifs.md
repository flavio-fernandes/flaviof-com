+++
author = "flaviof"
categories = ["main", "hacks"]
date = "2016-12-07T09:40:32-05:00"
tags = ["bash", "libvirt"]
title = "virsh show ifs"
+++

A handy script for showing the vms configured in libvirt.

<!--more-->

While playing with [virsh][], I'm always interested in finding out
the macs, ips, networks and vnc port of the configured virtual machines.

Thus **[virsh_show_ifs][]**.

```
#!/bin/bash

virt-addr() {
    VM="$1"
    vm_mac=$(virsh dumpxml $VM | grep "mac address" | sed "s/.*'\(.*\)'.*/\1/g")
    arp -an | grep "${vm_mac}" | awk '{ gsub(/[\(\)]/,"",$2); print $2 }'
}

for x in $(virsh list --all | awk '{ if (NR > 2 && $2 != "") {print $2} }') ; do \
    v=$(virsh vncdisplay $x 2> /dev/null || true)
    vip=$(virt-addr $x 2> /dev/null || true)
    echo "vm name: $x vnc: ${v:--} ip: ${vip:--}"
    virsh domiflist $x | awk '{ if (NR > 2) {print $0} }'
done
```

Here is an example output from using that script in my system

```
$ virsh_show_ifs
vm name: foo vnc: 127.0.0.1:0 ip: 10.1.0.146
vnet0      bridge     virbr1     virtio      52:54:00:f2:23:49

vm name: vm1 vnc: 127.0.0.1:1 ip: 192.168.122.110
vnet1      network    default    virtio      52:54:00:8e:f0:5a

vm name: vm2 vnc: 127.0.0.1:2 ip: 192.168.122.145
vnet2      network    default    virtio      52:54:00:0a:dd:bc

vm name: vm3 vnc: 127.0.0.1:3 ip: 192.168.122.2
vnet3      network    default    virtio      52:54:00:ef:4f:4d
```

If this is useful to you, put it in your path.
And feel free to share it with your geek friends. :)


[virsh]: http://libvirt.org/virshcmdref.html#viewing
[virsh_show_ifs]: https://gist.githubusercontent.com/flavio-fernandes/a773842c5b6748992482d74d6c1cb543/raw/d57ea3850cc40052ff09abad609e9662f00b432b/virsh_show_ifs
[virsh_show_ifs_old]: https://gist.githubusercontent.com/anonymous/53e04a414c0d653b0edc2d39d513b1a4/raw/7409bcde914a83eafe916871d725f98058d4dc88/gistify146068.txt
